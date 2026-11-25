"""Tes P1 Tahap 7 — retur penjualan & retur pembelian."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import tenant_app
from iris_db import (
    create_product,
    create_purchase,
    create_purchase_return,
    create_sale,
    create_sale_return,
    get_default_outlet,
    get_stock_qty,
    init_tenant_db,
    record_opening_balance,
    reconcile_stock,
)
from test_checkout import _add, _checkout, _client, _login, _seed
from test_purchases import _purchase


def _sell(client, tmp_path, pid, qty, price=17000):
    _add(client, pid, qty)
    _checkout(client, "cash", qty * price)


def _return(client, url, items, reason="Barang cacat", token=None):
    data = {
        "reason": reason, "notes": "",
        "product_id": [str(i[0]) for i in items],
        "qty": [str(i[1]) for i in items],
    }
    if token:
        data["idempotency_key"] = token
    return client.post(url, data=data, follow_redirects=True)


def _db(tmp_path):
    return init_tenant_db("toko-demo", data_dir=str(tmp_path))


def _ret(tmp_path, rid=1):
    conn = _db(tmp_path)
    try:
        row = conn.execute(
            "SELECT * FROM returns WHERE id = ?", (rid,)).fetchone()
        items = conn.execute(
            "SELECT * FROM return_items WHERE return_id = ?",
            (rid,)).fetchall()
        moves = conn.execute(
            "SELECT * FROM stock_movements ORDER BY id").fetchall()
        return row, items, moves
    finally:
        conn.close()


def _stock(tmp_path, pid):
    conn = _db(tmp_path)
    try:
        return get_stock_qty(conn, pid, 1)
    finally:
        conn.close()


def _sale_status(tmp_path, sid=1):
    conn = _db(tmp_path)
    try:
        return conn.execute(
            "SELECT status FROM sales WHERE id = ?", (sid,)).fetchone()["status"]
    finally:
        conn.close()


def test_sale_return_full(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _sell(client, tmp_path, pid, 5)
    assert _stock(tmp_path, pid) == 5
    resp = _return(client, "/sales/1/return", [(pid, 5)])
    assert b"tersimpan dan stok bertambah" in resp.data
    assert b"RS-" in resp.data
    row, items, moves = _ret(tmp_path)
    assert row["kind"] == "sale_return" and row["status"] == "completed"
    assert row["total"] == 85000 and row["sale_id"] == 1
    assert items[0]["product_name"] == "Gula Pasir 1 kg"
    assert items[0]["price"] == 17000
    assert _stock(tmp_path, pid) == 10
    rm = [m for m in moves if m["kind"] == "return"]
    assert len(rm) == 1 and rm[0]["qty"] == 5
    assert rm[0]["ref_type"] == "return" and rm[0]["ref_id"] == 1
    assert "INV-" in rm[0]["note"]
    assert _sale_status(tmp_path) == "returned"
    conn = _db(tmp_path)
    try:
        assert reconcile_stock(conn, pid, 1) == (10, 10, True)
        # Transaksi asal tidak berubah.
        assert conn.execute(
            "SELECT COUNT(*) n FROM sale_items WHERE sale_id = 1"
        ).fetchone()["n"] == 1
    finally:
        conn.close()


def test_sale_return_partial_and_cap(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _sell(client, tmp_path, pid, 5)
    resp = _return(client, "/sales/1/return", [(pid, 2)], reason="Pecah")
    assert b"tersimpan" in resp.data
    assert _stock(tmp_path, pid) == 7
    assert _sale_status(tmp_path) == "completed"
    # Produk yang tidak ada di transaksi asal ditolak.
    other = _seed(client, tmp_path, sku="KOPI-100G", name="Kopi 100 g",
                  sell_price="8000", stock=5)
    resp = _return(client, "/sales/1/return", [(other, 1)])
    assert b"tidak ada pada transaksi asal" in resp.data
    # Kuantitas 0 diabaikan -> tidak ada item.
    resp = _return(client, "/sales/1/return", [(pid, 0)])
    assert b"minimal satu item" in resp.data
    # Melebihi sisa (sudah diretur 2 dari 5, coba 4) ditolak.
    resp = _return(client, "/sales/1/return", [(pid, 4)])
    assert b"melebihi sisa" in resp.data
    assert _stock(tmp_path, pid) == 7
    resp = _return(client, "/sales/1/return", [(pid, 3)])
    assert b"tersimpan" in resp.data
    assert _sale_status(tmp_path) == "returned"
    assert _stock(tmp_path, pid) == 10


def test_sale_return_voided_sale_rejected(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _sell(client, tmp_path, pid, 2)
    client.post("/sales/1/void", data={"reason": "Salah input"},
                follow_redirects=True)
    resp = _return(client, "/sales/1/return", [(pid, 1)])
    assert b"sudah dibatalkan" in resp.data
    assert _stock(tmp_path, pid) == 10


def test_sale_return_historical_price_and_idempotency(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _sell(client, tmp_path, pid, 3)
    client.post(f"/products/{pid}/edit", data={
        "sku": "GULA-1KG", "name": "Gula Pasir BARU", "barcode": "",
        "category": "Sembako", "unit": "pcs", "buy_price": "12000",
        "sell_price": "99999", "min_stock": "5",
    }, follow_redirects=True)
    token = "tok-retur-1"
    resp = _return(client, "/sales/1/return", [(pid, 2)], token=token)
    assert b"tersimpan" in resp.data
    row, _, _ = _ret(tmp_path)
    assert row["total"] == 34000  # harga lama 17000, bukan 99999
    # Kirim ulang dengan token + data sama -> retur yang sama.
    resp = _return(client, "/sales/1/return", [(pid, 2)], token=token)
    assert b"tersimpan" in resp.data
    conn = _db(tmp_path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) n FROM returns").fetchone()["n"] == 1
    finally:
        conn.close()
    assert _stock(tmp_path, pid) == 9
    # Token sama + data beda -> ditolak.
    resp = _return(client, "/sales/1/return", [(pid, 1)], token=token)
    assert b"sudah dipakai" in resp.data


def test_sale_return_rollback(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _sell(client, tmp_path, pid, 2)
    conn = _db(tmp_path)
    try:
        conn.execute(
            "CREATE TRIGGER fail_ret BEFORE INSERT ON stock_movements"
            " WHEN NEW.kind = 'return'"
            " BEGIN SELECT RAISE(ABORT, 'boom'); END")
        conn.commit()
    finally:
        conn.close()
    _return(client, "/sales/1/return", [(pid, 1)])
    conn = _db(tmp_path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) n FROM returns").fetchone()["n"] == 0
    finally:
        conn.close()
    assert _stock(tmp_path, pid) == 8


def test_cancel_sale_return(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _sell(client, tmp_path, pid, 4)
    _return(client, "/sales/1/return", [(pid, 4)])
    assert _sale_status(tmp_path) == "returned"
    resp = client.post("/returns/1/cancel",
                       data={"reason": "Barang ternyata bagus"},
                       follow_redirects=True)
    assert b"dibatalkan" in resp.data
    row, _, moves = _ret(tmp_path)
    assert row["status"] == "cancelled"
    assert row["cancel_reason"] == "Barang ternyata bagus"
    assert _stock(tmp_path, pid) == 6
    voids = [m for m in moves if m["ref_type"] == "return_void"]
    assert len(voids) == 1 and voids[0]["qty"] == -4
    assert voids[0]["kind"] == "return"
    assert _sale_status(tmp_path) == "completed"
    # Pembatalan kedua ditolak.
    resp = client.post("/returns/1/cancel",
                       data={"reason": "lagi"}, follow_redirects=True)
    assert b"sudah dibatalkan" in resp.data


def test_cancel_sale_return_insufficient_stock(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _sell(client, tmp_path, pid, 5)
    _return(client, "/sales/1/return", [(pid, 5)])
    _sell(client, tmp_path, pid, 8)  # stok 10 -> 2
    resp = client.post("/returns/1/cancel",
                       data={"reason": "batal"}, follow_redirects=True)
    assert b"stok tidak mencukupi" in resp.data
    row, _, _ = _ret(tmp_path)
    assert row["status"] == "completed"


def test_void_blocked_after_return(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _sell(client, tmp_path, pid, 2)
    _return(client, "/sales/1/return", [(pid, 1)])
    resp = client.post("/sales/1/void", data={"reason": "batal"},
                       follow_redirects=True)
    assert b"sudah diretur" in resp.data
    assert _sale_status(tmp_path) == "completed"


def test_purchase_return_full_and_partial(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=0)
    _purchase(client, [(pid, 10, 12000)])
    assert _stock(tmp_path, pid) == 10
    resp = _return(client, "/purchases/1/return", [(pid, 4)],
                   reason="Kadaluarsa")
    assert b"tersimpan dan stok berkurang" in resp.data
    assert b"RP-" in resp.data
    row, items, moves = _ret(tmp_path)
    assert row["kind"] == "purchase_return" and row["total"] == 48000
    assert _stock(tmp_path, pid) == 6
    pm = [m for m in moves if m["kind"] == "purchase_return"]
    assert len(pm) == 1 and pm[0]["qty"] == -4
    conn = _db(tmp_path)
    try:
        assert conn.execute(
            "SELECT status FROM purchases WHERE id = 1"
        ).fetchone()["status"] == "received"
    finally:
        conn.close()
    resp = _return(client, "/purchases/1/return", [(pid, 7)])
    assert b"melebihi sisa" in resp.data
    resp = _return(client, "/purchases/1/return", [(pid, 6)])
    assert b"tersimpan" in resp.data
    conn = _db(tmp_path)
    try:
        assert conn.execute(
            "SELECT status FROM purchases WHERE id = 1"
        ).fetchone()["status"] == "returned"
    finally:
        conn.close()
    assert _stock(tmp_path, pid) == 0


def test_purchase_return_insufficient_stock_and_cancel(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=0)
    _purchase(client, [(pid, 10, 12000)])
    _sell(client, tmp_path, pid, 8)  # stok 10 -> 2
    resp = _return(client, "/purchases/1/return", [(pid, 5)])
    assert b"stok tidak mencukupi" in resp.data
    resp = _return(client, "/purchases/1/return", [(pid, 2)])
    assert b"tersimpan" in resp.data
    resp = client.post("/returns/1/cancel",
                       data={"reason": "Pemasok menolak"},
                       follow_redirects=True)
    assert b"dibatalkan" in resp.data
    row, _, moves = _ret(tmp_path)
    assert row["status"] == "cancelled"
    assert _stock(tmp_path, pid) == 2
    voids = [m for m in moves if m["ref_type"] == "return_void"]
    assert len(voids) == 1 and voids[0]["qty"] == 2
    assert voids[0]["kind"] == "purchase_return"
    conn = _db(tmp_path)
    try:
        assert conn.execute(
            "SELECT status FROM purchases WHERE id = 1"
        ).fetchone()["status"] == "received"
    finally:
        conn.close()


def test_purchase_return_cancelled_purchase_rejected(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=0)
    _purchase(client, [(pid, 4, 12000)])
    client.post("/purchases/1/cancel", data={"reason": "Salah PO"},
                follow_redirects=True)
    resp = _return(client, "/purchases/1/return", [(pid, 1)])
    assert b"tidak dapat diretur" in resp.data


def test_return_permissions_tenant_csrf(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _sell(client, tmp_path, pid, 2)
    _login(client, username="kasir")
    assert client.get("/sales/1/return").status_code == 403
    assert client.post("/sales/1/return",
                       data={"reason": "x", "product_id": [str(pid)],
                             "qty": ["1"]}).status_code == 403
    from iris_db import create_user
    conn = _db("toko-lain") if False else None
    conn = init_tenant_db("toko-lain", data_dir=str(tmp_path))
    try:
        create_user(conn, "owner", "rahasia-123", "Pemilik", role="owner")
    finally:
        conn.close()
    _login(client, tenant="toko-lain")
    assert client.post("/sales/1/return",
                       data={"reason": "x", "product_id": [str(pid)],
                             "qty": ["1"]}).status_code == 404


def test_return_csrf(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, csrf=True)
    login_html = client.get("/login").data.decode()
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', login_html)
    client.post("/login", data={
        "tenant": "toko-demo", "username": "owner", "password": "rahasia-123",
        "csrf_token": m.group(1),
    })
    conn = _db(tmp_path)
    try:
        pid = create_product(conn, "GULA-1KG", "Gula Pasir 1 kg", sell_price=17000)
        record_opening_balance(conn, pid, get_default_outlet(conn)["id"], 10)
        owner_id = conn.execute(
            "SELECT id FROM users WHERE username='owner'").fetchone()["id"]
        create_sale(conn, get_default_outlet(conn)["id"], owner_id,
                    [{"product_id": pid, "qty": 2}],
                    payment_method="cash", amount_tendered=34000,
                    idempotency_key="k1")
    finally:
        conn.close()
    client.post("/sales/1/return",
                data={"reason": "x", "product_id": [str(pid)], "qty": ["1"]},
                follow_redirects=True)
    conn = _db(tmp_path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) n FROM returns").fetchone()["n"] == 0
    finally:
        conn.close()


def test_return_history_and_detail(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=10)
    _sell(client, tmp_path, pid, 2)
    _return(client, "/sales/1/return", [(pid, 1)], reason="Pecah")
    html = client.get("/returns").data.decode()
    assert "RS-" in html and "Pecah" not in html  # alasan ada di detail
    html = client.get("/returns?jenis=purchase_return").data.decode()
    assert "RS-" not in html
    detail = client.get("/returns/1").data
    assert b"Pecah" in detail
    assert "Pengembalian uang".encode() in detail or b"belum diproses otomatis" in detail
    assert b"INV-" in detail
