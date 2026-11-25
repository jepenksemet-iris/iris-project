# POS IRIS — IRIS Platform

Platform Point of Sale (POS) berbasis web untuk toko retail, usaha kecil, dan UMKM. Arah pengembangan IRIS adalah menjadi platform operasional bisnis modular berbasis SaaS, bukan hanya aplikasi kasir.

> **Status:** Tahap 3 — skema database v1 + autentikasi tenant (2026-11-25). Database tenant SQLite kini punya skema v1 (14 tabel) dan aplikasi tenant dilindungi login dengan role owner/admin/cashier. Modul operasional (kasir, produk, stok, pembelian, laporan, dst) **belum** diimplementasikan — yang ada baru daftar produk (baca saja). Daftar fitur di dokumen adalah peta ruang lingkup produk — **bukan** pernyataan bahwa semua fitur sudah selesai atau tersedia.

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
| Tenant | `tenant_app.py` | 5001 | Aplikasi operasional milik tenant — **login wajib**, dashboard + daftar produk |
| Super Admin | `superadmin_app.py` | 5002 | Pengelolaan platform dan tenant (placeholder, **belum ada auth**) |

File pendukung: `config.py` (config dari environment), `iris_db.py` (`get_tenant_db`, `init_tenant_db`, `create_user`, `verify_user`), `iris_schema.sql` (skema v1, 14 tabel), `iris_auth.py` (Flask-Login + `require_role`), `forms.py` (form login), `templates/` (Jinja2), `tests/`, `requirements.txt`, `.env.example`.

## Menjalankan aplikasi (lokal)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # lalu isi SECRET_KEY
python landing_app.py    # http://127.0.0.1:5000
python tenant_app.py     # http://127.0.0.1:5001
python superadmin_app.py # http://127.0.0.1:5002
```

Buat owner pertama untuk sebuah tenant, lalu masuk lewat `/login`:

```bash
flask --app tenant_app create-owner --tenant toko-demo \
  --username owner --password 'minimal-8-karakter'
# Buka http://127.0.0.1:5001/login — tenant: toko-demo
```

Tes:

```bash
python -m pytest tests/ -q
# Terakhir diuji lokal: 7 passed (2026-11-25)
```

> **Peringatan keamanan:** Super Admin masih **belum punya autentikasi** — jangan diekspos ke internet. Aplikasi tenant sudah login + role, tapi belum ada rate limiting login, penguncian akun, atau reset password. Secret hanya dari environment (`.env`, tidak di-commit); password pengguna disimpan sebagai hash (Werkzeug/scrypt), bukan teks mentah.

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
