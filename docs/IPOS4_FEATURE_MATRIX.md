# Matriks Fitur iPOS 4 vs POS IRIS

> **Sumber benchmark:** dokumen "Riset Menu, Fitur, dan UX iPOS 4 untuk Pengembangan POS IRIS" — rekonstruksi fitur iPOS 4 dari panduan/manual dan sumber publik (Scribd, ipos4mobile.com, tokoipos.com, dll). Bukan spesifikasi resmi lengkap; ketersediaan fitur iPOS 4 dapat berbeda menurut edisi/build. Jangan mengklaim IRIS sudah memiliki fitur hanya karena tercantum di sini.
>
> **Audit IRIS:** repository `jepenksemet-iris/iris-project`, head commit `71ef6ec0` (tahap 4: landing page), diaudit read-only 2026-11-25; baris terkait produk & stok diperbarui setelah tahap 6 (2026-11-25). Status "Sudah Ada" hanya diberikan bila ada bukti route + template/backend + tes — bukan karena nama tabel atau nama menu ditemukan.
>
> **Status yang dipakai:** `Sudah Ada dan Teruji` · `Parsial` · `Belum Ada` · `Perlu Keputusan Produk` · `Tidak Relevan`

## Ringkasan audit IRIS (bukti)

| Bukti | Isi |
|---|---|
| Route landing (`landing_app.py`) | `GET /`, `GET /health`, `GET /register` (pendaftaran via WhatsApp, provisioning mandiri belum ada) |
| Route tenant (`tenant_app.py`) | `GET /` (dashboard, login wajib), `GET /products` (daftar baca saja, maks 100), `GET/POST /login`, `GET /logout`, `GET /admin-only` (demo role owner/admin), `GET /health`, CLI `create-owner` |
| Route superadmin (`superadmin_app.py`) | `GET /`, `GET /health` — placeholder, **tanpa autentikasi** |
| Skema DB v1 (`iris_schema.sql`, `PRAGMA user_version = 1`) | 14 tabel: `users, outlets, categories, units, products, stock, customers, suppliers, sales, sale_items, purchases, purchase_items, stock_movements, cash_transactions` |
| Auth (`iris_auth.py`, `iris_db.py`, `forms.py`) | Flask-Login, hash password Werkzeug/scrypt, role owner/admin/cashier, `require_role()`, user id `slug:row_id` + cek session tenant |
| Template | `templates/base.html`, `landing/index.html`, `landing/register.html`, `tenant/index.html`, `tenant/login.html`, `tenant/products.html`, `superadmin/index.html`; CSS/JS hanya untuk landing (`static/css/landing.css`, `static/js/landing.js`) |
| Tes | `tests/` — 10 passed lokal (Python 3.12.3): smoke landing/tenant/superadmin, skema v1, hash password, login flow, role, landing page |

**Peringatan penting:** 14 tabel skema v1 sudah ada, tetapi **belum ada satu pun logika bisnis** yang memakai `sales, sale_items, purchases, purchase_items, stock_movements, cash_transactions` — tidak ada route, template, atau tes untuk transaksi. Tabel ≠ fitur.

## 1. Master Data

| Kapabilitas benchmark (iPOS 4) | Status IRIS | Bukti implementasi | Gap / Rekomendasi |
|---|---|---|---|
| Data Item: tambah, daftar, edit, hapus | Parsial | **Tahap 6–7 (2026-11-25):** tambah/edit/arsip produk sudah ada dan teruji (`tenant_app.py`: `/products/new`, `/edit`, `/archive|activate`; `iris_db.py`: `create/update/set_product_active`). Daftar bisa dicari (SKU/nama) + filter kategori + filter nonaktif + indikator Habis/Rendah. Satuan dasar wajib (tahap 7); ganti satuan ditolak bila ada stok/mutasi | Hapus permanen sengaja tidak ada (arsip saja, demi histori). Barcode cetak, multi satuan/harga, serial masih Belum Ada |
| Kartu Stok per item | Sudah Ada dan Teruji | **Tahap 6:** riwayat mutasi per produk di halaman stok (`/products/<id>/stock`, `list_stock_movements()`), teruji di `test_stock_adjustment_and_movements` | — |
| Barcode: pengaturan kode, cetak label | Belum Ada | Kolom `barcode TEXT UNIQUE` sudah ada di `products` (`iris_schema.sql`); tanpa route/template/cetak | Perlu Keputusan Produk: apakah cetak label wajib di tahap awal, atau cukup SKU + scan? |
| Diskon Periode | Belum Ada | Tidak ada tabel/kolom diskon | P1/P2, setelah harga dasar stabil |
| Multi satuan / konversi satuan | Belum Ada | Tabel `units` ada; tidak ada tabel konversi atau logika konversi | P1 — tabel konversi + validasi server |
| Multi harga jual / level harga pelanggan | Belum Ada | `products` hanya punya satu harga jual (per skema v1) | Perlu Keputusan Produk: model harga (per pelanggan/per kuantitas) |
| Nomor serial item | Belum Ada | Tidak ada tabel serial | P3 / Tidak Relevan untuk target toko kelontong — tunda sampai ada permintaan |
| Data Supplier | Sudah Ada dan Teruji | **P1 Tahap 6 (2026-11-25):** daftar + cari + tambah/edit/arsip/aktifkan pemasok (`/suppliers`, owner/admin; `tests/test_purchases.py`) | — |
| Data Pelanggan, Grup Pelanggan, Poin, Wilayah/Subwilayah | Parsial | Tabel `customers` ada; tanpa route/template; grup/poin/wilayah tidak ada di skema | Pelanggan dasar P0 (menyertai kasir); grup/poin P2 |
| Data Sales | Belum Ada | Tidak ada tabel sales | P2 (komisi sales) — tunda |
| Data pendukung: Satuan, Department/Gudang, Merek, Bank, E-Money | Parsial | `units, outlets` ada di skema; merek/bank/e-money tidak ada | Merek + gudang/outlet menyertai Produk/Persediaan (P0/P1); bank/e-money P1 (menyertai pembayaran) |

## 2. Pembelian

| Kapabilitas benchmark | Status IRIS | Bukti | Gap / Rekomendasi |
|---|---|---|---|
| Pesanan Pembelian (PO) | Belum Ada | Tidak ada tabel PO; `purchases` tidak membedakan PO vs penerimaan | P0 — rancang PO sebagai dokumen terpisah atau status pada `purchases` (keputusan desain sebelum coding) |
| Daftar / Input Pembelian (penerimaan) | Sudah Ada dan Teruji | **P1 Tahap 6 (2026-11-25):** form pembelian multi-item + riwayat/detail (`/purchases`), penerimaan langsung menambah stok atomik lewat mutasi `purchase` + pembatalan dengan mutasi `purchase_void` (skema v5; `tests/test_purchases.py`) | P0 — PO draft (`ordered`) belum ada; retur pembelian terpisah |
| History Harga Beli | Belum Ada | Dapat diturunkan dari `purchase_items` setelah pembelian ada | P1 — laporan setelah modul pembelian jalan |
| Pembayaran Hutang, Status Lunas BG/Cek | Belum Ada | Tidak ada tabel hutang/pembayaran hutang | P0 (hutang) — hutang = sisa nilai pembelian kredit; BG/cek P1 |
| Retur Pembelian | Sudah Ada dan Teruji | **P1 Tahap 7 (2026-11-25):** retur sebagian/penuh dari pembelian (`/purchases/<id>/return`), stok keluar `purchase_return`, batas kumulatif, pembatalan retur (`tests/test_returns.py`) | P0 — pengurangan utang/penerimaan uang belum otomatis (modul keuangan) |

## 3. Penjualan

| Kapabilitas benchmark | Status IRIS | Bukti | Gap / Rekomendasi |
|---|---|---|---|
| Pesanan Penjualan / Sales Order | Belum Ada | Tidak ada tabel sales order | P1 — setelah kasir dasar jalan |
| Daftar / Input Penjualan (back-office) | Parsial | **P1 Tahap 3:** riwayat penjualan `/sales` + detail + struk sudah ada dan teruji; penyimpanan lewat kasir, bukan form back-office terpisah | P1 — form input penjualan back-office bila dibutuhkan |
| Penjualan Kasir (POS) | Sudah Ada dan Teruji | **P1 Tahap 2–3 (2026-11-25):** halaman kasir `/pos` + keranjang + checkout atomik (tunai + non-tunai manual, invoice unik, idempotensi, stok berkurang lewat ledger; `tests/test_pos.py` + `tests/test_checkout.py`, 27 tes). Tanpa diskon/pajak di P1 dasar; kuantitas checkout harus bulat | P1 — retur sebagian terpisah |
| Pembatalan Penjualan (Void) | Sudah Ada dan Teruji | **P1 Tahap 5 (2026-11-25):** `POST /sales/<id>/void` owner/admin, alasan wajib, atomik, stok dikembalikan lewat mutasi `sale_void` (skema v4), transaksi/item/pembayaran/mutasi asli tetap tersimpan; `tests/test_void.py`, 12 tes. Pembatalan bukan refund — pengembalian uang proses terpisah | P1 — retur sebagian terpisah |
| History Harga Jual | Belum Ada | Dapat diturunkan dari `sale_items` setelah penjualan ada | P1 |
| Pembayaran Piutang, Status Lunas BG/Cek | Belum Ada | Tidak ada tabel piutang/pembayaran | P0 (piutang) — piutang = sisa nilai penjualan kredit |
| Retur Penjualan | Sudah Ada dan Teruji | **P1 Tahap 7 (2026-11-25):** retur sebagian/penuh dari penjualan (`/sales/<id>/return`), stok masuk `return`, batas kumulatif, pembatalan retur, idempotensi (`tests/test_returns.py`) | P0 — pengembalian uang belum otomatis (modul keuangan) |
| Poin Penjualan | Belum Ada | Tanpa tabel/route | P2 |

## 4. Konsinyasi

| Kapabilitas benchmark | Status IRIS | Bukti | Gap / Rekomendasi |
|---|---|---|---|
| Penerimaan barang titipan, penjualan titipan, komisi, retur ke pemilik | Perlu Keputusan Produk | Tidak ada di skema v1; dokumen benchmark sendiri menandai konsinyasi sebagai historis/opsional dan mungkin tidak dilanjutkan di iPOS 4 | **Tidak dibangun** sampai kebutuhan bisnis tervalidasi. Jangan masuk roadmap P0–P1 |

## 5. Persediaan

| Kapabilitas benchmark | Status IRIS | Bukti | Gap / Rekomendasi |
|---|---|---|---|
| Ringkasan stok per outlet | Sudah Ada dan Teruji | **Tahap 6:** daftar produk menampilkan stok total; halaman stok menampilkan jumlah per outlet (`get_stock_qty()`), teruji | Manajemen outlet mandiri masih Belum Ada (outlet default "Outlet Utama" dibuat otomatis) |
| Item Masuk / Item Keluar | Sudah Ada dan Teruji | **Tahap 7:** penyesuaian masuk/keluar kini jenis mutasi sendiri (`adjustment_in`/`adjustment_out`, skema v2) dengan tanggal efektif + keterangan, teruji | — |
| Stok Opname | Belum Ada | Tanpa route/template | P1 — simpan stok sistem, stok fisik, selisih, alasan, user, waktu |
| Saldo Awal Item | Sudah Ada dan Teruji | **Tahap 7:** saldo awal sebagai mutasi `opening_balance` (skema v2) dengan tanggal efektif; hanya sekali per produk×outlet, duplikat ditolak; koreksi lewat penyesuaian. Teruji (`test_opening_balance_only_once`, `test_migration_v2.py`) | — |
| Transfer Stok antar gudang/outlet | Belum Ada | Tanpa route/template | P1 — satu transaksi DB: stok asal berkurang + tujuan bertambah + mutasi |
| Daftar Stok Minimum | Parsial | Kolom `min_stock` sudah ada di `products` (`iris_schema.sql`); **Tahap 6:** dapat diisi lewat form produk (teruji) | P1 — daftar peringatan stok menipis di dashboard + pengecekan saat penjualan |
| Mutasi Item / Kartu Stok | Sudah Ada dan Teruji | **Tahap 6–7:** `adjust_stock()` atomik (ubah `stock` + tulis `stock_movements` satu transaksi; stok negatif ditolak) + kartu stok dengan filter jenis/tanggal, kolom masuk/keluar + saldo berjalan; rekonsiliasi teruji (`reconcile_stock()`, `test_reconciliation_and_atomicity`) | Penjualan/pembelian/retur/transfer/opname belum ada — masing-masing wajib memakai `adjust_stock()`/mutasi saat dibangun |
| Serial / riwayat serial | Belum Ada | Tanpa tabel | P3 / Tidak Relevan untuk target awal |

## 6. Akuntansi

| Kapabilitas benchmark | Status IRIS | Bukti | Gap / Rekomendasi |
|---|---|---|---|
| Daftar Perkiraan / Chart of Accounts | Belum Ada | Tanpa tabel akun | P2 |
| Kas Masuk / Kas Keluar / Kas Transfer | Belum Ada | Tabel `cash_transactions` ada; tanpa route/template/logika | P1 — kas manual setelah penjualan/pembelian; transfer antar kas/bank bukan pendapatan/beban |
| Daftar Jurnal | Belum Ada | Tanpa tabel jurnal | P2 — double-entry hanya bila diputuskan; jurnal harus seimbang + audit trail |
| Saldo Awal Perkiraan / Hutang / Piutang | Belum Ada | Tanpa route/template | P1/P2 — konsisten dengan saldo awal stok |
| Setting Perkiraan Akuntansi | Belum Ada | Tanpa tabel setting | P2 |

## 7. Proses Data

| Kapabilitas benchmark | Status IRIS | Bukti | Gap / Rekomendasi |
|---|---|---|---|
| Proses Bulanan / Tahunan, Tutup Periode | Belum Ada | Tanpa route/template | **Rekomendasi: jangan ditiru sebagai proses manual.** IRIS memperbarui ledger saat transaksi terjadi. Tutup periode (P2, bila diperlukan) sebagai background job idempotent + kunci periode + log, bukan proses wajib bulanan |

## 8. Laporan

| Kapabilitas benchmark | Status IRIS | Bukti | Gap / Rekomendasi |
|---|---|---|---|
| Laporan Master (item, supplier, pelanggan, sales) | Belum Ada | Daftar produk baca saja adalah satu-satunya "laporan" | P1 — laporan = daftar + filter + ekspor, memakai pola halaman daftar yang sama |
| Laporan Pembelian / Penjualan / Persediaan | Belum Ada | Tanpa route/template | P1 — penjualan/pembelian/persediaan setelah modul transaksinya ada |
| Laporan Hutang/Piutang (beredar, umur, jatuh tempo) | Belum Ada | Tanpa data hutang/piutang | P1 |
| Laporan Keuangan (buku besar, neraca saldo, neraca, laba rugi) | Belum Ada | Tanpa akun/jurnal | P2 |
| Ekspor PDF/XLSX | Belum Ada | Tanpa dependensi ekspor | P1 — pilih satu format dulu (mis. CSV/XLSX), jangan semua sekaligus |

## 9. Pengaturan

| Kapabilitas benchmark | Status IRIS | Bukti | Gap / Rekomendasi |
|---|---|---|---|
| User / Multi Akses / Role | Parsial | `users` + role owner/admin/cashier + `require_role()` teruji (`test_admin_only_route_enforces_role`); tambah/ubah user hanya via CLI `create-owner` | P0 — kelola user lewat UI (owner/admin saja), tanpa CLI untuk operasional |
| Data Perusahaan / Profil Usaha | Belum Ada | Tanpa tabel profil usaha | P1 — nama usaha untuk dokumen/struk |
| Pengaturan Umum, Nomor Transaksi | Belum Ada | Tanpa tabel setting | P1 — penomoran transaksi konsisten + tidak ganda |
| Printer / Mini Printer / Customer Display | Belum Ada | Tanpa setting perangkat | P1 — cetak struk setelah kasir; recovery bila printer gagal |
| Tema / Background | Tidak Relevan | — | Jangan ditiru; IRIS memakai satu tema bersih |
| Import Excel / Import data | Belum Ada | Tanpa route/template | P1 — import tervalidasi (produk dulu), jangan import mentah |
| Backup / Restore Database | Belum Ada | Tanpa route/template; `.gitignore` mengecualikan `*.db` dan `tenants/` | P0 — backup yang **dapat diuji pemulihannya**; restore = operasi berisiko tinggi (konfirmasi kuat + audit log) |
| Desain Dokumen (faktur, surat jalan, label) | Belum Ada | Tanpa template dokumen | P2 — Template Studio setelah transaksi stabil |

## 10. Mobile / Responsif

| Kapabilitas benchmark | Status IRIS | Bukti | Gap / Rekomendasi |
|---|---|---|---|
| Responsif (landing) | Sudah Ada dan Teruji | `static/css/landing.css` breakpoint 1024/768/480px; `tests/test_landing.py` (aset + section) — verifikasi visual browser belum dilakukan | Uji visual desktop/mobile di Tahap E landing (belum dilakukan) |
| Responsif (tenant app) | Belum Ada | Tenant memakai `templates/base.html` tanpa CSS | P0 — tenant butuh CSS dasar + layout responsif sebelum modul kasir dipakai di tablet/ponsel |
| PWA / Offline mode | Belum Ada | Tanpa service worker/manifest | P3 — **jangan** menampilkan label offline sebelum sinkronisasi + konflik data benar-benar didukung |
| iPOS 4 Mobile: dashboard, notifikasi, cetak Bluetooth | Belum Ada | — | P3 — bukan prioritas; web responsif dulu |

## 11. Otomatisasi & Monitoring

| Kapabilitas benchmark | Status IRIS | Bukti | Gap / Rekomendasi |
|---|---|---|---|
| Automation Engine (aturan stok minimum, notifikasi jatuh tempo, ringkasan terjadwal) | Belum Ada | Tanpa tabel/job | P3 — setelah P0/P1 stabil |
| Error Monitoring / Audit Log | Belum Ada | Tanpa tabel audit log; Flask default logging saja | P0 — audit log untuk perubahan stok/keuangan dan aksi admin (tabel + penulisannya menyertai modul P0) |
| Super Admin Platform (daftar tenant, provisioning, paket, langganan) | Belum Ada | `superadmin_app.py` placeholder tanpa auth; `docs/TENANT_PROVISIONING.md` hanya rancangan | P0/P1 — provisioning tenant mandiri + auth Super Admin sebelum pendaftaran publik dibuka; **jangan tampilkan menu Super Admin ke tenant** |

## Prioritas pengembangan (dari dokumen benchmark §22, disesuaikan hasil audit)

- **P0 — Akurasi dan keselamatan transaksi:** isolasi tenant (sudah ada, teruji) → login/role (sudah ada, teruji; tambah kelola user UI) → produk & harga → POS/penjualan → pembelian → konsistensi stok (ledger mutasi) → retur/pembatalan → hutang/piutang → audit log → backup teruji.
- **P1 — Operasional lengkap:** multi outlet/gudang, transfer stok, opname, stok minimum, laporan penjualan/pembelian/persediaan, kas masuk/keluar/transfer, printer/struk, import tervalidasi.
- **P2 — Akuntansi dan analitik:** Chart of Accounts, jurnal double-entry, buku besar, neraca saldo, neraca, laba rugi, dashboard analitik, komisi/poin bila diperlukan.
- **P3 — Pengalaman dan otomatisasi lanjutan:** PWA/mobile, offline dengan sinkronisasi benar, push notification, Automation Engine, integrasi pihak ketiga, item rakitan/serial, Template Studio.

**Keputusan pemilik yang masih dibutuhkan:** (1) apakah barcode wajib di tahap awal; (2) model multi harga (per pelanggan/per kuantitas/tidak); (3) apakah konsinyasi masuk ruang lingkup; (4) apakah akuntansi double-entry atau cukup kas + laba rugi sederhana; (5) kuota/fitur per paket (menyusul — sudah ditanyakan, belum dijawab).
