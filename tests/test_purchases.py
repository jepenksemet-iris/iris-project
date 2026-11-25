"""Tes P1 Tahap 6 — pemasok & pembelian + penerimaan stok."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tenant_app
from iris_db import (
    create_user,
    get_stock_qty,
    init_tenant_db,
    reconcile_stock,
)
from test_checkout import _add, _checkout, _client, _login, _seed


def _supplier_id(client, tmp_path, name="PT Sembako Jaya"):
    client.post("/suppliers/new", data={
        "name": name, "phone": "0812", "address": "Jl. Raya 1",
        "notes": "Langganan",
    }, follow_redirects=True)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        return conn.execute(
            "SELECT id FROM suppliers WHERE name = ?", (name,)
        ).fetchone()["id"]
    finally:
        conn.close()


def _purchase(client, items, supplier_id=0, notes="", total="1"):
    """items: list (product_id, qty, price). total palsu diabaikan server."""
    data = {
        "supplier_id": str(supplier_id), "notes": notes, "total": total,
        "product_id": [str(i[0]) for i in items],
        "qty": [str(i[1]) for i in items],
        "price": [str(i[2]) for i in items],
    }
    return client.post("/purchases/new", data=data, follow_redirects=True)


def _purchase_row(tmp_path, purchase_id=1):
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        row = conn.execute(
            "SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
        items = conn.execute(
            "SELECT * FROM purchase_items WHERE purchase_id = ?",
            (purchase_id,)).fetchall()
        moves = conn.execute(
            "SELECT * FROM stock_movements ORDER BY id").fetchall()
        return row, items, moves
    finally:
        conn.close()


def _stock(tmp_path, pid):
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        return get_stock_qty(conn, pid, 1)
    finally:
        conn.close()


def test_supplier_crud(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    sid = _supplier_id(client, tmp_path)
    html = client.get("/suppliers").data.decode()
    assert "PT Sembako Jaya" in html and "0812" in html
    assert "Langganan" in html
    # Pencarian.
    assert "PT Sembako Jaya" in client.get("/suppliers?q=Sembako").data.decode()
    assert "PT Sembako Jaya" not in client.get("/suppliers?q=tidakada").data.decode()
    # Edit.
    resp = client.post(f"/suppliers/{sid}/edit", data={
        "name": "PT Sembako Baru", "phone": "0813", "address": "Jl. Baru",
        "notes": "",
    }, follow_redirects=True)
    assert b"diperbarui" in resp.data
    assert "PT Sembako Baru" in client.get("/suppliers").data.decode()
    # Arsip: hilang dari daftar, muncul dengan filter nonaktif.
    client.post(f"/suppliers/{sid}/archive", follow_redirects=True)
    assert "PT Sembako Baru" not in client.get("/suppliers").data.decode()
    assert "PT Sembako Baru" in client.get(
        "/suppliers?tampilkan_nonaktif=1").data.decode()
    client.post(f"/suppliers/{sid}/activate", follow_redirects=True)
    assert "PT Sembako Baru" in client.get("/suppliers").data.decode()
    # Nama kosong ditolak.
    resp = client.post("/suppliers/new", data={
        "name": "  ", "phone": "", "address": "", "notes": "",
    }, follow_redirects=True)
    assert b"This field is required" in resp.data
    # Kasir tidak boleh mengelola pemasok.
    _login(client, username="kasir")
    assert client.get("/suppliers/new").status_code == 403


def test_purchase_multi_item_atomic(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    sid = _supplier_id(client, tmp_path)
    p1 = _seed(client, tmp_path, sku="GULA-1KG", name="Gula Pasir 1 kg",
               sell_price="17000", stock=5)
    p2 = _seed(client, tmp_path, sku="KOPI-100G", name="Kopi 100 g",
               sell_price="8000", stock=0)
    resp = _purchase(client, [(p1, 2, 12000), (p2, 3, 5000)],
                     supplier_id=sid, notes="PO pertama")
    assert b"tersimpan dan stok bertambah" in resp.data
    assert b"PO-" in resp.data
    row, items, moves = _purchase_row(tmp_path)
    assert row["status"] == "received"
    assert row["supplier_id"] == sid and row["notes"] == "PO pertama"
    assert row["total"] == 39000  # 2*12000 + 3*5000, bukan total palsu "1"
    assert len(items) == 2
    assert items[0]["product_name"] == "Gula Pasir 1 kg"
    assert items[0]["sku"] == "GULA-1KG" and items[0]["price"] == 12000
    assert _stock(tmp_path, p1) == 7 and _stock(tmp_path, p2) == 3
    pmoves = [m for m in moves if m["kind"] == "purchase"]
    assert [(m["product_id"], m["qty"]) for m in pmoves] == [(p1, 2), (p2, 3)]
    assert all(m["ref_type"] == "purchase" and m["ref_id"] == 1 for m in pmoves)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        # Harga jual tidak berubah.
        assert conn.execute(
            "SELECT sell_price FROM products WHERE id = ?", (p1,)
        ).fetchone()["sell_price"] == 17000
        assert reconcile_stock(conn, p1, 1) == (7, 7, True)
    finally:
        conn.close()


def test_purchase_without_supplier_and_fractional(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, sku="BERAS-KG", name="Beras",
                sell_price="15000", stock=0)
    resp = _purchase(client, [(pid, 2.5, 10000)])
    assert b"tersimpan" in resp.data
    row, items, _ = _purchase_row(tmp_path)
    assert row["supplier_id"] is None
    assert row["total"] == 25000
    assert _stock(tmp_path, pid) == 2.5


def test_purchase_validation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=5)
    # Produk nonaktif.
    client.post(f"/products/{pid}/archive", follow_redirects=True)
    resp = _purchase(client, [(pid, 1, 10000)])
    assert b"nonaktif" in resp.data
    client.post(f"/products/{pid}/activate", follow_redirects=True)
    # Kuantitas 0 / negatif / harga negatif / produk tak dikenal / kosong.
    for items, needle in (
        ([(pid, 0, 10000)], b"lebih dari 0"),
        ([(pid, -1, 10000)], b"lebih dari 0"),
        ([(pid, 1, -100)], b"tidak boleh negatif"),
        ([(999, 1, 10000)], b"tidak ditemukan"),
    ):
        resp = _purchase(client, items)
        assert needle in resp.data, items
    resp = client.post("/purchases/new", data={
        "supplier_id": "0", "notes": "",
        "product_id": [""], "qty": ["1"], "price": ["1000"],
    }, follow_redirects=True)
    assert b"minimal satu item" in resp.data
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert conn.execute("SELECT COUNT(*) n FROM purchases").fetchone()["n"] == 0
    finally:
        conn.close()
    # Pemasok nonaktif tidak bisa dipilih di form (bukan pilihan) dan
    # ditolak di level service.
    sid = _supplier_id(client, tmp_path)
    client.post(f"/suppliers/{sid}/archive", follow_redirects=True)
    resp = _purchase(client, [(pid, 1, 10000)], supplier_id=sid)
    assert b"Not a valid choice" in resp.data
    from iris_db import create_purchase, get_default_outlet
    import pytest
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        with pytest.raises(ValueError, match="tidak aktif"):
            create_purchase(conn, get_default_outlet(conn)["id"], 1,
                            [{"product_id": pid, "qty": 1, "price": 10000}],
                            supplier_id=sid)
    finally:
        conn.close()


def test_purchase_rollback_on_ledger_failure(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=5)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        conn.execute(
            "CREATE TRIGGER fail_buy BEFORE INSERT ON stock_movements"
            " WHEN NEW.kind = 'purchase'"
            " BEGIN SELECT RAISE(ABORT, 'boom'); END")
        conn.commit()
    finally:
        conn.close()
    resp = _purchase(client, [(pid, 2, 10000)])
    assert resp.status_code == 200
    row, items, moves = _purchase_row(tmp_path)
    assert row is None and not items
    assert not [m for m in moves if m["kind"] == "purchase"]
    assert _stock(tmp_path, pid) == 5


def test_cancel_purchase_restores_stock(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=5)
    _purchase(client, [(pid, 4, 10000)])
    assert _stock(tmp_path, pid) == 9
    resp = client.post("/purchases/1/cancel",
                       data={"reason": "Barang cacat"},
                       follow_redirects=True)
    assert b"dibatalkan" in resp.data
    row, _, moves = _purchase_row(tmp_path)
    assert row["status"] == "cancelled"
    assert row["cancel_reason"] == "Barang cacat"
    assert row["cancelled_by"] is not None and row["cancelled_at"]
    assert _stock(tmp_path, pid) == 5
    voids = [m for m in moves if m["kind"] == "purchase_void"]
    assert len(voids) == 1 and voids[0]["qty"] == -4
    assert voids[0]["ref_type"] == "purchase_void" and voids[0]["ref_id"] == 1
    assert len([m for m in moves if m["kind"] == "purchase"]) == 1
    # Pembatalan kedua ditolak.
    resp = client.post("/purchases/1/cancel",
                       data={"reason": "lagi"}, follow_redirects=True)
    assert b"sudah dibatalkan" in resp.data
    assert _stock(tmp_path, pid) == 5


def test_cancel_purchase_insufficient_stock(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=0)
    _purchase(client, [(pid, 10, 10000)])
    _add(client, pid, 8)
    _checkout(client, "cash", 136000)
    assert _stock(tmp_path, pid) == 2
    resp = client.post("/purchases/1/cancel",
                       data={"reason": "batal"}, follow_redirects=True)
    assert b"stok tidak mencukupi" in resp.data
    row, _, _ = _purchase_row(tmp_path)
    assert row["status"] == "received"
    assert _stock(tmp_path, pid) == 2


def test_cancel_purchase_permissions_and_tenant(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _seed(client, tmp_path, stock=5)
    _purchase(client, [(pid, 2, 10000)])
    _login(client, username="kasir")
    assert client.post("/purchases/1/cancel",
                       data={"reason": "coba"}).status_code == 403
    conn = init_tenant_db("toko-lain", data_dir=str(tmp_path))
    try:
        create_user(conn, "owner", "rahasia-123", "Pemilik", role="owner")
    finally:
        conn.close()
    _login(client, tenant="toko-lain")
    assert client.post("/purchases/1/cancel",
                       data={"reason": "coba"}).status_code == 404
    row, _, _ = _purchase_row(tmp_path)
    assert row["status"] == "received"


def test_cancel_purchase_csrf(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, csrf=True)
    login_html = client.get("/login").data.decode()
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', login_html)
    client.post("/login", data={
        "tenant": "toko-demo", "username": "owner", "password": "rahasia-123",
        "csrf_token": m.group(1),
    })
    from iris_db import create_product, create_purchase, get_default_outlet, record_opening_balance
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        pid = create_product(conn, "GULA-1KG", "Gula Pasir 1 kg", sell_price=17000)
        record_opening_balance(conn, pid, get_default_outlet(conn)["id"], 5)
        owner_id = conn.execute(
            "SELECT id FROM users WHERE username='owner'").fetchone()["id"]
        create_purchase(conn, get_default_outlet(conn)["id"], owner_id,
                        [{"product_id": pid, "qty": 2, "price": 10000}])
    finally:
        conn.close()
    client.post("/purchases/1/cancel", data={"reason": "batal"},
                follow_redirects=True)
    row, _, _ = _purchase_row(tmp_path)
    assert row["status"] == "received"


def test_purchase_snapshot_and_history(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    sid = _supplier_id(client, tmp_path)
    pid = _seed(client, tmp_path, stock=5)
    _purchase(client, [(pid, 2, 12000)], supplier_id=sid)
    client.post(f"/products/{pid}/edit", data={
        "sku": "GULA-1KG", "name": "Gula Pasir BARU", "barcode": "",
        "category": "Sembako", "unit": "pcs", "buy_price": "12000",
        "sell_price": "99999", "min_stock": "5",
    }, follow_redirects=True)
    detail = client.get("/purchases/1").data
    assert b"Gula Pasir 1 kg" in detail and b"12000" in detail
    html = client.get("/purchases").data.decode()
    assert "PO-" in html and "24000" in html
    html = client.get("/purchases?pemasok=" + str(sid)).data.decode()
    assert "PO-" in html
    html = client.get("/purchases?status=cancelled").data.decode()
    assert "PO-" not in html
    html = client.get("/purchases?status=bogus").data.decode()
    assert "PO-" in html  # filter tidak valid diabaikan
    assert client.get("/purchases/new").status_code == 200
