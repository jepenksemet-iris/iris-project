"""Tes migrasi skema v1 -> v2 (tahap 7 / Paket B).

Database v1 dibangun manual dengan CHECK lama, lalu init_tenant_db()
harus memigrasikannya: jenis mutasi dipetakan, kolom effective_date
ditambah, versi menjadi 2, dan data lain utuh.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from iris_db import (
    SCHEMA_VERSION,
    get_schema_version,
    init_tenant_db,
    record_opening_balance,
)

V1_MOVEMENTS_DDL = """
CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    barcode TEXT UNIQUE,
    name TEXT NOT NULL,
    category_id INTEGER,
    unit_id INTEGER,
    buy_price INTEGER NOT NULL DEFAULT 0,
    sell_price INTEGER NOT NULL DEFAULT 0,
    min_stock REAL NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE outlets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    address TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE stock (
    product_id INTEGER NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    outlet_id INTEGER NOT NULL REFERENCES outlets (id) ON DELETE CASCADE,
    qty REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (product_id, outlet_id)
);
CREATE TABLE stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products (id),
    outlet_id INTEGER NOT NULL REFERENCES outlets (id),
    qty REAL NOT NULL,
    kind TEXT NOT NULL
        CHECK (kind IN ('sale', 'purchase', 'adjustment', 'return', 'transfer')),
    ref_type TEXT NOT NULL DEFAULT '',
    ref_id INTEGER,
    note TEXT NOT NULL DEFAULT '',
    user_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _build_v1_db(tmp_path):
    from iris_db import get_tenant_db
    conn = get_tenant_db("toko-demo", data_dir=str(tmp_path))
    conn.executescript(V1_MOVEMENTS_DDL)
    conn.execute("INSERT INTO outlets (id, name, slug) VALUES (1, 'Outlet Utama', 'outlet-utama')")
    conn.execute("INSERT INTO products (id, sku, name) VALUES (1, 'GULA-1KG', 'Gula Pasir 1 kg')")
    conn.execute("INSERT INTO stock (product_id, outlet_id, qty) VALUES (1, 1, 2)")
    conn.execute(
        "INSERT INTO stock_movements (product_id, outlet_id, qty, kind, note)"
        " VALUES (1, 1, 5, 'adjustment', 'Saldo awal')"
    )
    conn.execute(
        "INSERT INTO stock_movements (product_id, outlet_id, qty, kind, note)"
        " VALUES (1, 1, -2, 'adjustment', 'Koreksi')"
    )
    conn.execute(
        "INSERT INTO stock_movements (product_id, outlet_id, qty, kind, note)"
        " VALUES (1, 1, -1, 'sale', 'Penjualan')"
    )
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()


def test_fresh_db_is_v2(tmp_path):
    # Skema terbaru kini v3; DB baru langsung v3 (migrasi v1->v2 tetap
    # diuji lewat test_migrate_v1_to_v2 di bawah, yang berantai ke v3).
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_schema_version(conn) == SCHEMA_VERSION == 4
        kinds = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'stock_movements'"
        ).fetchone()[0]
        assert "opening_balance" in kinds and "effective_date" in kinds
    finally:
        conn.close()


def test_migrate_v1_to_v2(tmp_path):
    _build_v1_db(tmp_path)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        # Rantai migrasi kini berakhir di v3.
        assert get_schema_version(conn) == 4  # rantai migrasi berakhir di v4
        # Data stok utuh, jenis mutasi dipetakan.
        assert conn.execute(
            "SELECT qty FROM stock WHERE product_id = 1 AND outlet_id = 1"
        ).fetchone()[0] == 2
        kinds = [r[0] for r in conn.execute(
            "SELECT kind FROM stock_movements ORDER BY id")]
        assert kinds == ["opening_balance", "adjustment_out", "sale"]
        # Saldo awal hasil migrasi tidak bisa dicatat dua kali.
        import pytest
        with pytest.raises(ValueError):
            record_opening_balance(conn, 1, 1, 5)
        # Jenis baru bisa dipakai setelah migrasi.
        conn.execute(
            "INSERT INTO stock_movements (product_id, outlet_id, qty, kind,"
            " note, effective_date) VALUES (1, 1, 3, 'adjustment_in', 'Tambah', '2026-11-25')"
        )
        conn.commit()
        row = conn.execute(
            "SELECT effective_date FROM stock_movements WHERE kind = 'adjustment_in'"
        ).fetchone()
        assert row[0] == "2026-11-25"
    finally:
        conn.close()
