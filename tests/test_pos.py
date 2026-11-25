"""Tes P1 tahap 2 — halaman kasir, keranjang, kalkulasi.

Tahap ini TIDAK mem-posting transaksi dan TIDAK mengubah stok/ledger:
semua tes keranjang menegaskan hal itu.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tenant_app
from iris_db import create_user, get_stock_qty, init_tenant_db


def _client(tmp_path, monkeypatch):
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


def _login(client, username="owner", tenant="toko-demo"):
    return client.post("/login", data={
        "tenant": tenant, "username": username, "password": "rahasia-123",
    }, follow_redirects=True)


def _seed_product(client, sku="GULA-1KG", name="Gula Pasir 1 kg", barcode="",
                  sell_price="17000", min_stock="5"):
    client.post("/products/new", data={
        "sku": sku, "name": name, "barcode": barcode, "category": "Sembako",
        "unit": "pcs", "buy_price": "12000", "sell_price": sell_price,
        "min_stock": min_stock,
    }, follow_redirects=True)


def _seed_with_stock(client, tmp_path, sku="GULA-1KG", name="Gula Pasir 1 kg",
                     barcode="", sell_price="17000", stock=10):
    _seed_product(client, sku=sku, name=name, barcode=barcode,
                  sell_price=sell_price)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        from iris_db import get_default_outlet, record_opening_balance
        outlet = get_default_outlet(conn)
        pid = conn.execute(
            "SELECT id FROM products WHERE sku = ?", (sku,)).fetchone()["id"]
        record_opening_balance(conn, pid, outlet["id"], stock)
        return pid
    finally:
        conn.close()


def _add(client, product_id, qty):
    return client.post("/pos/cart/add", data={
        "product_id": str(product_id), "qty": str(qty),
    }, follow_redirects=True)


def test_cashier_page_opens(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/pos").status_code == 302  # wajib login
    _login(client)
    resp = client.get("/pos")
    assert resp.status_code == 200
    assert b"Kasir" in resp.data
    assert b"Proses pembayaran" in resp.data


def test_search_by_name_sku_barcode(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _seed_with_stock(client, tmp_path, barcode="8991234567890")
    assert b"Gula Pasir" in client.get("/pos?q=Gula").data
    assert b"Gula Pasir" in client.get("/pos?q=GULA-1KG").data
    assert b"Gula Pasir" in client.get("/pos?q=8991234567890").data
    assert b"tidak ditemukan" in client.get("/pos?q=tidak-ada").data


def test_add_and_merge_same_product(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed_with_stock(client, tmp_path, stock=10)
    _add(client, pid, 2)
    resp = _add(client, pid, 3)
    assert b"Gula Pasir" in resp.data
    # Satu baris, kuantitas digabung: 5 x 17000 = 85000.
    assert resp.data.count(b"Gula Pasir") >= 1
    assert b"85000" in resp.data
    assert b"Total kuantitas: 5" in resp.data


def test_inactive_product_rejected(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed_with_stock(client, tmp_path, stock=10)
    client.post(f"/products/{pid}/archive", follow_redirects=True)
    resp = _add(client, pid, 1)
    assert b"nonaktif" in resp.data
    assert b"Keranjang masih kosong" in resp.data
    assert b"tidak ditemukan" in client.get("/pos?q=Gula").data


def test_qty_zero_or_negative_rejected(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed_with_stock(client, tmp_path, stock=10)
    resp = _add(client, pid, 0)
    assert b"lebih dari 0" in resp.data
    resp = _add(client, pid, -2)
    assert b"lebih dari 0" in resp.data
    assert b"Keranjang masih kosong" in client.get("/pos").data


def test_qty_exceeding_stock_rejected(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed_with_stock(client, tmp_path, stock=3)
    resp = _add(client, pid, 5)
    assert b"tidak cukup" in resp.data
    assert b"Keranjang masih kosong" in client.get("/pos").data
    _add(client, pid, 3)
    resp = _add(client, pid, 1)  # total 4 > stok 3
    assert b"tidak cukup" in resp.data
    assert b"Total kuantitas: 3" in client.get("/pos").data


def test_cart_math_two_products(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    p1 = _seed_with_stock(client, tmp_path, stock=10)
    p2 = _seed_with_stock(client, tmp_path, sku="KOPI-1", name="Kopi",
                          sell_price="8000", stock=10)
    _add(client, p1, 2)   # 34000
    resp = _add(client, p2, 3)  # 24000
    assert b"58000" in resp.data
    assert b"Total kuantitas: 5" in resp.data


def test_server_recalculates_price(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed_with_stock(client, tmp_path, stock=10)
    # Kirim harga palsu lewat browser — harus diabaikan.
    resp = client.post("/pos/cart/add", data={
        "product_id": str(pid), "qty": "2", "price": "1",
    }, follow_redirects=True)
    assert b"34000" in resp.data
    # Harga produk diubah di database -> total ikut berubah.
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        conn.execute("UPDATE products SET sell_price = 20000 WHERE id = ?", (pid,))
        conn.commit()
    finally:
        conn.close()
    assert b"40000" in client.get("/pos").data


def test_set_qty_remove_clear(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed_with_stock(client, tmp_path, stock=10)
    _add(client, pid, 2)
    resp = client.post("/pos/cart/set", data={
        "product_id": str(pid), "qty": "5",
    }, follow_redirects=True)
    assert b"85000" in resp.data
    resp = client.post("/pos/cart/set", data={
        "product_id": str(pid), "qty": "0",
    }, follow_redirects=True)
    assert b"Keranjang masih kosong" in resp.data
    _add(client, pid, 1)
    resp = client.post("/pos/cart/remove", data={
        "product_id": str(pid),
    }, follow_redirects=True)
    assert b"Keranjang masih kosong" in resp.data
    _add(client, pid, 1)
    resp = client.post("/pos/cart/clear", follow_redirects=True)
    assert b"Keranjang masih kosong" in resp.data


def test_cart_changes_do_not_touch_stock_or_ledger(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed_with_stock(client, tmp_path, stock=10)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        before_stock = get_stock_qty(conn, pid, 1)
        before_moves = conn.execute(
            "SELECT COUNT(*) n FROM stock_movements").fetchone()["n"]
        before_sales = conn.execute(
            "SELECT COUNT(*) n FROM sales").fetchone()["n"]
    finally:
        conn.close()
    _add(client, pid, 2)
    client.post("/pos/cart/set", data={"product_id": str(pid), "qty": "5"},
                follow_redirects=True)
    client.post("/pos/cart/remove", data={"product_id": str(pid)},
                follow_redirects=True)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_stock_qty(conn, pid, 1) == before_stock == 10
        assert conn.execute(
            "SELECT COUNT(*) n FROM stock_movements").fetchone()["n"] == before_moves
        assert conn.execute(
            "SELECT COUNT(*) n FROM sales").fetchone()["n"] == before_sales == 0
    finally:
        conn.close()


def test_tenant_isolation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed_with_stock(client, tmp_path, stock=10)
    # Tenant lain: produk tenant A tidak ditemukan / tidak bisa ditambah.
    conn = init_tenant_db("toko-lain", data_dir=str(tmp_path))
    try:
        create_user(conn, "owner", "rahasia-123", "Pemilik", role="owner")
    finally:
        conn.close()
    _login(client, tenant="toko-lain")
    assert b"tidak ditemukan" in client.get("/pos?q=Gula").data
    resp = _add(client, pid, 1)
    assert b"tidak ditemukan" in resp.data
    assert b"Keranjang masih kosong" in resp.data


def test_cashier_role_can_use_pos_but_not_manage_products(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client, username="kasir")
    assert client.get("/pos").status_code == 200
    # Produk dibuat owner dulu, lalu kasir menjualnya.
    _login(client)
    pid = _seed_with_stock(client, tmp_path, stock=10)
    _login(client, username="kasir")
    resp = _add(client, pid, 1)
    assert b"17000" in resp.data
    assert client.post("/products/new", data={}).status_code == 403


def test_csrf_cart_post_without_token_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("IRIS_DATA_DIR", str(tmp_path))
    app = tenant_app.create_app()
    app.config.update(DATA_DIR=str(tmp_path), TESTING=True)  # CSRF aktif
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
    # Seed lewat database langsung (form tambah produk butuh token CSRF).
    from iris_db import create_product, get_default_outlet, record_opening_balance
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        pid = create_product(conn, "GULA-1KG", "Gula Pasir 1 kg", sell_price=17000)
        record_opening_balance(conn, pid, get_default_outlet(conn)["id"], 10)
    finally:
        conn.close()
    # POST keranjang tanpa token: produk tidak masuk keranjang.
    resp = client.post("/pos/cart/add", data={
        "product_id": "1", "qty": "1",
    }, follow_redirects=True)
    assert b"Keranjang masih kosong" in resp.data
