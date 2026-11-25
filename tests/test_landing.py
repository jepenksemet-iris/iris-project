"""Tes landing page tahap 4: semua section, harga, WhatsApp, FAQ.

Tidak mengklaim trial aktif (belum aktif) dan tidak mengklaim kuota
paket (menyusul) — tes memastikan klaim itu TIDAK muncul.
"""
from landing_app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_index_has_all_sections(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode()
    for anchor in ("#fitur", "#solusi", "#cara-kerja", "#harga", "#faq"):
        assert anchor in html
    for heading in (
        "Kelola Toko Lebih Mudah",
        "Masalah yang diselesaikan",
        "Satu sistem untuk operasional toko",
        "Mulai dalam empat langkah",
        "Pilih paket yang tepat",
        "Data usaha Anda dijaga",
        "Pertanyaan yang sering diajukan",
        "Mulai Kelola Toko dengan Lebih Teratur",
    ):
        assert heading in html
    # Harga rancangan, tanpa kuota karangan.
    for price in ("Rp10.000", "Rp189.000", "Rp499.000"):
        assert price in html


def test_whatsapp_link_and_no_trial_claim(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    html = client.get("/").data.decode()
    assert "https://wa.me/6282237727330" in html
    assert "0822-3772-7330" in html
    assert "Coba Gratis" not in html
    assert "trial" not in html.lower()
    # Register menjelaskan pendaftaran via WhatsApp, bukan form palsu.
    reg = client.get("/register").data.decode()
    assert "https://wa.me/6282237727330" in reg
    assert "<form" not in reg


def test_landing_assets_and_faq_buttons(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/static/css/landing.css").status_code == 200
    assert client.get("/static/js/landing.js").status_code == 200
    html = client.get("/").data.decode()
    assert html.count("faq-question") >= 7
    assert "menu-toggle" in html
    # Halaman lain tetap jalan: base header/footer tenant tidak rusak.
    assert client.get("/health").status_code == 200
