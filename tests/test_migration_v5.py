"""Tes migrasi skema v5 (P1 Tahap 6): modul pembelian.

v4 -> v5: kolom pemasok/pembelian + snapshot purchase_items +
jenis mutasi 'purchase_void'. Data lama tetap utuh.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from iris_db import (
    SCHEMA_VERSION,
    _migrate_v2_to_v3,
    _migrate_v3_to_v4,
    get_schema_version,
    get_tenant_db,
    init_tenant_db,
    migrate_tenant_db,
)
from test_migration_v3 import _build_v2_db


def test_fresh_db_is_v5(tmp_path):
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_schema_version(conn) == SCHEMA_VERSION == 6
        sup_cols = [r[1] for r in conn.execute("PRAGMA table_info(suppliers)")]
        assert {"notes", "is_active", "updated_at"} <= set(sup_cols)
        pur_cols = [r[1] for r in conn.execute("PRAGMA table_info(purchases)")]
        assert {"notes", "cancel_reason", "cancelled_by",
                "cancelled_at"} <= set(pur_cols)
        item_cols = [r[1] for r in conn.execute("PRAGMA table_info(purchase_items)")]
        assert {"product_name", "sku", "unit"} <= set(item_cols)
        assert "purchase_void" in conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'stock_movements'"
        ).fetchone()["sql"]
        conn.execute(
            "INSERT INTO outlets (id, name, slug) VALUES (1, 'Outlet Utama', 'outlet-utama')")
        conn.execute(
            "INSERT INTO products (id, sku, name) VALUES (1, 'GULA-1KG', 'Gula Pasir 1 kg')")
        conn.execute(
            "INSERT INTO stock_movements (product_id, outlet_id, qty, kind)"
            " VALUES (1, 1, -2, 'purchase_void')")
        conn.commit()
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_migrate_v4_to_v5_keeps_data(tmp_path):
    _build_v2_db(tmp_path)
    conn = get_tenant_db("toko-demo", data_dir=str(tmp_path))
    _migrate_v2_to_v3(conn)
    _migrate_v3_to_v4(conn)
    conn.execute("PRAGMA user_version = 4")
    conn.commit()
    conn.close()
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_schema_version(conn) == 6
        assert conn.execute(
            "SELECT COUNT(*) n FROM sales").fetchone()["n"] == 1
        assert conn.execute(
            "SELECT kind FROM stock_movements").fetchone()["kind"] == "opening_balance"
        assert conn.execute(
            "SELECT qty FROM stock WHERE product_id = 1").fetchone()["qty"] == 8
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()
    # Migrasi ulang idempotent.
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_schema_version(conn) == 6
        assert conn.execute(
            "SELECT COUNT(*) n FROM sales").fetchone()["n"] == 1
    finally:
        conn.close()


def test_unknown_version_not_migrated(tmp_path):
    conn = get_tenant_db("toko-demo", data_dir=str(tmp_path))
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    try:
        migrate_tenant_db(conn, 99)
    except ValueError:
        pass
    else:
        raise AssertionError("versi 99 seharusnya ditolak")
    assert get_schema_version(conn) == 99
    conn.close()
