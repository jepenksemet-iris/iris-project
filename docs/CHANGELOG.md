# Changelog

## 2026-11-25 — Tahap 5: matriks iPOS 4 vs IRIS + rancangan UX

- `docs/IPOS4_FEATURE_MATRIX.md` — audit read-only repo head `71ef6ec0` dibandingkan dengan benchmark iPOS 4 (9 menu utama). Setiap fitur dinilai `Sudah Ada dan Teruji` / `Parsial` / `Belum Ada` / `Perlu Keputusan Produk` / `Tidak Relevan` dengan bukti file/route/test. Temuan kunci: 14 tabel skema v1 ada, tetapi belum ada logika bisnis untuk `sales, purchases, stock_movements, cash_transactions`; produk hanya daftar baca saja; konsinyasi dan proses bulanan manual direkomendasikan tidak ditiru.
- `docs/IRIS_UX_INFORMATION_ARCHITECTURE.md` — sitemap tenant, navigasi sidebar + topbar, dashboard per role, pola halaman daftar (referensi: daftar produk), pola form transaksi, pola kasir, alur utama, matriks hak akses, states dan aksesibilitas, urutan implementasi bertahap.
- Koreksi dari pemeriksaan skema: `products` sudah punya `sku`, `barcode TEXT UNIQUE`, dan `min_stock` — dicatat di matriks sebagai kolom yang ada tanpa UI/logika.
- `docs/README.md` diperbarui dengan indeks kedua dokumen baru. Tidak ada perubahan kode aplikasi; tes tidak berubah (10 passed sebelumnya).

## 2026-11-25 — Tahap 4: landing page POS IRIS

- `templates/landing/index.html` — ditulis ulang penuh: header/nav (Fitur, Solusi, Cara Kerja, Harga, FAQ), hero + mockup kasir (HTML/CSS, data contoh), value strip, masalah, grid 9 fitur, showcase kasir/stok/laporan, cara kerja 4 langkah, 5 kartu solusi, 3 kartu harga, keamanan, FAQ accordion 7 pertanyaan, final CTA, footer. SEO: meta description + Open Graph, canonical posiris.biz.id.
- `static/css/landing.css` — design tokens (CSS variables), responsif 1024/768/480px, `prefers-reduced-motion`. `static/js/landing.js` — menu mobile + FAQ accordion (aria-expanded).
- `templates/landing/register.html` — tanpa form palsu: pendaftaran via WhatsApp resmi 0822-3772-7330 (wa.me/6282237727330), pendaftaran mandiri sedang disiapkan.
- `templates/base.html` — blok `extra_head`/`extra_scripts` dan `body_class`; header/footer skeleton disembunyikan di halaman landing (yang punya header/footer sendiri). Halaman tenant/superadmin tidak berubah tampilannya.
- Kejujuran konten: tanpa "Coba Gratis" (trial belum aktif), tanpa testimoni/statistik palsu, tanpa kuota paket karangan, tanpa halaman legal kosong. Fitur ditandai sebagai ruang lingkup yang sedang dibangun bertahap.
- Tes baru `tests/test_landing.py`: total **10 passed** lokal (Python 3.12.3); landing + tenant dicek langsung lewat HTTP (`/` 200, `/register` 200, CSS/JS 200, `/login` tenant 200).
- Yang BELUM ada: pendaftaran & provisioning tenant mandiri, autentikasi Super Admin, rate limiting login, dan modul operasional.

## 2026-11-25 — Tahap 3: skema database v1 + autentikasi tenant

- `iris_schema.sql` — skema tenant v1 (14 tabel): users, outlets, categories, units, products, stock (per outlet), customers, suppliers, sales, sale_items, purchases, purchase_items, stock_movements, cash_transactions. Uang disimpan sebagai INTEGER rupiah; versi skema dicatat di `PRAGMA user_version = 1`.
- `iris_db.py` — `init_tenant_db()` (idempotent), `create_user()`, `verify_user()`. Password di-hash dengan Werkzeug/scrypt, tidak pernah disimpan mentah. Slug tenant tetap divalidasi ketat.
- `iris_auth.py` + `forms.py` — autentikasi tenant dengan Flask-Login. User id di session dipasangkan dengan slug tenant di session, mencegah session lintas tenant. Role owner/admin/cashier via decorator `require_role()` dan route percobaan `/admin-only`.
- `tenant_app.py` — dashboard dan `/products` kini wajib login; ada `/login` (form Flask-WTF + CSRF), `/logout`, dan perintah CLI `flask --app tenant_app create-owner`.
- Tes baru `tests/test_schema_auth.py` + penyesuaian `tests/test_apps.py`: total **7 passed** lokal (Python 3.12.3).
- Yang BELUM ada: autentikasi Super Admin, rate limiting login / penguncian akun / reset password, pendaftaran & provisioning tenant, dan modul operasional (kasir, tambah produk, mutasi stok, pembelian, laporan).
- `README.md`, `docs/DATABASE.md`, dan `docs/SECURITY.md` diperbarui.

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
