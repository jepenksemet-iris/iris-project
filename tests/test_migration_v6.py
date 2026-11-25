"""Tes migrasi skema v6 (P1 Tahap 7): tabel retur + jenis 'purchase_return'."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from iris_db import (
    SCHEMA_VERSION,
    _migrate_v2_to_v3,
    _migrate_v3_to_v4,
    _migrate_v4_to_v5,
    get_schema_version,
    get_tenant_db,
    init_tenant_db,
    migrate_tenant_db,
)
from test_migration_v3 import _build_v2_db


def test_fresh_db_is_v6(tmp_path):
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_schema_version(conn) == SCHEMA_VERSION == 6
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name='returns'").fetchone() is not None
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name='return_items'").fetchone() is not None
        assert "purchase_return" in conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'stock_movements'"
        ).fetchone()["sql"]
        conn.execute(
            "INSERT INTO outlets (id, name, slug) VALUES (1, 'Outlet Utama', 'outlet-utama')")
        conn.execute(
            "INSERT INTO products (id, sku, name) VALUES (1, 'GULA-1KG', 'Gula Pasir 1 kg')")
        conn.execute(
            "INSERT INTO returns (kind, outlet_id, return_no, reason)"
            " VALUES ('sale_return', 1, 'RS-20261125-0001', 'Rusak')")
        conn.execute(
            "INSERT INTO stock_movements (product_id, outlet_id, qty, kind)"
            " VALUES (1, 1, -2, 'purchase_return')")
        conn.commit()
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_migrate_v5_to_v6_keeps_data(tmp_path):
    _build_v2_db(tmp_path)
    conn = get_tenant_db("toko-demo", data_dir=str(tmp_path))
    _migrate_v2_to_v3(conn)
    _migrate_v3_to_v4(conn)
    conn.execute("PRAGMA user_version = 4")
    conn.commit()
    conn.close()
    # init pertama: skema v6 dibuat (tabel yang hilang ikut dibuat),
    # lalu rantai migrasi v4->v5->v6 berjalan.
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    assert get_schema_version(conn) == 6
    conn.execute("PRAGMA user_version = 5")
    conn.commit()
    conn.close()
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_schema_version(conn) == 6
        assert conn.execute(
            "SELECT COUNT(*) n FROM sales").fetchone()["n"] == 1
        assert conn.execute(
            "SELECT qty FROM stock WHERE product_id = 1").fetchone()["qty"] == 8
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_schema_version(conn) == 6
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
