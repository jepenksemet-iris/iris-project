# Changelog

## 2026-11-25 — Laporan P1 (Rencana Lanjutan, Langkah 1)

- **Tanpa migrasi skema.** Laporan hanya membaca data transaksi yang sudah ada (`iris_db.report_*`, route `/reports*`, template `templates/reports/`).
- **Filter tanggal UTC** (`parse_report_range`): rentang kalender UTC half-open `[dari 00:00, sampai+1 hari 00:00)` — batas awal inklusif, batas akhir eksklusif; tanggal tidak valid diabaikan; rentang default bulan berjalan (UTC). Definisi metrik terdokumentasi di `docs/REPORTS.md`.
- **Ringkasan usaha** (`/reports`): penjualan kotor/diskon/nilai retur/penjualan bersih/nilai pembatalan (terpisah), pembayaran per metode (Σ `paid` transaksi aktif), total/retur/bersih pembelian.
- **Laporan penjualan** (`/reports/sales`): baris per transaksi (nomor, tanggal UTC, kasir, item, subtotal, diskon, total, metode, status) + ringkasan; transaksi batal tidak dihitung sebagai penjualan aktif.
- **Laporan pembelian** (`/reports/purchases`): baris per pembelian (nomor, tanggal, pemasok, item, total, status) + ringkasan; status pembayaran/utang dinyatakan belum tersedia.
- **Laporan stok** (`/reports/stock`): saldo saat ini + masuk/keluar dari ledger pada rentang + indikator Habis/Rendah; filter produk/kategori (pencarian nama/SKU).
- **Laporan retur & pembatalan** (`/reports/returns`): retur (jenis, transaksi asal, nilai, status) + pembatalan penjualan/pembelian (alasan, oleh); peringatan retur bukan bukti refund dibayar.
- **Tes baru (8):** `tests/test_reports.py` — laporan kosong, perhitungan ringkasan (kotor 119000, retur 17000, bersih 102000, batal 24000 terpisah; pembelian bersih 72000), stok dari ledger (masuk/keluar cocok), batas rentang (00:00:00 masuk, 00:00:00 hari berikut tidak masuk), tanggal tidak valid diabaikan, retur + pembatalan, isolasi tenant + login wajib. Total **109 passed** lokal; smoke HTTP: `/reports` dan `/reports/sales` tanpa login 302, `/login` 200, `/health` 200.
- **Keterbatasan yang dicatat:** tidak ada laporan laba/rugi (omzet bukan laba); tidak ada laporan hutang/piutang dan keuangan — menunggu modul keuangan; `cash_transactions` tetap tidak dipakai.
- Dokumen: `docs/REPORTS.md` (baru), `docs/RENCANA_LANJUTAN_AUDIT.md` (tahap 1), matriks iPOS 4.

## 2026-11-25 — P1 Tahap 7: retur penjualan & retur pembelian (migrasi v6)

- **Audit dulu** (`docs/P1_RETUR_AUDIT.md`): skema v5 sudah mencadangkan status `returned` di sales/purchases dan jenis mutasi `return` (keduanya belum pernah dipakai); tidak ada konsep stok rusak/karantina; tidak ada mekanisme refund/utang yang bisa diaudit — nilai retur dicatat sebagai informasi dan pengembalian uang **tidak** otomatis.
- **Migrasi skema v5 → v6** (`iris_schema.sql`, `iris_db.py`, `SCHEMA_VERSION = 6`): tabel baru `returns` + `return_items`; `stock_movements.kind` tambah `'purchase_return'`; index returns/return_items. Rantai migrasi kini v1→…→v6.
- **`iris_db` — retur atomik** (`BEGIN IMMEDIATE`): `create_sale_return()` (stok masuk `return`, hanya penjualan `completed`/`pending`, tolak `void`) dan `create_purchase_return()` (stok keluar `purchase_return`, hanya pembelian `received`, tolak bila stok tidak cukup). Keduanya: harga dari snapshot transaksi asal (bukan dari browser), kumulatif retur per produk dibatasi kuantitas asal dikurangi retur terdahulu, idempotensi token + hash payload (replay mengembalikan retur yang sama), transaksi asal yang diretur penuh menjadi status `returned`, gagal di langkah mana pun → rollback. `cancel_return()` membatalkan retur dengan mutasi kompensasi `ref_type='return_void'` (ditolak bila stok tidak cukup untuk membalik retur penjualan) dan mengembalikan status asal bila tadinya `returned`.
- **Pengaman silang:** `void_sale()` dan `cancel_purchase()` kini menolak pembatalan bila transaksi sudah diretur — agar stok tidak dikembalikan dua kali.
- **Route & template baru:** `GET/POST /sales/<id>/return`, `GET/POST /purchases/<id>/return` (owner/admin; form menampilkan sisa kuantitas yang masih bisa diretur per item), `GET /returns` (filter jenis/status/tanggal/urut), `GET /returns/<id>` (detail + jejak audit + peringatan penyelesaian refund belum otomatis), `POST /returns/<id>/cancel`. Detail penjualan/pembelian menampilkan daftar retur dan tautan "Buat retur"; dashboard menautkan Retur.
- **Tes baru (17):** `tests/test_migration_v6.py` (DB baru v6, migrasi v5→v6 dengan data utuh, migrasi ulang idempotent) dan `tests/test_returns.py` (14 tes: retur penjualan penuh/sebagian + batas kumulatif, produk di luar transaksi asal ditolak, retur penjualan void ditolak, harga historis setelah edit produk, idempotensi replay + token beda data ditolak, rollback saat ledger gagal, batal retur penjualan + stok kembali + status asal pulih, batal ditolak saat stok tidak cukup, void diblokir setelah retur, retur pembelian penuh/sebagian + batas + stok tidak cukup, batal retur pembelian, pembelian batal ditolak diretur, izin kasir 403 + tenant lain 404 + CSRF, riwayat/filter/detail). Total **101 passed** lokal; smoke HTTP: `/pos`, `/returns`, `/purchases` tanpa login 302, `/login` 200, `/health` 200.
- **Keterbatasan yang dicatat:** tidak ada stok rusak/karantina (retur penjualan selalu menambah stok tersedia); tidak ada draft retur (retur langsung diproses); pengembalian uang ke pelanggan dan pengurangan utang pemasok belum otomatis — dicatat sebagai backlog modul keuangan.
- Dokumen: `docs/P1_RETUR_AUDIT.md` (baru), `docs/DATABASE.md` (bagian skema v6), matriks iPOS 4.

## 2026-11-25 — P1 Tahap 6: modul pembelian & penerimaan stok (migrasi v5)

- **Migrasi skema v4 → v5** (`iris_schema.sql`, `iris_db.py`, `SCHEMA_VERSION = 5`): `suppliers` tambah `notes`/`is_active`/`updated_at`; `purchases` tambah `notes` + kolom pembatalan `cancel_reason`/`cancelled_by`/`cancelled_at`; `purchase_items` tambah snapshot `product_name`/`sku`/`unit`; `stock_movements.kind` tambah `'purchase_void'`; index `purchases(created_at)`, `purchases(supplier_id)`, `purchase_items(purchase_id)`. Rantai migrasi kini v1→v2→v3→v4→v5.
- **Pemasok** (`/suppliers`): daftar + cari nama/telepon/alamat, tambah/edit/arsip/aktifkan (owner/admin; kasir 403; daftar untuk semua role yang login). `iris_db`: `list_suppliers`/`get_supplier`/`create_supplier`/`update_supplier`/`set_supplier_active`.
- **`iris_db.create_purchase()` — pembelian atomik** (`BEGIN IMMEDIATE`): pembelian dibuat langsung berstatus `received` (sesuai spesifikasi tahap awal); validasi pemasok (harus aktif bila diisi) dan produk (harus aktif), kuantitas > 0 (pecahan diizinkan — pembelian per berat dimungkinkan), harga beli ≥ 0; total dihitung ulang server; nomor `PO-YYYYMMDD-NNNN`; simpan header + detail snapshot + satu mutasi masuk `purchase` (`ref_type='purchase'`, `ref_id`=purchase id) per item. Harga jual produk tidak diubah. Gagal di langkah mana pun → rollback.
- **Pembatalan pembelian** (`POST /purchases/<id>/cancel`, owner/admin, CSRF, alasan wajib): hanya pembelian `received`; satu mutasi `purchase_void` per item; **ditolak bila stok saat ini tidak mencukupi** (mis. sebagian barang sudah terjual) agar stok tidak negatif; pembatalan ganda dicegah; transaksi/item/mutasi `purchase` asli tidak dihapus.
- **Route & template baru:** `GET /suppliers`, `GET/POST /suppliers/new|/<id>/edit`, `POST /suppliers/<id>/archive|activate`, `GET /purchases` (cari nomor + filter pemasok/status/tanggal/urut), `GET/POST /purchases/new` (form baris item dinamis — tambah/hapus baris + estimasi total di browser, total akhir dihitung server), `GET /purchases/<id>`, `POST /purchases/<id>/cancel`. Dashboard tenant menautkan Pembelian & Pemasok.
- **Tes baru (13):** `tests/test_migration_v5.py` (DB baru v5, migrasi v4→v5 dengan data utuh, migrasi ulang idempotent) dan `tests/test_purchases.py` (10 tes: CRUD pemasok + pencarian + arsip, pembelian multi-item dengan total server & stok & ledger cocok, pembelian tanpa pemasok + kuantitas pecahan, validasi gagal, rollback saat ledger gagal, batal pembelian + stok kembali, batal ditolak saat stok tidak cukup, izin kasir 403 + tenant lain 404 + CSRF, snapshot bertahan setelah edit produk, riwayat/filter). Total **84 passed** lokal (Python 3.12.3; venv `/tmp/iris-venv` sempat hilang karena pergantian VM dan dibuat ulang dari `requirements.txt`); smoke HTTP: `/pos`, `/purchases`, `/suppliers` tanpa login 302, `/login` 200, `/health` 200.
- **Keterbatasan yang dicatat:** pesanan pembelian/PO draft (status `ordered`) belum diimplementasikan — pembelian langsung diterima; retur pembelian adalah tahap terpisah (pembatalan bukan retur); utang ke pemasok belum dicatat (tidak ada modul keuangan).
- Dokumen: `docs/DATABASE.md` (bagian skema v5), matriks iPOS 4.

## 2026-11-25 — P1 Tahap 4 & 5: audit ledger + pembatalan penjualan (migrasi v4)

- **Tahap 4 — audit integrasi ledger** (`docs/P1_LEDGER_AUDIT.md`, baru): audit read-only atas checkout Tahap 3 — setiap item checkout menghasilkan tepat satu mutasi `sale` (kuantitas cocok, `ref_type='sale'`/`ref_id`=sale id, catatan berisi nomor invoice), stok hanya diubah lewat `_apply_stock_change()`, rollback penuh saat ledger gagal, idempotensi tanpa duplikasi, konkurensi stok terakhir aman — semua sudah terbukti oleh kode dan tes Tahap 3. Tidak ada perubahan kode integrasi yang diperlukan; ditambah satu tes multi-item eksplisit.
- **Migrasi skema v3 → v4** (`iris_schema.sql`, `iris_db.py`, `SCHEMA_VERSION = 4`): `stock_movements.kind` ditambah `'sale_void'` (mutasi pembalik pembatalan); tabel dibuat ulang dalam satu transaksi, data lama disalin apa adanya. Rantai migrasi kini v1→v2→v3→v4.
- **`iris_db.void_sale()` — pembatalan atomik** (`BEGIN IMMEDIATE`): hanya sale `completed`/`pending`; alasan wajib (maks. 500 karakter); cegah pembatalan ganda (cek status + mutasi pembalik yang sudah ada); tulis `void_reason`/`voided_by`/`voided_at`; satu mutasi `sale_void` per item yang mengembalikan stok persis kuantitas terjual. Transaksi, item, pembayaran, dan mutasi `sale` asli tidak dihapus/diubah. Kebijakan: pembatalan **bukan** pengembalian uang — `paid` dan `sale_payments` tetap tercatat; tidak ada status `refunded` yang dipalsukan.
- **Route baru:** `POST /sales/<id>/void` (owner/admin saja, CSRF, alasan wajib; kasir 403; tenant lain 404). Detail transaksi menampilkan status pembayaran turunan (Lunas/Belum terverifikasi/Dibatalkan), kolom diskon item, info pembatalan, dan form pembatalan; struk transaksi batal menampilkan **DIBATALKAN** + alamat/telepon outlet.
- **Riwayat dilengkapi:** filter metode pembayaran, urut terbaru/terlama, filter tidak valid (status/tanggal/urutan) diabaikan dengan aman — tidak crash dan tidak menyembunyikan data secara diam-diam.
- **Tes baru (15):** `tests/test_migration_v4.py` (DB baru v4, migrasi v3→v4 dengan data utuh, migrasi ulang idempotent) dan `tests/test_void.py` (12 tes: ledger multi-item cocok + rekonsiliasi konsisten, void tunai & non-tunai pending mengembalikan stok, alasan wajib, kasir 403, double-void tidak menggandakan stok, rollback saat ledger pembalik gagal, void setelah produk diarsip, void tenant lain 404, CSRF, filter riwayat + filter invalid + state kosong). Total **71 passed** lokal (Python 3.12.3); smoke HTTP: `/pos` dan `/sales` tanpa login 302, `/login` 200, `/health` 200.
- **Keterbatasan yang dicatat:** tidak ada batas waktu pembatalan yang diarang (bisa dibatalkan selama status memenuhi syarat); retur sebagian adalah tahap terpisah; pengembalian uang adalah proses terpisah dan belum diimplementasikan.
- Dokumen: `docs/P1_LEDGER_AUDIT.md` (baru), `docs/DATABASE.md` (bagian skema v4), matriks iPOS 4.

## 2026-11-25 — P1 Tahap 3: penyimpanan penjualan, pembayaran, migrasi v3

- **Migrasi skema v2 → v3** (`iris_schema.sql`, `iris_db.py`, `SCHEMA_VERSION = 3`): `sale_items` tambah kolom snapshot `product_name`/`sku`/`unit`; `sales` dibuat ulang (status CHECK + `'pending'`, kolom `change_amount`, `payment_ref`, `idempotency_key UNIQUE`, `idempotency_payload`, `void_reason`/`voided_by`/`voided_at`); tabel baru `sale_payments`; index `sales(created_at)`, `sales(user_id)`, `sale_items(product_id)`, `sale_payments(sale_id)`. Migrasi berantai v1→v2→v3; `migrate_tenant_db` menolak versi tak dikenal tanpa menandainya.
- **`iris_db.create_sale()` — checkout atomik** (`BEGIN IMMEDIATE`): cek idempotensi (token + hash payload; token sama + payload berbeda ditolak), validasi keranjang dari database (produk aktif, kuantitas bulat > 0, stok cukup), hitung ulang total (tanpa diskon/pajak di P1 dasar), nomor invoice `INV-YYYYMMDD-NNNN` (UNIQUE constraint sebagai pengaman), simpan `sales` + `sale_items` (snapshot) + `sale_payments`, kurangi stok lewat ledger (`kind='sale'`, `ref_type='sale'`, `ref_id`=sale id) — gagal di langkah mana pun membatalkan semuanya. `adjust_stock()` di-refactor ke inti `_apply_stock_change()` agar bisa dipakai di dalam transaksi penjualan tanpa commit parsial.
- **Pembayaran:** tunai wajib uang diterima ≥ total (kembalian dihitung server); non-tunai (transfer/QRIS/debit) dicatat manual, status `pending`, `paid`=0 sampai owner/admin mengonfirmasi via `POST /sales/<id>/confirm-payment` (kasir 403). Pembayaran parsial tidak diaktifkan.
- **Route baru:** `POST /pos/checkout`, `GET /sales` (cari invoice + filter tanggal/status), `GET /sales/<id>`, `GET /sales/<id>/receipt` (struk `@media print`), `POST /sales/<id>/confirm-payment`. Form kasir kini punya pilihan metode + uang diterima + referensi + token idempotensi, tombol bayar menonaktifkan diri saat diproses.
- **Tes baru (18):** `tests/test_migration_v3.py` (DB baru v3, migrasi v2→v3 dengan data utuh, rantai v1→v3, versi tak dikenal ditolak, FK check bersih, migrasi ulang idempotent) dan `tests/test_checkout.py` (14 tes: tunai pas/lebih/kurang, non-tunai pending + konfirmasi + konfirmasi ganda ditolak, snapshot bertahan setelah edit produk, invoice unik, idempotensi sekali saja + payload berbeda ditolak, validasi gagal, rollback saat ledger gagal, **dua checkout bersamaan untuk stok terakhir — hanya satu berhasil**, riwayat/detail/struk, isolasi tenant, CSRF). Total **56 passed** lokal (Python 3.12.3); smoke HTTP: `/pos` dan `/sales` tanpa login 302, `/login` 200, `/health` 200.
- **Keterbatasan yang dicatat:** checkout hanya menerima kuantitas bulat (sesuai spesifikasi Tahap 3) — produk yang dijual per berat (kg) belum bisa dijual sampai ada keputusan fractional; pembayaran non-tunai diverifikasi manual (tanpa integrasi gateway); pembatalan/retur masuk Tahap 5, kolomnya sudah disiapkan di v3.
- Dokumen: `docs/DATABASE.md` (bagian skema v3), matriks iPOS 4.

## 2026-11-25 — P1 Tahap 2: halaman kasir, keranjang & kalkulasi

- **Halaman kasir** (`GET /pos`, semua role yang login): pencarian nama/SKU/barcode (scanner berfungsi seperti keyboard), hasil pencarian dengan harga + stok outlet default, keranjang selalu terlihat, total menonjol; tombol proses pembayaran dinonaktifkan dengan keterangan "Tahap 3".
- **Keranjang di session per tenant** (`POST /pos/cart/add|set|remove|clear`): produk yang sama digabung satu baris; kuantitas 0 pada ubah = hapus item; kosongkan keranjang dengan konfirmasi. **Tidak ada** transaksi penjualan yang diposting dan **tidak ada** perubahan stok/ledger pada tahap ini.
- `iris_db.py` — `search_products()` (produk aktif saja, stok outlet default) dan `summarize_cart()` (harga selalu dari `sell_price` database; validasi aktif, qty > 0, qty ≤ stok; baris bermasalah tidak dihitung).
- `forms.py` — `CartAddForm`/`CartSetForm`/`CartRemoveForm` (CSRF). Perbaikan kecil: validator kuantitas memakai `InputRequired` supaya angka 0 ditolak dengan pesan yang jelas, bukan gagal diam-diam (`DataRequired` menganggap 0 kosong).
- Template `templates/pos/cashier.html` + `static/css/pos.css` (dua kolom di desktop, satu kolom ≤ 768px); tautan "Buka kasir" dari dashboard tenant.
- Tes baru `tests/test_pos.py` (13 tes): halaman terbuka + wajib login, cari nama/SKU/barcode, tambah + gabung, nonaktif ditolak, qty 0/negatif ditolak, qty melebihi stok ditolak, kalkulasi dua produk, harga dihitung ulang dari server (harga palsu dari browser diabaikan; harga DB diubah → total ikut), ubah/hapus/kosongkan, **tidak ada perubahan stok/ledger/sales saat keranjang berubah**, isolasi tenant, kasir boleh kasir tapi 403 kelola produk, CSRF tanpa token. Total **38 passed** lokal (Python 3.12.3); smoke HTTP: `/pos` tanpa login 302, `/login` 200, `pos.css` 200, `/health` 200.
- Audit P1 (`docs/P1_KASIR_AUDIT.md`) ditulis sebelum coding: P0 terverifikasi selesai (25 tes), gap skema v3 untuk Tahap 3 (snapshot produk di `sale_items`, status `pending`, `payment_ref`, `idempotency_key`, kolom pembatalan) dicatat di sana — belum dikerjakan.

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
