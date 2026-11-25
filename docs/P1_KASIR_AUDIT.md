# Audit Tahap 1 — P1 Modul Kasir (read-only, 2026-11-25)

> **Head yang diaudit:** `b883e87b` (tahap 6–7, skema v2). Audit ini tidak mengubah kode.
> **Hasil regresi saat audit:** `pytest` **25 passed** (Python 3.12.3) — seluruh tes P0 + regresi lolos.

## 1. Verifikasi penutupan P0 (Bagian A dokumen P1)

| Checklist P0 | Bukti verifikasi |
|---|---|
| Daftar, cari, tambah, edit produk | Route `/products`, `/products/new`, `/edit`; tes `test_products_stock.py` |
| SKU unik per tenant | `products.sku UNIQUE`; tes duplikat ditolak |
| Validasi nama/SKU/satuan | `ProductForm` (server-side) + `create/update_product()`; tes nama kosong ditolak |
| Produk nonaktif tidak dapat dipilih untuk transaksi baru | **Belum dapat diverifikasi — belum ada transaksi.** Akan ditegakkan di P1 (hanya produk aktif yang bisa dijual) |
| Histori tidak rusak saat produk diedit | Edit tidak menyentuh `stock_movements`; arsip via `is_active`, tanpa hapus fisik |
| Saldo awal → ledger; masuk/keluar tercatat | `record_opening_balance()` + `adjust_stock()` atomik; tes `test_opening_balance_only_once` |
| Saldo == ledger; stok negatif dicegah; atomicity | `reconcile_stock()` + tes rekonsiliasi dan atomicity (trigger) |
| Mutasi tidak dapat diubah/dihapus diam-diam | Tidak ada route edit/hapus mutasi |
| Isolasi tenant, permission, CSRF | Tes isolasi tenant; kasir 403 untuk kelola produk/stok; tes CSRF tanpa token |
| Tes tidak menyentuh DB tenant nyata | Semua tes memakai `tmp_path` |

**Kesimpulan:** P0 terbukti selesai kecuali satu poin yang memang baru bisa dibuktikan oleh P1 (produk nonaktif tidak terjual). Tidak ada rebuild P0 yang diperlukan.

## 2. Kondisi aktual yang dipakai ulang (komponen P0)

- `get_tenant_db` / `init_tenant_db` / `migrate_tenant_db` — koneksi + migrasi per tenant.
- `list_products` (cari SKU/nama, filter kategori) + `get_product` + `get_stock_qty` — sumber harga (`sell_price`) dan stok.
- `adjust_stock()` — atomik (ubah `stock` + tulis `stock_movements`), tolak stok negatif. **Satu kekurangan:** `ref_type` di-hardcode `''` dan `ref_id` tidak pernah diisi — kasir butuh mutasi dengan referensi transaksi penjualan. Perbaikan minimal: tambah parameter `ref_type`/`ref_id` (default kosong, kompatibel dengan pemakaian lama).
- `get_default_outlet()` — outlet untuk penjualan (multi-outlet belum ada UI pemilihan).
- `require_role("owner","admin")` untuk kelola produk/stok; kasir boleh login + lihat daftar produk. Login Flask-Login, CSRF Flask-WTF, flash message, template `base.html`.
- `stock_movements.kind` v2 sudah mengenal `sale` — mutasi penjualan memakai `kind='sale'`.

## 3. Skema penjualan yang sudah ada (v2) — dan gap-nya

| Tabel/kolom | Kondisi | Penilaian |
|---|---|---|
| `sales` | `outlet_id`, `user_id`, `customer_id` (nullable), `invoice_no TEXT UNIQUE`, `status CHECK ('completed','void','returned')`, `subtotal/discount/tax/total/paid INTEGER >= 0`, `payment_method TEXT DEFAULT 'cash'` (tanpa CHECK) | Bisa dipakai. **Gap:** tidak ada status untuk pembayaran non-tunai yang belum terverifikasi; tidak ada kolom referensi pembayaran; tidak ada kolom alasan/audit pembatalan |
| `sale_items` | `sale_id` (CASCADE), `product_id`, `qty REAL > 0`, `price INTEGER` (snapshot harga), `discount INTEGER` | **Gap:** tidak ada snapshot nama produk, SKU, dan satuan — spesifikasi §9/§12 mewajibkan histori tetap benar meski master produk diedit |
| `cash_transactions` | `kind income/expense`, `amount`, `description` | Untuk kas di luar penjualan/pembelian — **tidak** dipakai untuk pembayaran penjualan (pembayaran tercatat di `sales.paid` + `payment_method`) |
| `products.barcode` | `TEXT UNIQUE`, sudah bisa diisi | Pencarian barcode didukung skema; perlu helper cari yang mencakup barcode |
| Format `invoice_no` | Tidak ada pola di repo | Belum ada — perlu diputuskan (usulan §5) |

## 4. Rencana migrasi minimal — skema v3

Satu migrasi, diuji di DB sementara seperti v2 (`migrate_tenant_db`, tambah jalur v2→v3):

1. `sale_items`: tambah kolom `product_name TEXT`, `sku TEXT`, `unit TEXT` (snapshot; diisi saat penjualan disimpan).
2. `sales`: tambah `payment_ref TEXT` (referensi transfer/QRIS), `idempotency_key TEXT UNIQUE` (pencegah submit ganda di sisi server), `void_reason TEXT`, `voided_by INTEGER`, `voided_at TEXT`.
3. `sales.status`: tambah `'pending'` ke CHECK (transaksi non-tunai yang pembayarannya belum terverifikasi — supaya tidak ditandai berhasil hanya karena kasir memilih metode non-tunai, sesuai spesifikasi §10).
4. Tidak ada perubahan pada tabel P0 (`products`, `stock`, `stock_movements`) kecuali penambahan parameter referensi di `adjust_stock()` (bukan perubahan skema).

## 5. Keputusan bisnis yang diusulkan (perlu persetujuan pemilik)

| # | Keputusan | Usulan |
|---|---|---|
| 1 | Diskon | **Tidak ada diskon di P1 dasar.** Skema mendukung (`discount`), tapi tidak ada aturan/permission diskon yang jelas. Total = subtotal. |
| 2 | Pajak | **Tidak ada pajak di P1 dasar** (tarif 0). Tidak ada konfigurasi pajak di proyek; jangan mengarang tarif. |
| 3 | Metode pembayaran | Tunai + transfer bank + QRIS. Tunai: uang diterima + kembalian, ditolak bila kurang. Non-tunai: status `pending` + referensi bila ada; owner/admin mengonfirmasi pembayaran di halaman detail (baru setelah itu `completed` + `paid` = total). |
| 4 | Format nomor transaksi | `INV-YYYYMMDD-0001` (urutan harian per tenant, dibuat di dalam transaksi DB; benturan ditangani retry). |
| 5 | Pelanggan | Tidak ada pemilihan pelanggan di P1 dasar (`customer_id` NULL — penjualan tunai tanpa nama). |
| 6 | Outlet | Outlet default (`get_default_outlet`) untuk semua penjualan P1. |
| 7 | Pembatalan | Hanya owner/admin; alasan wajib; mutasi pembalik `kind='return'` dengan `ref_type='sale'` ke transaksi asal; pembatalan ganda ditolak; transaksi tidak dihapus. |
| 8 | Keranjang | Disimpan di session Flask per tenant; server menghitung ulang harga/stok/total saat checkout (tidak percaya nilai dari browser). Produk stok nol tidak bisa dijual. |
| 9 | Cetak ulang struk | Semua role yang login boleh (hanya baca); tidak membuat transaksi/mutasi baru. |

## 6. Rencana file (Tahap 2–6)

- **Baru:** `tests/test_pos.py` (keranjang, perhitungan, pembayaran, atomik, konkurensi, histori, pembatalan, isolasi), `tests/test_migration_v3.py`, `templates/pos/cashier.html`, `templates/pos/sales_list.html`, `templates/pos/sale_detail.html`, `templates/pos/receipt.html`.
- **Diubah:** `iris_schema.sql` (v3), `iris_db.py` (`migrate_tenant_db` jalur v2→v3; `search_products()` termasuk barcode; `create_sale()` atomik dengan `BEGIN IMMEDIATE`; `get_sale()`/`list_sales()`; `void_sale()`; `confirm_payment()`; `adjust_stock()` tambah `ref_type`/`ref_id`), `forms.py` (form keranjang/checkout), `tenant_app.py` (route `/pos`, `/pos/search`, `/pos/checkout`, `/sales`, `/sales/<id>`, `/sales/<id>/receipt`, `/sales/<id>/void`, `/sales/<id>/confirm-payment`), `README.md`, `docs/CHANGELOG.md`, `docs/DATABASE.md`, `docs/IPOS4_FEATURE_MATRIX.md`, `docs/README.md`.
- **Tidak diubah:** `products`, `stock`, `stock_movements` (skema), logika P0, landing, superadmin.

## 7. Risiko

- **Stok terakhir dijual dua kasir bersamaan:** ditangani dengan `BEGIN IMMEDIATE` (satu penulis dalam satu waktu di SQLite) + validasi stok di dalam transaksi yang sama. Diuji dengan dua koneksi bersamaan.
- **Submit ganda:** `idempotency_key` unik per keranjang + token form; submit kedua mengembalikan transaksi yang sama, bukan transaksi baru.
- **Harga dari browser:** diabaikan; harga selalu diambil dari `products.sell_price` di server saat checkout.
- **Retur sebagian:** di luar P1 (tahap terpisah, sesuai spesifikasi §14).
- **Verifikasi pembayaran non-tunai:** manual oleh owner/admin; tidak ada integrasi provider pembayaran di P1.
