"""Tes Laporan (P1 — Rencana Lanjutan, Langkah 1).

Laporan hanya membaca data transaksi yang sudah ada (tanpa migrasi).
Filter tanggal memakai kalender UTC half-open [dari, sampai+1 hari).
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from iris_db import (
    init_tenant_db,
    parse_report_range,
    report_purchases_summary,
    report_returns_rows,
    report_sales_summary,
    report_stock,
    report_voids_rows,
)
from test_checkout import _add, _checkout, _client, _login, _seed
from test_purchases import _purchase
from test_returns import _return


def _scenario(client, tmp_path):
    p1 = _seed(client, tmp_path, sku="GULA-1KG", name="Gula Pasir 1 kg",
               sell_price="17000", stock=10)
    p2 = _seed(client, tmp_path, sku="KOPI-100G", name="Kopi 100 g",
               sell_price="8000", stock=5)
    _add(client, p1, 5)
    _checkout(client, "cash", 85000)          # penjualan 1: 85000
    _add(client, p2, 3)
    _checkout(client, "cash", 24000)          # penjualan 2: 24000
    client.post("/sales/2/void", data={"reason": "Salah input"},
                follow_redirects=True)
    _add(client, p1, 2)
    _checkout(client, "cash", 34000)          # penjualan 3: 34000
    _return(client, "/sales/3/return", [(p1, 1)], reason="Pecah")
    _purchase(client, [(p1, 10, 12000)])      # pembelian: 120000
    _return(client, "/purchases/1/return", [(p1, 4)], reason="Kadaluarsa")
    return p1, p2


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def test_empty_reports(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    for url in ("/reports", "/reports/sales", "/reports/purchases",
                "/reports/stock", "/reports/returns"):
        resp = client.get(url)
        assert resp.status_code == 200, url
    html = client.get("/reports").data.decode()
    assert "Rp 0" in html
    assert "Tidak ada transaksi penjualan" in client.get(
        "/reports/sales").data.decode()
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        s, e = parse_report_range(_today(), _today())
        summary = report_sales_summary(conn, s, e)
        assert summary["kotor"] == 0 and summary["bersih"] == 0
        assert summary["n_aktif"] == 0 and summary["n_batal"] == 0
    finally:
        conn.close()


def test_sales_summary_math(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _scenario(client, tmp_path)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        s, e = parse_report_range(_today(), _today())
        summary = report_sales_summary(conn, s, e)
        # Aktif: 85000 + 34000 = 119000; retur 17000; bersih 102000.
        assert summary["kotor"] == 119000
        assert summary["retur"] == 17000
        assert summary["bersih"] == 102000
        # Batal 24000 terpisah, tidak masuk kotor.
        assert summary["batal"] == 24000
        assert summary["n_aktif"] == 2 and summary["n_batal"] == 1
        assert summary["n_retur"] == 1
        # Pembayaran tunai = paid transaksi aktif.
        assert summary["pembayaran"][0]["method"] == "cash"
        assert summary["pembayaran"][0]["paid"] == 119000
        # Rentang kemarin: kosong.
        from datetime import timedelta
        y = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        s2, e2 = parse_report_range(y, y)
        assert report_sales_summary(conn, s2, e2)["kotor"] == 0
    finally:
        conn.close()
    html = client.get("/reports").data.decode()
    assert "119000" in html and "102000" in html and "24000" in html
    html = client.get("/reports/sales").data.decode()
    assert "INV-" in html and "119000" in html


def test_purchases_summary_math(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _scenario(client, tmp_path)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        s, e = parse_report_range(_today(), _today())
        summary = report_purchases_summary(conn, s, e)
        assert summary["total"] == 120000
        assert summary["retur"] == 48000
        assert summary["bersih"] == 72000
        assert summary["n_aktif"] == 1
    finally:
        conn.close()


def test_stock_report_from_ledger(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    p1, p2 = _scenario(client, tmp_path)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        s, e = parse_report_range(_today(), _today())
        rows = {r["id"]: r for r in report_stock(conn, s, e)}
        # p1: stok 10 -5 -2 +1 (retur) +10 (beli) -4 (retur beli) = 10.
        assert rows[p1]["stock_qty"] == 10
        # Masuk: saldo awal 10 + retur jual 1 + beli 10 = 21.
        assert rows[p1]["masuk"] == 21
        # Keluar: jual 5+2 + retur beli 4 = 11.
        assert rows[p1]["keluar"] == 11
        # p2: stok 5 -3 +3 (void) = 5; masuk 5+3=8; keluar 3.
        assert rows[p2]["stock_qty"] == 5
        assert rows[p2]["masuk"] == 8 and rows[p2]["keluar"] == 3
    finally:
        conn.close()
    html = client.get("/reports/stock").data.decode()
    assert "Gula Pasir 1 kg" in html


def test_date_range_boundaries(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        conn.execute(
            "INSERT INTO outlets (id, name, slug) VALUES (1, 'Outlet Utama', 'outlet-utama')")
        conn.execute(
            "INSERT INTO sales (id, outlet_id, invoice_no, status, total, paid, created_at)"
            " VALUES (1, 1, 'INV-20261125-0001', 'completed', 10000, 10000, '2026-11-25 00:00:00')")
        conn.execute(
            "INSERT INTO sales (id, outlet_id, invoice_no, status, total, paid, created_at)"
            " VALUES (2, 1, 'INV-20261126-0001', 'completed', 20000, 20000, '2026-11-26 00:00:00')")
        conn.execute(
            "INSERT INTO sales (id, outlet_id, invoice_no, status, total, paid, created_at)"
            " VALUES (3, 1, 'INV-20261125-0002', 'completed', 5000, 5000, '2026-11-25 23:59:59')")
        conn.commit()
        s, e = parse_report_range("2026-11-25", "2026-11-25")
        summary = report_sales_summary(conn, s, e)
        # Batas awal inklusif (00:00:00 masuk), batas akhir eksklusif
        # (26 00:00:00 tidak masuk), akhir hari masuk.
        assert summary["kotor"] == 15000
        assert summary["n_aktif"] == 2
        s, e = parse_report_range("2026-11-25", "2026-11-26")
        assert report_sales_summary(conn, s, e)["kotor"] == 35000
    finally:
        conn.close()


def test_invalid_dates_ignored(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _scenario(client, tmp_path)
    resp = client.get("/reports/sales?dari=bogus&sampai=2026-13-40")
    assert resp.status_code == 200
    assert "INV-" in resp.data.decode()
    assert parse_report_range("bogus", "juga-bogus") == (None, None)


def test_returns_and_voids_report(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _scenario(client, tmp_path)
    conn = init_tenant_db("toko-demo", data_dir=str(tmp_path))
    try:
        s, e = parse_report_range(_today(), _today())
        rows = report_returns_rows(conn, s, e)
        assert len(rows) == 2
        voids = report_voids_rows(conn, s, e)
        assert len(voids["penjualan"]) == 1
        assert voids["penjualan"][0]["alasan"] == "Salah input"
        assert len(voids["pembelian"]) == 0
    finally:
        conn.close()
    html = client.get("/reports/returns").data.decode()
    assert "RS-" in html and "RP-" in html and "Salah input" in html


def test_reports_tenant_isolation_and_auth(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _scenario(client, tmp_path)
    from iris_db import create_user
    conn = init_tenant_db("toko-lain", data_dir=str(tmp_path))
    try:
        create_user(conn, "owner", "rahasia-123", "Pemilik", role="owner")
    finally:
        conn.close()
    _login(client, tenant="toko-lain")
    html = client.get("/reports").data.decode()
    assert "119000" not in html
    assert "Rp 0" in html
    assert client.get("/reports/sales/1").status_code == 404
    client.get("/logout", follow_redirects=True)
    assert client.get("/reports").status_code == 302
