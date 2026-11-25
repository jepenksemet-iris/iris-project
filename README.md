# POS IRIS — IRIS Platform

Platform Point of Sale (POS) berbasis web untuk toko retail, usaha kecil, dan UMKM. Arah pengembangan IRIS adalah menjadi platform operasional bisnis modular berbasis SaaS, bukan hanya aplikasi kasir.

> **Status:** Dokumentasi / rancangan proyek. Repository ini saat ini berisi dokumentasi induk dan pemecahannya per topik. Daftar fitur di dokumen adalah peta ruang lingkup produk — **bukan** pernyataan bahwa semua fitur sudah selesai atau tersedia. Status implementasi harus ditentukan melalui audit kode dan pengujian.

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

Komponen aplikasi yang diketahui (verifikasi dari repository/kode aktual sebelum digunakan):

| Aplikasi | File | Fungsi |
|---|---|---|
| Landing | `landing_app.py` | Situs publik, informasi produk, pendaftaran |
| Tenant | `tenant_app.py` | Aplikasi operasional milik tenant |
| Super Admin | `superadmin_app.py` | Pengelolaan platform dan tenant |

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
