# Changelog

## 2026-11-25 — Tahap 7: tutup gap P0 produk & stok + migrasi skema v2 (Paket B)

- **Migrasi skema v1 → v2** (`iris_schema.sql`, `iris_db.py`): `SCHEMA_VERSION = 2`; `stock_movements.kind` ditambah `opening_balance`, `adjustment_in`, `adjustment_out`; kolom baru `effective_date`. `migrate_tenant_db()` membuat ulang tabel dalam satu transaksi (CHECK SQLite tidak bisa di-ALTER) dengan pemetaan data lama: `adjustment` + catatan "Saldo awal…" → `opening_balance`, positif → `adjustment_in`, negatif → `adjustment_out`. `init_tenant_db()` menjalankan migrasi otomatis untuk DB lama; DB baru langsung v2.
- `iris_db.py` — `record_opening_balance()` (qty > 0; nol tidak menulis mutasi; duplikat per produk×outlet ditolak), `reconcile_stock()` (saldo `stock` vs jumlah mutasi), `list_stock_movements()` dengan filter jenis + rentang tanggal, `list_products()` dengan filter kategori, `list_categories()`, `update_product()` melarang ganti satuan bila produk sudah punya stok/mutasi.
- `forms.py` — satuan dasar kini wajib; `min_stock` opsional (kosong = 0); `StockAdjustForm` kini punya jenis mutasi (saldo awal / masuk / keluar) + tanggal efektif.
- `tenant_app.py` + template — daftar produk: filter kategori + indikator Habis/Rendah; halaman stok: form jenis mutasi + tanggal efektif, filter ledger, kolom masuk/keluar + saldo berjalan.
- Tes baru: `tests/test_migration_v2.py` (DB baru v2; migrasi v1→v2 dengan pemetaan jenis + data stok utuh) dan 7 tes baru di `tests/test_products_stock.py` (saldo awal sekali saja, nama kosong, edit SKU sama/ID tetap, satuan terkunci, rekonsiliasi + atomicity via trigger, CSRF tanpa token, SQL injection sebagai data, filter kategori + badge stok). Total **25 passed** lokal (Python 3.12.3); tenant dicek langsung lewat HTTP (`/login` 200, `/products` tanpa login 302, `/health` 200).
- Keputusan pemilik yang diterapkan (Paket B): jenis mutasi baru via migrasi v2; satuan dasar wajib; pagination tidak dibuat (pola ini belum dipakai aplikasi mana pun, sesuai spesifikasi §P0.1).
- Dokumen: `docs/DATABASE.md` (bagian skema v2), `docs/P0_PRODUK_STOK_GAP_ANALYSIS.md` (status gap diperbarui), matriks iPOS 4.

## 2026-11-25 — Tahap 6: modul produk & stok

- `iris_db.py` — `create_product()`, `get_product()`, `update_product()`, `set_product_active()` (arsip, bukan hapus), `list_products()` (cari SKU/nama + total stok), `get_or_create_category/unit()`, `get_default_outlet()` (buat "Outlet Utama" bila belum ada outlet), `adjust_stock()` (atomik: ubah `stock` + tulis `stock_movements` dalam satu transaksi; stok hasil tidak boleh negatif), `list_stock_movements()`, `get_stock_qty()`, `list_outlets()`.
- `tenant_app.py` — route baru (login wajib; tambah/edit/arsip/stok hanya owner/admin, 403 untuk kasir): `GET /products` (cari + filter nonaktif + stok total), `GET/POST /products/new`, `GET/POST /products/<id>/edit`, `POST /products/<id>/archive|activate`, `GET/POST /products/<id>/stock` (penyesuaian + kartu stok).
- `forms.py` — `ProductForm` (SKU, nama, barcode, kategori, satuan, harga beli/jual, stok minimum), `StockAdjustForm` (outlet, jumlah +/-, keterangan), `ConfirmForm` (CSRF untuk arsip).
- Template tenant baru/diubah: `products.html` (daftar + cari), `product_form.html`, `product_stock.html` (stok per outlet + kartu stok), `index.html` (tautan + status modul).
- Tes baru `tests/test_products_stock.py` (6 tes): tambah + SKU duplikat ditolak, kasir 403 tapi bisa lihat daftar, edit + arsip/aktifkan, penyesuaian +10/−3 = 7 dengan 2 mutasi, penyesuaian negatif berlebih ditolak tanpa mutasi, isolasi antar-tenant. Total **16 passed** lokal (Python 3.12.3); tenant dicek langsung lewat HTTP (`/login` 200, `/products` tanpa login 302, `/health` 200).
- Yang BELUM ada: kasir/penjualan, pembelian, laporan, keuangan, dan manajemen outlet/kategori mandiri (kategori/satuan dibuat otomatis dari form produk; outlet default dibuat otomatis).

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
