"""Tes tahap 3: skema v1, hash password, login tenant, dan proteksi role."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from iris_db import (
    SCHEMA_VERSION,
    create_user,
    get_schema_version,
    get_user_by_username,
    init_tenant_db,
    verify_user,
)
import tenant_app


EXPECTED_TABLES = {
    "users", "outlets", "categories", "units", "products", "stock",
    "customers", "suppliers", "sales", "sale_items", "purchases",
    "purchase_items", "stock_movements", "cash_transactions",
}


def test_schema_v1_tables(tmp_path):
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_schema_version(conn) == SCHEMA_VERSION == 3
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert EXPECTED_TABLES <= tables
        # Slug berbahaya (path traversal) tetap ditolak.
        with pytest.raises(ValueError):
            init_tenant_db("../etc", data_dir=str(tmp_path))
    finally:
        conn.close()


def test_password_is_hashed_not_stored(tmp_path):
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        create_user(conn, "owner", "rahasia-123", "Pemilik", role="owner")
        row = get_user_by_username(conn, "owner")
        assert row["password_hash"] != "rahasia-123"
        assert verify_user(conn, "owner", "rahasia-123") is not None
        assert verify_user(conn, "owner", "salah") is None
        with pytest.raises(ValueError):
            create_user(conn, "pendek", "123", role="cashier")
    finally:
        conn.close()


def _client_with_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("IRIS_DATA_DIR", str(tmp_path))
    app = tenant_app.create_app()
    app.config.update(DATA_DIR=str(tmp_path), TESTING=True, WTF_CSRF_ENABLED=False)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        create_user(conn, "owner", "rahasia-123", "Pemilik", role="owner")
        create_user(conn, "kasir", "rahasia-123", "Kasir", role="cashier")
    finally:
        conn.close()
    return app.test_client()


def test_login_flow_and_protected_dashboard(tmp_path, monkeypatch):
    client = _client_with_owner(tmp_path, monkeypatch)
    assert client.get("/").status_code == 302  # belum login -> /login
    assert client.get("/products").status_code == 302
    assert b"Masuk" in client.get("/login").data
    # Login salah gagal, login benar berhasil.
    assert client.post("/login", data={
        "tenant": "toko-demo", "username": "owner", "password": "salah",
    }).status_code == 200
    resp = client.post("/login", data={
        "tenant": "toko-demo", "username": "owner", "password": "rahasia-123",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"toko-demo" in resp.data
    assert client.get("/products").status_code == 200
    assert client.get("/logout", follow_redirects=True).status_code == 200
    assert client.get("/").status_code == 302


def test_admin_only_route_enforces_role(tmp_path, monkeypatch):
    client = _client_with_owner(tmp_path, monkeypatch)
    client.post("/login", data={
        "tenant": "toko-demo", "username": "kasir", "password": "rahasia-123",
    })
    assert client.get("/admin-only").status_code == 403
    client.get("/logout")
    client.post("/login", data={
        "tenant": "toko-demo", "username": "owner", "password": "rahasia-123",
    })
    assert client.get("/admin-only").status_code == 200
