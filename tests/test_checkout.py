"""Tes P1 Tahap 3 — checkout atomik, pembayaran, idempotensi, riwayat."""
import re
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tenant_app
from iris_db import (
    create_user,
    get_stock_qty,
    get_tenant_db,
    init_tenant_db,
)


def _client(tmp_path, monkeypatch, csrf=False):
    monkeypatch.setenv("IRIS_DATA_DIR", str(tmp_path))
    app = tenant_app.create_app()
    app.config.update(DATA_DIR=str(tmp_path), TESTING=True,
                      WTF_CSRF_ENABLED=csrf)
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


def _seed(client, tmp_path, sku="GULA-1KG", name="Gula Pasir 1 kg",
          sell_price="17000", stock=10):
    client.post("/products/new", data={
        "sku": sku, "name": name, "barcode": "", "category": "Sembako",
        "unit": "pcs", "buy_price": "12000", "sell_price": sell_price,
        "min_stock": "5",
    }, follow_redirects=True)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        from iris_db import get_default_outlet, record_opening_balance
        pid = conn.execute(
            "SELECT id FROM products WHERE sku = ?", (sku,)).fetchone()["id"]
        record_opening_balance(conn, pid, get_default_outlet(conn)["id"], stock)
        return pid
    finally:
        conn.close()


def _add(client, product_id, qty):
    return client.post("/pos/cart/add", data={
        "product_id": str(product_id), "qty": str(qty),
    }, follow_redirects=True)


def _token(client):
    html = client.get("/pos").data.decode()
    m = re.search(r'name="idempotency_key"[^>]*value="([^"]+)"', html)
    assert m, "token idempotensi tidak ditemukan di halaman kasir"
    return m.group(1)


def _checkout(client, method="cash", amount=None, ref="", token=None):
    token = token or _token(client)
    data = {"payment_method": method, "payment_ref": ref,
            "idempotency_key": token}
    if amount is not None:
        data["amount_tendered"] = str(amount)
    return client.post("/pos/checkout", data=data, follow_redirects=True)


def _sale_row(tmp_path, sale_id=1):
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        sale = conn.execute(
            "SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
        items = conn.execute(
            "SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,)).fetchall()
        payments = conn.execute(
            "SELECT * FROM sale_payments WHERE sale_id = ?", (sale_id,)).fetchall()
        moves = conn.execute(
            "SELECT * FROM stock_movements WHERE kind = 'sale'").fetchall()
        return sale, items, payments, moves
    finally:
        conn.close()


def test_cash_exact_payment(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _add(client, pid, 2)
    resp = _checkout(client, "cash", 34000)
    assert b"berhasil" in resp.data
    assert b"INV-" in resp.data
    sale, items, payments, moves = _sale_row(tmp_path)
    assert sale["status"] == "completed" and sale["total"] == 34000
    assert sale["paid"] == 34000 and sale["change_amount"] == 0
    assert len(items) == 1
    assert items[0]["product_name"] == "Gula Pasir 1 kg"
    assert items[0]["sku"] == "GULA-1KG" and items[0]["unit"] == "pcs"
    assert items[0]["qty"] == 2 and items[0]["price"] == 17000
    assert payments[0]["amount"] == 34000 and payments[0]["payment_method"] == "cash"
    assert len(moves) == 1 and moves[0]["qty"] == -2
    assert moves[0]["ref_type"] == "sale" and moves[0]["ref_id"] == sale["id"]
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_stock_qty(conn, pid, 1) == 8
    finally:
        conn.close()
    assert b"Keranjang masih kosong" in client.get("/pos").data


def test_cash_overpayment_change(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _add(client, pid, 2)
    resp = _checkout(client, "cash", 50000)
    assert b"Kembalian: Rp 16000" in resp.data
    sale, _, payments, _ = _sale_row(tmp_path)
    assert sale["change_amount"] == 16000 and payments[0]["amount"] == 50000


def test_cash_underpayment_rejected(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _add(client, pid, 2)
    resp = _checkout(client, "cash", 10000)
    assert b"kurang dari total" in resp.data
    sale, _, _, _ = _sale_row(tmp_path, sale_id=1)
    assert sale is None
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_stock_qty(conn, pid, 1) == 10
    finally:
        conn.close()


def test_non_cash_pending_and_confirm(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _add(client, pid, 1)
    resp = _checkout(client, "qris", ref="QRIS-REF-1")
    assert b"pending" in resp.data
    sale, _, payments, moves = _sale_row(tmp_path)
    assert sale["status"] == "pending" and sale["paid"] == 0
    assert payments[0]["amount"] == 17000
    assert payments[0]["reference_number"] == "QRIS-REF-1"
    assert len(moves) == 1  # stok tetap berkurang (barang diserahkan)
    # Kasir tidak boleh mengonfirmasi.
    _login(client, username="kasir")
    assert client.post("/sales/1/confirm-payment").status_code == 403
    # Owner mengonfirmasi.
    _login(client)
    resp = client.post("/sales/1/confirm-payment", follow_redirects=True)
    assert b"dikonfirmasi" in resp.data
    sale, _, _, _ = _sale_row(tmp_path)
    assert sale["status"] == "completed" and sale["paid"] == 17000
    # Konfirmasi kedua ditolak.
    resp = client.post("/sales/1/confirm-payment", follow_redirects=True)
    assert b"hanya transaksi pending" in resp.data


def test_snapshot_survives_product_edit(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _add(client, pid, 1)
    _checkout(client, "cash", 17000)
    client.post(f"/products/{pid}/edit", data={
        "sku": "GULA-1KG", "name": "Gula Pasir BARU", "barcode": "",
        "category": "Sembako", "unit": "pcs", "buy_price": "12000",
        "sell_price": "99999", "min_stock": "5",
    }, follow_redirects=True)
    _, items, _, _ = _sale_row(tmp_path)
    assert items[0]["product_name"] == "Gula Pasir 1 kg"
    assert items[0]["price"] == 17000
    assert b"Gula Pasir 1 kg" in client.get("/sales/1").data


def test_invoice_numbers_unique(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _add(client, pid, 1)
    _checkout(client, "cash", 17000)
    _add(client, pid, 1)
    _checkout(client, "cash", 17000)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        nos = [r[0] for r in conn.execute(
            "SELECT invoice_no FROM sales ORDER BY id")]
    finally:
        conn.close()
    assert len(set(nos)) == 2
    assert all(re.match(r"INV-\d{8}-\d{4}$", n) for n in nos)


def test_idempotency_same_token_once(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _add(client, pid, 1)
    token = _token(client)
    _checkout(client, "cash", 17000, token=token)
    resp = _checkout(client, "cash", 17000, token=token)
    assert b"sudah pernah diproses" in resp.data
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert conn.execute("SELECT COUNT(*) n FROM sales").fetchone()["n"] == 1
        assert get_stock_qty(conn, pid, 1) == 9
    finally:
        conn.close()


def test_idempotency_same_token_different_payload_rejected(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _add(client, pid, 1)
    token = _token(client)
    _checkout(client, "cash", 17000, token=token)
    _add(client, pid, 2)  # keranjang berbeda, token sama
    resp = _checkout(client, "cash", 34000, token=token)
    assert b"token idempotensi sudah dipakai" in resp.data
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert conn.execute("SELECT COUNT(*) n FROM sales").fetchone()["n"] == 1
    finally:
        conn.close()


def test_checkout_validation_failures(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    # Keranjang kosong.
    resp = _checkout(client, "cash", 0)
    assert b"Keranjang kosong" in resp.data
    # Produk nonaktif setelah masuk keranjang.
    _add(client, pid, 1)
    client.post(f"/products/{pid}/archive", follow_redirects=True)
    resp = _checkout(client, "cash", 17000)
    assert b"nonaktif" in resp.data
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert conn.execute("SELECT COUNT(*) n FROM sales").fetchone()["n"] == 0
    finally:
        conn.close()
    # Kuantitas pecahan ditolak saat checkout.
    client.post(f"/products/{pid}/activate", follow_redirects=True)
    with client.session_transaction() as sess:
        sess["pos_cart"] = {"tenant": "toko-demo",
                            "items": [{"product_id": pid, "qty": 1.5}]}
    resp = _checkout(client, "cash", 25500)
    assert b"bilangan bulat" in resp.data
    # Produk tidak dikenal.
    with client.session_transaction() as sess:
        sess["pos_cart"] = {"tenant": "toko-demo",
                            "items": [{"product_id": 999, "qty": 1}]}
    resp = _checkout(client, "cash", 1000)
    assert b"tidak ditemukan" in resp.data
    # Metode tidak dikenal: form menolak pilihan itu (tidak ada penjualan).
    with client.session_transaction() as sess:
        sess["pos_cart"] = {"tenant": "toko-demo",
                            "items": [{"product_id": pid, "qty": 1}]}
    resp = _checkout(client, "bitcoin", 17000)
    assert b"Not a valid choice" in resp.data
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert conn.execute("SELECT COUNT(*) n FROM sales").fetchone()["n"] == 0
        # Validasi yang sama di level service, dengan pesan yang jelas.
        from iris_db import create_sale, get_default_outlet
        import pytest
        with pytest.raises(ValueError, match="tidak dikenal"):
            create_sale(conn, get_default_outlet(conn)["id"], 1,
                        [{"product_id": pid, "qty": 1}], "bitcoin",
                        amount_tendered=17000, idempotency_key="tok-x")
    finally:
        conn.close()


def test_rollback_on_ledger_failure(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _add(client, pid, 1)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        conn.execute(
            "CREATE TRIGGER fail_sale BEFORE INSERT ON stock_movements"
            " WHEN NEW.kind = 'sale'"
            " BEGIN SELECT RAISE(ABORT, 'boom'); END")
        conn.commit()
    finally:
        conn.close()
    resp = _checkout(client, "cash", 17000)
    assert resp.status_code == 200  # ditangani sebagai error, bukan 500
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert conn.execute("SELECT COUNT(*) n FROM sales").fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) n FROM sale_payments").fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) n FROM stock_movements WHERE kind='sale'"
        ).fetchone()["n"] == 0
        assert get_stock_qty(conn, pid, 1) == 10
    finally:
        conn.close()


def test_concurrent_last_stock(tmp_path, monkeypatch):
    from iris_db import create_product, create_sale, get_default_outlet
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        create_user(conn, "owner", "rahasia-123", "Pemilik", role="owner")
        from iris_db import record_opening_balance
        pid = create_product(conn, "GULA-1KG", "Gula Pasir 1 kg", sell_price=17000)
        outlet_id = get_default_outlet(conn)["id"]
        record_opening_balance(conn, pid, outlet_id, 1)
        owner_id = conn.execute(
            "SELECT id FROM users WHERE username='owner'").fetchone()["id"]
    finally:
        conn.close()
    results = {}

    def run(key, slot):
        c = get_tenant_db("toko-demo", data_dir=str(tmp_path))
        try:
            sale_id, _ = create_sale(
                c, outlet_id, owner_id,
                [{"product_id": pid, "qty": 1}], "cash",
                amount_tendered=17000, idempotency_key=key)
            results[slot] = ("ok", sale_id)
        except Exception as exc:  # noqa: BLE001 - hasil dicatat untuk asersi
            results[slot] = ("error", str(exc))
        finally:
            c.close()

    t1 = threading.Thread(target=run, args=("tok-1", "a"))
    t2 = threading.Thread(target=run, args=("tok-2", "b"))
    t1.start(); t2.start(); t1.join(); t2.join()
    oks = [v for v in results.values() if v[0] == "ok"]
    assert len(oks) == 1
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert get_stock_qty(conn, pid, 1) == 0
        assert conn.execute("SELECT COUNT(*) n FROM sales").fetchone()["n"] == 1
    finally:
        conn.close()


def test_history_list_detail_receipt(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _add(client, pid, 2)
    _checkout(client, "cash", 34000)
    html = client.get("/sales").data.decode()
    assert "INV-" in html and "34000" in html
    html = client.get("/sales?q=INV-").data.decode()
    assert "INV-" in html
    detail = client.get("/sales/1").data
    assert b"Gula Pasir 1 kg" in detail and b"34000" in detail
    receipt = client.get("/sales/1/receipt").data
    assert b"POS IRIS" in receipt and b"Cetak struk" in receipt


def test_tenant_isolation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _add(client, pid, 1)
    _checkout(client, "cash", 17000)
    conn = init_tenant_db("toko-lain", data_dir=str(tmp_path))
    try:
        create_user(conn, "owner", "rahasia-123", "Pemilik", role="owner")
    finally:
        conn.close()
    _login(client, tenant="toko-lain")
    assert client.get("/sales/1").status_code == 404
    assert client.get("/sales").status_code == 200
    assert b"INV-" not in client.get("/sales").data


def test_csrf_checkout_without_token_rejected(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, csrf=True)
    login_html = client.get("/login").data.decode()
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', login_html)
    client.post("/login", data={
        "tenant": "toko-demo", "username": "owner", "password": "rahasia-123",
        "csrf_token": m.group(1),
    })
    from iris_db import create_product, get_default_outlet, record_opening_balance
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        pid = create_product(conn, "GULA-1KG", "Gula Pasir 1 kg", sell_price=17000)
        record_opening_balance(conn, pid, get_default_outlet(conn)["id"], 10)
    finally:
        conn.close()
    with client.session_transaction() as sess:
        sess["pos_cart"] = {"tenant": "toko-demo",
                            "items": [{"product_id": pid, "qty": 1}]}
    # Tanpa token CSRF: checkout ditolak, tidak ada penjualan.
    resp = client.post("/pos/checkout", data={
        "payment_method": "cash", "amount_tendered": "17000",
        "idempotency_key": "tok-csrf",
    }, follow_redirects=True)
    assert b"INV-" not in resp.data
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert conn.execute("SELECT COUNT(*) n FROM sales").fetchone()["n"] == 0
    finally:
        conn.close()
