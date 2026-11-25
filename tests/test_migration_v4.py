"""Tes migrasi skema v4 (P1 Tahap 5): jenis mutasi 'sale_void'.

v3 -> v4: stock_movements dibuat ulang dengan CHECK yang ditambah
'sale_void'; data lama disalin apa adanya.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from iris_db import (
    SCHEMA_VERSION,
    _migrate_v2_to_v3,
    get_schema_version,
    get_tenant_db,
    init_tenant_db,
    migrate_tenant_db,
)
from test_migration_v3 import _build_v2_db


def test_fresh_db_is_v4(tmp_path):
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_schema_version(conn) == SCHEMA_VERSION == 4
        assert "sale_void" in conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'stock_movements'"
        ).fetchone()["sql"]
        conn.execute(
            "INSERT INTO outlets (id, name, slug) VALUES (1, 'Outlet Utama', 'outlet-utama')")
        conn.execute(
            "INSERT INTO products (id, sku, name) VALUES (1, 'GULA-1KG', 'Gula Pasir 1 kg')")
        conn.execute(
            "INSERT INTO stock_movements (product_id, outlet_id, qty, kind)"
            " VALUES (1, 1, 2, 'sale_void')")
        conn.commit()
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_migrate_v3_to_v4_keeps_data(tmp_path):
    _build_v2_db(tmp_path)
    conn = get_tenant_db("toko-demo", data_dir=str(tmp_path))
    _migrate_v2_to_v3(conn)
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_schema_version(conn) == 4
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
        assert get_schema_version(conn) == 4
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
