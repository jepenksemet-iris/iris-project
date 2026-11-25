"""Tes migrasi skema v3 (P1 Tahap 3).

v2 -> v3: snapshot sale_items, sales dibuat ulang (status 'pending' +
kolom baru), sale_payments baru. v1 -> v3 berantai. Data lama utuh,
foreign key check bersih, migrasi ulang idempotent.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from iris_db import (
    SCHEMA_VERSION,
    get_schema_version,
    get_tenant_db,
    init_tenant_db,
    migrate_tenant_db,
)

V2_DDL = """
CREATE TABLE outlets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE, address TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '', is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT NOT NULL UNIQUE,
    barcode TEXT UNIQUE, name TEXT NOT NULL,
    category_id INTEGER, unit_id INTEGER,
    buy_price INTEGER NOT NULL DEFAULT 0, sell_price INTEGER NOT NULL DEFAULT 0,
    min_stock REAL NOT NULL DEFAULT 0, is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE stock (
    product_id INTEGER NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    outlet_id INTEGER NOT NULL REFERENCES outlets (id) ON DELETE CASCADE,
    qty REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (product_id, outlet_id));
CREATE TABLE stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products (id),
    outlet_id INTEGER NOT NULL REFERENCES outlets (id),
    qty REAL NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('sale', 'purchase', 'adjustment',
        'return', 'transfer', 'opening_balance', 'adjustment_in',
        'adjustment_out')),
    ref_type TEXT NOT NULL DEFAULT '', ref_id INTEGER,
    note TEXT NOT NULL DEFAULT '', user_id INTEGER,
    effective_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    outlet_id INTEGER NOT NULL REFERENCES outlets (id),
    user_id INTEGER, customer_id INTEGER,
    invoice_no TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'completed'
        CHECK (status IN ('completed', 'void', 'returned')),
    subtotal INTEGER NOT NULL DEFAULT 0, discount INTEGER NOT NULL DEFAULT 0,
    tax INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
    paid INTEGER NOT NULL DEFAULT 0, payment_method TEXT NOT NULL DEFAULT 'cash',
    created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sales (id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products (id),
    qty REAL NOT NULL CHECK (qty > 0),
    price INTEGER NOT NULL CHECK (price >= 0),
    discount INTEGER NOT NULL DEFAULT 0);
"""


def _build_v2_db(tmp_path):
    conn = get_tenant_db("toko-demo", data_dir=str(tmp_path))
    conn.executescript(V2_DDL)
    conn.execute("INSERT INTO outlets (id, name, slug) VALUES (1, 'Outlet Utama', 'outlet-utama')")
    conn.execute("INSERT INTO products (id, sku, name, sell_price) VALUES (1, 'GULA-1KG', 'Gula Pasir 1 kg', 17000)")
    conn.execute("INSERT INTO stock (product_id, outlet_id, qty) VALUES (1, 1, 8)")
    conn.execute(
        "INSERT INTO stock_movements (product_id, outlet_id, qty, kind, note)"
        " VALUES (1, 1, 10, 'opening_balance', 'Saldo awal')")
    conn.execute(
        "INSERT INTO sales (id, outlet_id, invoice_no, status, subtotal, total, paid)"
        " VALUES (1, 1, 'INV-20261125-0001', 'completed', 34000, 34000, 34000)")
    conn.execute(
        "INSERT INTO sale_items (sale_id, product_id, qty, price)"
        " VALUES (1, 1, 2, 17000)")
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()


def test_fresh_db_is_v3(tmp_path):
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_schema_version(conn) == SCHEMA_VERSION == 3
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "sale_payments" in tables
        item_cols = [r[1] for r in conn.execute("PRAGMA table_info(sale_items)")]
        assert {"product_name", "sku", "unit"} <= set(item_cols)
        sales_cols = [r[1] for r in conn.execute("PRAGMA table_info(sales)")]
        assert {"change_amount", "payment_ref", "idempotency_key",
                "idempotency_payload", "void_reason", "voided_by",
                "voided_at"} <= set(sales_cols)
        # Status 'pending' diterima CHECK baru.
        conn.execute(
            "INSERT INTO outlets (id, name, slug) VALUES (1, 'Outlet Utama', 'outlet-utama')")
        conn.execute(
            "INSERT INTO sales (outlet_id, invoice_no, status, total)"
            " VALUES (1, 'INV-X-1', 'pending', 0)")
        conn.commit()
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_migrate_v2_to_v3_keeps_data(tmp_path):
    _build_v2_db(tmp_path)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_schema_version(conn) == 3
        sale = conn.execute("SELECT * FROM sales WHERE id = 1").fetchone()
        assert sale["invoice_no"] == "INV-20261125-0001"
        assert sale["total"] == 34000 and sale["change_amount"] == 0
        assert sale["status"] == "completed"
        assert conn.execute(
            "SELECT COUNT(*) n FROM sale_items WHERE sale_id = 1"
        ).fetchone()["n"] == 1
        assert conn.execute(
            "SELECT qty FROM stock WHERE product_id = 1"
        ).fetchone()["qty"] == 8
        assert conn.execute(
            "SELECT kind FROM stock_movements"
        ).fetchone()["kind"] == "opening_balance"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()
    # Migrasi ulang idempotent: data dan versi tidak berubah.
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_schema_version(conn) == 3
        assert conn.execute(
            "SELECT COUNT(*) n FROM sales").fetchone()["n"] == 1
    finally:
        conn.close()


def test_migrate_v1_to_v3_chain(tmp_path):
    # v1: CHECK lama di stock_movements + sales v1 (tanpa kolom v3).
    from test_migration_v2 import V1_MOVEMENTS_DDL
    conn = get_tenant_db("toko-demo", data_dir=str(tmp_path))
    conn.executescript(V1_MOVEMENTS_DDL)
    conn.execute(
        "CREATE TABLE sales (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " outlet_id INTEGER NOT NULL REFERENCES outlets (id),"
        " user_id INTEGER, customer_id INTEGER,"
        " invoice_no TEXT NOT NULL UNIQUE,"
        " status TEXT NOT NULL DEFAULT 'completed'"
        "  CHECK (status IN ('completed', 'void', 'returned')),"
        " subtotal INTEGER NOT NULL DEFAULT 0, discount INTEGER NOT NULL DEFAULT 0,"
        " tax INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,"
        " paid INTEGER NOT NULL DEFAULT 0,"
        " payment_method TEXT NOT NULL DEFAULT 'cash',"
        " created_at TEXT NOT NULL DEFAULT (datetime('now')))")
    conn.execute(
        "CREATE TABLE sale_items (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " sale_id INTEGER NOT NULL REFERENCES sales (id) ON DELETE CASCADE,"
        " product_id INTEGER NOT NULL REFERENCES products (id),"
        " qty REAL NOT NULL CHECK (qty > 0),"
        " price INTEGER NOT NULL CHECK (price >= 0),"
        " discount INTEGER NOT NULL DEFAULT 0)")
    conn.execute("INSERT INTO outlets (id, name, slug) VALUES (1, 'Outlet Utama', 'outlet-utama')")
    conn.execute("INSERT INTO products (id, sku, name) VALUES (1, 'GULA-1KG', 'Gula Pasir 1 kg')")
    conn.execute(
        "INSERT INTO stock_movements (product_id, outlet_id, qty, kind, note)"
        " VALUES (1, 1, 5, 'adjustment', 'Saldo awal')")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_schema_version(conn) == 3
        assert conn.execute(
            "SELECT kind FROM stock_movements").fetchone()["kind"] == "opening_balance"
        assert conn.execute(
            "SELECT COUNT(*) n FROM sqlite_master WHERE type='table'"
            " AND name='sale_payments'").fetchone()["n"] == 1
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_unknown_version_not_migrated(tmp_path):
    conn = get_tenant_db("toko-demo", data_dir=str(tmp_path))
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    with pytest.raises(ValueError):
        migrate_tenant_db(conn, 99)
    assert get_schema_version(conn) == 99
    conn.close()
