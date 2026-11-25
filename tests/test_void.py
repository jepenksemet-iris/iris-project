"""Tes P1 Tahap 4 & 5 — audit ledger multi-item + pembatalan penjualan."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tenant_app
from iris_db import (
    create_user,
    get_stock_qty,
    get_tenant_db,
    init_tenant_db,
    reconcile_stock,
)
from test_checkout import _add, _checkout, _client, _login, _seed


def _stock(tmp_path, pid):
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        return get_stock_qty(conn, pid, 1)
    finally:
        conn.close()


def _sale(tmp_path, sale_id=1):
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        sale = conn.execute(
            "SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
        moves = conn.execute(
            "SELECT * FROM stock_movements ORDER BY id").fetchall()
        return sale, moves
    finally:
        conn.close()


def _make_sale(client, tmp_path, method="cash", amount=None):
    pid = _seed(client, tmp_path, stock=10)
    _add(client, pid, 2)
    _checkout(client, method, amount if amount is not None else 34000)
    return pid


def test_multi_item_checkout_ledger_matches_items(tmp_path, monkeypatch):
    """Tahap 4: checkout 2 produk -> 2 mutasi sale, kuantitas cocok,
    saldo = jumlah ledger."""
    client = _client(tmp_path, monkeypatch)
    _login(client)
    p1 = _seed(client, tmp_path, sku="GULA-1KG", name="Gula Pasir 1 kg",
               sell_price="17000", stock=10)
    p2 = _seed(client, tmp_path, sku="KOPI-100G", name="Kopi 100 g",
               sell_price="8000", stock=5)
    _add(client, p1, 2)
    _add(client, p2, 3)
    _checkout(client, "cash", 58000)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        moves = conn.execute(
            "SELECT * FROM stock_movements WHERE kind = 'sale'"
            " ORDER BY product_id").fetchall()
        assert [(m["product_id"], m["qty"]) for m in moves] == [(p1, -2), (p2, -3)]
        assert all(m["ref_type"] == "sale" and m["ref_id"] == 1 for m in moves)
        assert reconcile_stock(conn, p1, 1) == (8, 8, True)
        assert reconcile_stock(conn, p2, 1) == (2, 2, True)
    finally:
        conn.close()


def test_void_completed_restores_stock(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _make_sale(client, tmp_path)
    assert _stock(tmp_path, pid) == 8
    resp = client.post("/sales/1/void", data={"reason": "Pelanggan batal beli"},
                       follow_redirects=True)
    assert b"dibatalkan" in resp.data
    sale, moves = _sale(tmp_path)
    assert sale["status"] == "void"
    assert sale["void_reason"] == "Pelanggan batal beli"
    assert sale["voided_by"] is not None and sale["voided_at"]
    assert _stock(tmp_path, pid) == 10
    voids = [m for m in moves if m["kind"] == "sale_void"]
    assert len(voids) == 1 and voids[0]["qty"] == 2
    assert voids[0]["ref_type"] == "sale_void" and voids[0]["ref_id"] == 1
    sales = [m for m in moves if m["kind"] == "sale"]
    assert len(sales) == 1 and sales[0]["qty"] == -2  # mutasi asli tetap ada
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        assert conn.execute(
            "SELECT COUNT(*) n FROM sale_payments WHERE sale_id = 1"
        ).fetchone()["n"] == 1  # pembayaran asli tetap tercatat
        assert sale["paid"] == 34000  # bukan refund otomatis
        assert reconcile_stock(conn, pid, 1) == (10, 10, True)
    finally:
        conn.close()
    assert b"DIBATALKAN" in client.get("/sales/1/receipt").data
    assert b"Pelanggan batal beli" in client.get("/sales/1").data


def test_void_pending_non_cash(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _make_sale(client, tmp_path, method="qris")
    assert _stock(tmp_path, pid) == 8
    client.post("/sales/1/void", data={"reason": "QRIS gagal"},
                follow_redirects=True)
    sale, _ = _sale(tmp_path)
    assert sale["status"] == "void"
    assert _stock(tmp_path, pid) == 10


def test_void_requires_reason(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _make_sale(client, tmp_path)
    resp = client.post("/sales/1/void", data={"reason": "  "},
                       follow_redirects=True)
    assert b"wajib diisi" in resp.data
    sale, _ = _sale(tmp_path)
    assert sale["status"] == "completed"
    assert _stock(tmp_path, pid) == 8


def test_void_cashier_forbidden(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _make_sale(client, tmp_path)
    _login(client, username="kasir")
    assert client.post("/sales/1/void",
                       data={"reason": "coba"}).status_code == 403
    sale, _ = _sale(tmp_path)
    assert sale["status"] == "completed"


def test_double_void_no_double_stock(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _make_sale(client, tmp_path)
    client.post("/sales/1/void", data={"reason": "batal"},
                follow_redirects=True)
    resp = client.post("/sales/1/void", data={"reason": "batal lagi"},
                       follow_redirects=True)
    assert b"sudah dibatalkan" in resp.data
    assert _stock(tmp_path, pid) == 10
    _, moves = _sale(tmp_path)
    assert len([m for m in moves if m["kind"] == "sale_void"]) == 1


def test_void_rollback_on_ledger_failure(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _make_sale(client, tmp_path)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        conn.execute(
            "CREATE TRIGGER fail_void BEFORE INSERT ON stock_movements"
            " WHEN NEW.kind = 'sale_void'"
            " BEGIN SELECT RAISE(ABORT, 'boom'); END")
        conn.commit()
    finally:
        conn.close()
    resp = client.post("/sales/1/void", data={"reason": "batal"},
                       follow_redirects=True)
    assert resp.status_code == 200
    sale, moves = _sale(tmp_path)
    assert sale["status"] == "completed"
    assert _stock(tmp_path, pid) == 8
    assert not [m for m in moves if m["kind"] == "sale_void"]


def test_void_after_product_archived(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    pid = _make_sale(client, tmp_path)
    client.post(f"/products/{pid}/archive", follow_redirects=True)
    client.post("/sales/1/void", data={"reason": "batal"},
                follow_redirects=True)
    sale, _ = _sale(tmp_path)
    assert sale["status"] == "void"
    assert _stock(tmp_path, pid) == 10


def test_void_other_tenant_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _make_sale(client, tmp_path)
    conn = init_tenant_db("toko-lain", data_dir=str(tmp_path))
    try:
        create_user(conn, "owner", "rahasia-123", "Pemilik", role="owner")
    finally:
        conn.close()
    _login(client, tenant="toko-lain")
    resp = client.post("/sales/1/void", data={"reason": "batal"})
    assert resp.status_code == 404
    sale, _ = _sale(tmp_path)
    assert sale["status"] == "completed"


def test_void_csrf_without_token_rejected(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, csrf=True)
    login_html = client.get("/login").data.decode()
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', login_html)
    client.post("/login", data={
        "tenant": "toko-demo", "username": "owner", "password": "rahasia-123",
        "csrf_token": m.group(1),
    })
    from iris_db import create_product, create_sale, get_default_outlet, record_opening_balance
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        pid = create_product(conn, "GULA-1KG", "Gula Pasir 1 kg", sell_price=17000)
        record_opening_balance(conn, pid, get_default_outlet(conn)["id"], 10)
        owner_id = conn.execute(
            "SELECT id FROM users WHERE username='owner'").fetchone()["id"]
        create_sale(conn, get_default_outlet(conn)["id"], owner_id,
                    [{"product_id": pid, "qty": 1}], "cash",
                    amount_tendered=17000, idempotency_key="tok-csrf-void")
    finally:
        conn.close()
    resp = client.post("/sales/1/void", data={"reason": "batal"},
                       follow_redirects=True)
    sale, _ = _sale(tmp_path)
    assert sale["status"] == "completed"
    assert _stock(tmp_path, pid) == 9


def test_history_filters(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _make_sale(client, tmp_path)  # tunai, completed
    pid = _seed(client, tmp_path, sku="KOPI-100G", name="Kopi 100 g",
                sell_price="8000", stock=5)
    _add(client, pid, 1)
    _checkout(client, "qris")  # pending
    client.post("/sales/1/void", data={"reason": "batal"},
                follow_redirects=True)
    html = client.get("/sales?metode=qris").data.decode()
    assert "INV-" in html and html.count("INV-") == 1
    html = client.get("/sales?status=void").data.decode()
    assert html.count("INV-") == 1
    html = client.get("/sales?status=completed").data.decode()
    assert "INV-" not in html  # sale 1 void, sale 2 pending
    # Filter tidak valid diabaikan: semua transaksi tampil, tanpa crash.
    html = client.get("/sales?status=bogus&dari=bukan-tanggal&urut=ngaco").data.decode()
    assert html.count("INV-") == 2
    # Urut terlama: invoice pertama muncul lebih dulu.
    html = client.get("/sales?urut=oldest").data.decode()
    assert html.index("INV-") < html.rindex("INV-")


def test_history_empty_state(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    assert b"Belum ada transaksi penjualan" in client.get("/sales").data
