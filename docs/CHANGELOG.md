# Changelog

## 2026-11-25 — Tahap 2: skeleton Flask

- Menambahkan kerangka aplikasi Flask yang bisa dijalankan:
  - `landing_app.py` (port 5000), `tenant_app.py` (port 5001), `superadmin_app.py` (port 5002), masing-masing dengan route `/` (placeholder) dan `/health`.
  - `config.py` — konfigurasi dari environment (SECRET_KEY wajib di production).
  - `iris_db.py` — `get_tenant_db(slug)` dengan validasi slug ketat; database per tenant di `tenants/<slug>/iris.db`. Belum ada skema/tabel.
  - `templates/` Jinja2: base, landing (index + register placeholder), tenant, superadmin.
  - `requirements.txt`, `.env.example`, `tests/test_apps.py` (3 smoke test).
- Diuji lokal dengan Python 3.12.3: `python -m pytest tests/ -q` → **3 passed**; landing app dicek langsung lewat HTTP (`/health` mengembalikan `{"status":"ok","app":"landing"}`).
- Yang BELUM ada: autentikasi/otorisasi, pendaftaran & provisioning tenant, modul kasir/produk/stok/pembelian/laporan, dan skema database. Identitas tenant di skeleton masih dari query `?tenant=` (lokal saja).
- `README.md` diperbarui dengan cara menjalankan dan peringatan keamanan skeleton.

## 2026-11-25 — Tahap 1: dokumentasi

- Repository diisi dengan dokumentasi proyek POS IRIS:
  - `README.md` utama berisi ringkasan proyek, stack, dan indeks dokumentasi.
  - Dokumen induk dimasukkan sebagai `docs/DOKUMENTASI_PROYEK_IRIS.md`.
  - Dokumentasi dipecah per topik di folder `docs/`: overview, architecture, modules, database, security, testing, deployment, dan tenant provisioning.
  - Ditambahkan `.gitignore` untuk Python/Flask/SQLite dan file secret lokal.
- Status proyek tetap: dokumentasi/rancangan. Belum ada kode aplikasi di repository ini.
