"""Tes tahap 6: modul produk & stok tenant.

Tambah/edit/arsip produk, penyesuaian stok atomik + ledger mutasi,
proteksi role, dan isolasi antar-tenant.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from iris_db import (
    create_user,
    get_product,
    get_stock_qty,
    init_tenant_db,
    list_stock_movements,
)
import tenant_app


def _client(tmp_path, monkeypatch, tenant="toko-demo"):
    monkeypatch.setenv("IRIS_DATA_DIR", str(tmp_path))
    app = tenant_app.create_app()
    app.config.update(DATA_DIR=str(tmp_path), TESTING=True, WTF_CSRF_ENABLED=False)
    conn = init_tenant_db(tenant, data_dir=str(tmp_path))
    try:
        create_user(conn, "owner", "rahasia-123", "Pemilik", role="owner")
        create_user(conn, "kasir", "rahasia-123", "Kasir", role="cashier")
    finally:
        conn.close()
    return app.test_client()


def _login(client, username="owner", tenant="toko-demo"):
    return client.post("/login", data={
        "tenant": tenant, "username": username, "password": "rahasia-123",
    }, follow_redirects=True)


def _product_data(**overrides):
    data = {
        "sku": "GULA-1KG", "name": "Gula Pasir 1 kg", "barcode": "",
        "category": "Sembako", "unit": "pcs",
        "buy_price": "12000", "sell_price": "17000", "min_stock": "5",
    }
    data.update(overrides)
    return data


def test_create_and_list_product(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    resp = client.post("/products/new", data=_product_data(), follow_redirects=True)
    assert resp.status_code == 200
    assert b"Gula Pasir" in resp.data
    assert b"17000" in resp.data
    # SKU duplikat ditolak dengan pesan, tanpa duplikasi.
    resp = client.post("/products/new", data=_product_data(), follow_redirects=True)
    assert b"sudah dipakai" in resp.data
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        rows = conn.execute("SELECT COUNT(*) n FROM products").fetchone()["n"]
        assert rows == 1
    finally:
        conn.close()


def test_cashier_cannot_manage_products(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client, username="kasir")
    assert client.get("/products/new").status_code == 403
    assert client.post("/products/new", data=_product_data()).status_code == 403
    assert client.get("/products/1/edit").status_code == 403
    assert client.get("/products/1/stock").status_code == 403
    # Kasir tetap bisa melihat daftar produk.
    assert client.get("/products").status_code == 200


def test_edit_and_archive_product(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    client.post("/products/new", data=_product_data(), follow_redirects=True)
    resp = client.post("/products/1/edit", data=_product_data(
        name="Gula Pasir Premium", sell_price="18000"), follow_redirects=True)
    assert b"Gula Pasir Premium" in resp.data
    assert b"18000" in resp.data
    # Arsipkan: produk hilang dari daftar default, muncul bila filter nonaktif.
    client.post("/products/1/archive", data={}, follow_redirects=True)
    assert b"Gula Pasir Premium" not in client.get("/products").data
    assert b"Gula Pasir Premium" in client.get(
        "/products?tampilkan_nonaktif=1").data
    client.post("/products/1/activate", data={}, follow_redirects=True)
    assert b"Gula Pasir Premium" in client.get("/products").data


def _stock_post(client, product_id, kind, qty, note=""):
    return client.post(f"/products/{product_id}/stock", data={
        "outlet_id": "1", "kind": kind, "qty_delta": str(qty), "note": note,
    }, follow_redirects=True)


def test_stock_adjustment_and_movements(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    client.post("/products/new", data=_product_data(), follow_redirects=True)
    # Outlet default dibuat otomatis (Outlet Utama, id 1).
    resp = _stock_post(client, 1, "opening_balance", 10, "Saldo awal")
    assert resp.status_code == 200
    assert b"Saldo awal" in resp.data
    resp = _stock_post(client, 1, "adjustment_out", 3, "Rusak")
    assert resp.status_code == 200
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_stock_qty(conn, 1, 1) == 7
        movements = list_stock_movements(conn, product_id=1)
        assert len(movements) == 2
        # Diurutkan terbaru dulu.
        assert [m["qty"] for m in movements] == [-3.0, 10.0]
        assert [m["kind"] for m in movements] == [
            "adjustment_out", "opening_balance"]
    finally:
        conn.close()


def test_opening_balance_only_once(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    client.post("/products/new", data=_product_data(), follow_redirects=True)
    assert _stock_post(client, 1, "opening_balance", 20, "Saldo awal").status_code == 200
    resp = _stock_post(client, 1, "opening_balance", 5, "Saldo awal lagi")
    assert b"sudah dicatat" in resp.data
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_stock_qty(conn, 1, 1) == 20
        assert len(list_stock_movements(conn, product_id=1)) == 1
        # Koreksi tetap bisa lewat penyesuaian biasa.
        _stock_post(client, 1, "adjustment_in", 2, "Koreksi")
        assert get_stock_qty(conn, 1, 1) == 22
    finally:
        conn.close()


def test_stock_cannot_go_negative(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    client.post("/products/new", data=_product_data(), follow_redirects=True)
    _stock_post(client, 1, "opening_balance", 5, "Saldo awal")
    resp = _stock_post(client, 1, "adjustment_out", 10, "Terlalu banyak")
    assert b"tidak boleh negatif" in resp.data
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_stock_qty(conn, 1, 1) == 5
        assert len(list_stock_movements(conn, product_id=1)) == 1
    finally:
        conn.close()


def test_empty_name_rejected_and_edit_keeps_sku_and_id(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    resp = client.post("/products/new", data=_product_data(name=""),
                       follow_redirects=True)
    assert b"Gula Pasir" not in resp.data
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert conn.execute("SELECT COUNT(*) n FROM products").fetchone()["n"] == 0
    finally:
        conn.close()
    client.post("/products/new", data=_product_data(), follow_redirects=True)
    # Edit dengan SKU yang sama diperbolehkan dan ID tidak berubah.
    resp = client.post("/products/1/edit", data=_product_data(
        name="Gula Pasir Premium"), follow_redirects=True)
    assert b"Gula Pasir Premium" in resp.data
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        row = conn.execute("SELECT * FROM products WHERE id = 1").fetchone()
        assert row["sku"] == "GULA-1KG" and row["name"] == "Gula Pasir Premium"
        # SKU produk lain tidak boleh dipakai saat edit.
        client.post("/products/new", data=_product_data(
            sku="KOPI-1", name="Kopi"), follow_redirects=True)
        resp = client.post("/products/2/edit", data=_product_data(
            sku="GULA-1KG", name="Kopi"), follow_redirects=True)
        assert b"sudah dipakai" in resp.data
    finally:
        conn.close()


def test_unit_change_blocked_when_stock_exists(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    client.post("/products/new", data=_product_data(), follow_redirects=True)
    _stock_post(client, 1, "opening_balance", 5, "Saldo awal")
    resp = client.post("/products/1/edit", data=_product_data(unit="dus"),
                       follow_redirects=True)
    assert b"Satuan dasar tidak dapat diubah" in resp.data
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert conn.execute(
            "SELECT u.name FROM products p JOIN units u ON u.id = p.unit_id"
            " WHERE p.id = 1").fetchone()[0] == "pcs"
    finally:
        conn.close()


def test_reconciliation_and_atomicity(tmp_path, monkeypatch):
    from iris_db import adjust_stock, get_default_outlet, reconcile_stock
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        from iris_db import create_product
        get_default_outlet(conn)  # outlet id 1, diperlukan FK tabel stock
        pid = create_product(conn, "GULA-1KG", "Gula Pasir 1 kg", sell_price=17000)
        adjust_stock(conn, pid, 1, 20, kind="opening_balance")
        adjust_stock(conn, pid, 1, 5, kind="adjustment_in")
        adjust_stock(conn, pid, 1, -3, kind="adjustment_out")
        stock_qty, total, consistent = reconcile_stock(conn, pid, 1)
        assert (stock_qty, total, consistent) == (22, 22, True)
        # Kegagalan saat menulis mutasi membatalkan pembaruan saldo:
        # trigger yang menggagalkan INSERT ke stock_movements.
        conn.execute(
            "CREATE TRIGGER fail_movement BEFORE INSERT ON stock_movements"
            " WHEN NEW.note = 'gagal-atomik'"
            " BEGIN SELECT RAISE(ABORT, 'boom'); END"
        )
        conn.commit()
        import pytest
        with pytest.raises(Exception):
            adjust_stock(conn, pid, 1, 10, note="gagal-atomik",
                         kind="adjustment_in")
        stock_qty, total, consistent = reconcile_stock(conn, pid, 1)
        assert (stock_qty, total, consistent) == (22, 22, True)
    finally:
        conn.close()


def test_sql_injection_treated_as_data(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    evil = "'; DROP TABLE products; --"
    resp = client.post("/products/new", data=_product_data(name=evil),
                       follow_redirects=True)
    assert resp.status_code == 200
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        rows = conn.execute("SELECT name FROM products").fetchall()
        assert [r["name"] for r in rows] == [evil]
    finally:
        conn.close()


def test_category_filter_and_low_stock_badge(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    client.post("/products/new", data=_product_data(), follow_redirects=True)
    client.post("/products/new", data=_product_data(
        sku="SABUN-1", name="Sabun", category="Perawatan", sell_price="5000"),
        follow_redirects=True)
    _stock_post(client, 1, "opening_balance", 3, "Saldo awal")
    html = client.get("/products").data.decode()
    assert "Rendah" in html  # stok 3 <= min_stock 5
    assert "Habis" in html  # sabun belum ada stok
    # Filter kategori Sembako hanya menampilkan gula.
    html = client.get("/products?kategori=1").data.decode()
    assert "Gula Pasir" in html and "Sabun" not in html


def test_csrf_post_without_token_rejected(tmp_path, monkeypatch):
    import re
    monkeypatch.setenv("IRIS_DATA_DIR", str(tmp_path))
    app = tenant_app.create_app()
    # CSRF aktif (default): WTF_CSRF_ENABLED tidak dimatikan di sini.
    app.config.update(DATA_DIR=str(tmp_path), TESTING=True)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        create_user(conn, "owner", "rahasia-123", "Pemilik", role="owner")
    finally:
        conn.close()
    client = app.test_client()

    def _token(html):
        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
        assert m, "token CSRF tidak ditemukan di form"
        return m.group(1)

    login_html = client.get("/login").data.decode()
    client.post("/login", data={
        "tenant": "toko-demo", "username": "owner", "password": "rahasia-123",
        "csrf_token": _token(login_html),
    })
    # POST tanpa token CSRF: validasi form gagal, produk tidak dibuat
    # (Flask-WTF tanpa CSRFProtect mengembalikan form, bukan 400;
    # nama produk tetap tampil di form yang dirender ulang, jadi
    # yang diperiksa adalah database, bukan HTML).
    resp = client.post("/products/new", data=_product_data(),
                       follow_redirects=True)
    assert resp.status_code == 200
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert conn.execute("SELECT COUNT(*) n FROM products").fetchone()["n"] == 0
    finally:
        conn.close()
    # POST dengan token valid berhasil.
    form_html = client.get("/products/new").data.decode()
    resp = client.post("/products/new", data={
        **_product_data(), "csrf_token": _token(form_html),
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Gula Pasir" in resp.data


def test_products_isolated_between_tenants(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    client.post("/products/new", data=_product_data(), follow_redirects=True)
    # Tenant lain: buat owner + login, daftar produknya kosong.
    conn = init_tenant_db("toko-lain", data_dir=str(tmp_path))
    try:
        create_user(conn, "owner", "rahasia-123", "Pemilik", role="owner")
    finally:
        conn.close()
    client.get("/logout")
    _login(client, tenant="toko-lain")
    assert b"Gula Pasir" not in client.get("/products").data
    assert client.get("/products/1/stock").status_code == 404
