# POS IRIS — IRIS Platform

Platform Point of Sale (POS) berbasis web untuk toko retail, usaha kecil, dan UMKM. Arah pengembangan IRIS adalah menjadi platform operasional bisnis modular berbasis SaaS, bukan hanya aplikasi kasir.

> **Status:** Tahap 2 — skeleton Flask (2026-11-25). Repository berisi dokumentasi proyek + kerangka aplikasi Flask yang bisa dijalankan (halaman placeholder dan `/health` di ketiga aplikasi). Modul operasional (kasir, produk, stok, pembelian, laporan, dst) **belum** diimplementasikan. Daftar fitur di dokumen adalah peta ruang lingkup produk — **bukan** pernyataan bahwa semua fitur sudah selesai atau tersedia.

- **Nama proyek:** IRIS Platform
- **Nama aplikasi:** POS IRIS
- **Domain:** `posiris.biz.id`
- **Target pengguna:** Semua toko retail dan UMKM (toko kelontong/sembako, toko bangunan, toko pakaian, toko elektronik, usaha dagang satu atau beberapa outlet)

## Stack

Pertahankan stack yang sudah dirancang — jangan diganti tanpa keputusan dan analisis migrasi yang eksplisit.

- Python 3.12
- Flask + Jinja2
- SQLite (`sqlite3`, database terpisah per tenant melalui `get_tenant_db`)
- Dependensi yang pernah disebut: Flask-WTF, Flask-Limiter, Gunicorn, pytest, pytest-flask

Komponen aplikasi (skeleton tahap 2 — sudah ada, masih placeholder):

| Aplikasi | File | Port | Fungsi |
|---|---|---|---|
| Landing | `landing_app.py` | 5000 | Situs publik, informasi produk, pendaftaran (placeholder) |
| Tenant | `tenant_app.py` | 5001 | Aplikasi operasional milik tenant (placeholder) |
| Super Admin | `superadmin_app.py` | 5002 | Pengelolaan platform dan tenant (placeholder) |

File pendukung: `config.py` (config dari environment), `iris_db.py` (`get_tenant_db` + validasi slug tenant), `templates/` (Jinja2), `tests/test_apps.py`, `requirements.txt`, `.env.example`.

## Menjalankan skeleton (lokal)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # lalu isi SECRET_KEY
python landing_app.py    # http://127.0.0.1:5000
python tenant_app.py     # http://127.0.0.1:5001/?tenant=toko-demo
python superadmin_app.py # http://127.0.0.1:5002
```

Tes:

```bash
python -m pytest tests/ -q
# Terakhir diuji lokal: 3 passed (2026-11-25)
```

> **Peringatan keamanan:** Super Admin dan Tenant di skeleton ini belum punya autentikasi/otorisasi, dan identitas tenant di `tenant_app.py` masih dari query `?tenant=` untuk keperluan lokal saja. Jangan mengekspos tiga aplikasi ini ke internet sebelum login dan RBAC ditambahkan. Secret hanya dari environment (`.env`, tidak di-commit).

## Dokumentasi

Dokumen induk lengkap: [docs/DOKUMENTASI_PROYEK_IRIS.md](docs/DOKUMENTASI_PROYEK_IRIS.md)

Pemecahan per topik — lihat [docs/README.md](docs/README.md):

- [Project Overview](docs/PROJECT_OVERVIEW.md) — ringkasan, sasaran pengguna, model bisnis & paket
- [Architecture](docs/ARCHITECTURE.md) — stack, komponen, isolasi database tenant
- [Modules](docs/MODULES.md) — peta ruang lingkup fitur per modul
- [Database](docs/DATABASE.md) — pola database per tenant
- [Security](docs/SECURITY.md) — keamanan dan administrasi sistem
- [Testing](docs/TESTING.md) — strategi pengujian dan audit
- [Deployment](docs/DEPLOYMENT.md) — lingkungan pengembangan dan deployment
- [Tenant Provisioning](docs/TENANT_PROVISIONING.md) — alur pendaftaran dan pembuatan tenant
- [Changelog](docs/CHANGELOG.md)

## Model bisnis (rancangan, perlu verifikasi sebelum dipublikasikan)

| Paket | Harga |
|---|---|
| Starter | Rp10.000/bulan |
| Growth | Rp189.000/bulan — harga tetap untuk seluruh outlet selama masih dalam batas paket |
| Scale | Rp499.000/bulan — harga tetap untuk seluruh outlet selama masih dalam batas paket |

Batas outlet, kuota produk/pengguna/transaksi/penyimpanan, dan fitur tiap paket harus ditetapkan eksplisit sebagai konfigurasi paket.

## Prinsip pengembangan

1. Jaga data transaksi dan stok tetap benar.
2. Pastikan isolasi antar-tenant.
3. Lindungi autentikasi dan otorisasi (validasi di server).
4. Jaga kestabilan aplikasi yang sudah berjalan; perubahan sekecil mungkin.
5. Setiap perubahan perilaku disertai pengujian.
6. Jangan memasukkan secret ke Git — gunakan environment variables.

Aturan kerja lengkap untuk pengembangan dengan AI/copilot ada di dokumen induk, bagian 13.
