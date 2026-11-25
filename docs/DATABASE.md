# Database — POS IRIS

Dari dokumen induk: [DOKUMENTASI_PROYEK_IRIS.md](DOKUMENTASI_PROYEK_IRIS.md) bagian 4.3.

## Pola penyimpanan

Database SQLite terpisah untuk setiap tenant, dengan pola direktori:

```text
tenants/
└── <tenant-slug>/
    └── iris.db
```

Akses database tenant dilakukan melalui `get_tenant_db(slug)` di `iris_db.py`, dan skema diterapkan oleh `init_tenant_db(slug)` dari `iris_schema.sql`.

## Skema v6 (P1 Tahap 7, 2026-11-25)

Versi skema dicatat di `PRAGMA user_version = 6`. Database lama dimigrasi otomatis oleh `iris_db.migrate_tenant_db()` (rantai v1→…→v6).

Perubahan v6 (retur penjualan & pembelian):
- Tabel baru `returns` (kind `sale_return`/`purchase_return`, nomor `RS-`/`RP-YYYYMMDD-NNNN`, status `completed`/`cancelled`, alasan wajib, total dari harga historis asal, `idempotency_key` UNIQUE, jejak pembatalan `cancel_*`) dan `return_items` (snapshot produk + qty + harga historis).
- `stock_movements.kind`: tambah `'purchase_return'` (retur penjualan memakai `'return'` yang sudah ada). Pembatalan retur memakai `ref_type='return_void'`.
- Aturan yang ditegakkan service: retur penjualan hanya untuk penjualan `completed`/`pending` (bukan `void`); retur pembelian hanya untuk pembelian `received`; kumulatif retur per produk tidak boleh melebihi kuantitas asal; retur pembelian ditolak bila stok tidak mencukupi; penjualan/pembelian yang diretur penuh menjadi status `returned`; pembatalan penjualan/pembelian diblokir bila sudah ada retur yang diproses (agar stok tidak kembali dua kali); pembatalan retur memakai mutasi kompensasi dan mengembalikan status asal bila tadinya `returned`.
- Nilai retur adalah informasi transaksi — pengembalian uang/utang **tidak** diproses otomatis (belum ada modul keuangan).

## Skema v5 (P1 Tahap 6, 2026-11-25)

Versi skema dicatat di `PRAGMA user_version = 5`. Database lama dimigrasi otomatis oleh `iris_db.migrate_tenant_db()` (rantai v1→v2→v3→v4→v5).

Perubahan v5 (modul pembelian):
- `suppliers`: tambah `notes`, `is_active`, `updated_at`.
- `purchases`: tambah `notes` + kolom pembatalan `cancel_reason`/`cancelled_by`/`cancelled_at`.
- `purchase_items`: tambah snapshot `product_name`/`sku`/`unit`.
- `stock_movements.kind`: tambah `'purchase_void'` (mutasi pembalik pembatalan pembelian; tabel dibuat ulang, data disalin apa adanya).
- Index baru: `purchases(created_at)`, `purchases(supplier_id)`, `purchase_items(purchase_id)`.

## Skema v4 (P1 Tahap 5, 2026-11-25)

Versi skema dicatat di `PRAGMA user_version = 4`. Database lama dimigrasi otomatis oleh `iris_db.migrate_tenant_db()` (rantai v1→v2→v3→v4).

Perubahan v4: satu-satunya perubahan adalah `stock_movements.kind` ditambah `'sale_void'` (mutasi pembalik pembatalan penjualan). Tabel dibuat ulang dalam satu transaksi; data lama disalin apa adanya, tanpa pemetaan jenis.

## Skema v3 (P1 Tahap 3, 2026-11-25)

Versi skema dicatat di `PRAGMA user_version = 3`. Database lama dimigrasi otomatis oleh `iris_db.migrate_tenant_db()` (rantai v1→v2→v3 atau v2→v3).

Perubahan v3 (penjualan kasir):
- `sale_items`: kolom snapshot baru `product_name`, `sku`, `unit` (ALTER TABLE, data lama tetap).
- `sales`: dibuat ulang dalam satu transaksi — status CHECK ditambah `'pending'` (pembayaran non-tunai dicatat manual tapi belum terverifikasi); kolom baru `change_amount`, `payment_ref`, `idempotency_key UNIQUE`, `idempotency_payload`, `void_reason`, `voided_by`, `voided_at`. Data penjualan lama disalin utuh.
- Tabel baru `sale_payments` (satu baris per pembayaran yang dicatat kasir; non-tunai = dicatat manual, **bukan** terverifikasi gateway).
- Index baru: `sales(created_at)`, `sales(user_id)`, `sale_items(product_id)`, `sale_payments(sale_id)`.
- Arti kolom pembayaran: `sales.paid` = jumlah yang diterapkan ke penjualan (tunai = total; non-tunai pending = 0 sampai dikonfirmasi); `sale_payments.amount` = nominal yang diterima (tunai bisa lebih dari total; kembaliannya di `sales.change_amount`).

## Skema v2 (tahap 7 / Paket B, 2026-11-25)

Versi skema dicatat di `PRAGMA user_version = 2`. Database v1 dimigrasi otomatis oleh `iris_db.migrate_tenant_db()` saat `init_tenant_db()` dijalankan — CHECK constraint SQLite tidak bisa diubah dengan ALTER, jadi tabel `stock_movements` dibuat ulang (tabel baru → salin data → hapus lama → ganti nama) dalam satu transaksi.

Perubahan v2:
- `stock_movements.kind` ditambah `opening_balance`, `adjustment_in`, `adjustment_out` (jenis lama tetap berlaku).
- Kolom baru `stock_movements.effective_date` (tanggal efektif mutasi, mis. saldo awal; kosong berarti berlaku `created_at`).
- Pemetaan data lama: `adjustment` + catatan diawali "Saldo awal" → `opening_balance`; `adjustment` positif → `adjustment_in`; negatif → `adjustment_out`; jenis lain tidak berubah.

## Skema v1 (tahap 3, 2026-11-25)

Versi skema dicatat di `PRAGMA user_version = 1`. Migrasi berikutnya harus menaikkan versi ini secara eksplisit.

| Tabel | Isi |
|---|---|
| `users` | Pengguna tenant: username unik, `password_hash` (Werkzeug/scrypt), `full_name`, role (`owner`/`admin`/`cashier`), `outlet_id`, `is_active` |
| `outlets` | Outlet/cabang tenant |
| `categories` | Kategori produk |
| `units` | Satuan produk (pcs, kg, liter, dus, …) |
| `products` | SKU unik, barcode, nama, kategori, satuan, harga beli/jual, `min_stock` |
| `stock` | Stok per produk × outlet (primary key gabungan) |
| `customers` | Pelanggan |
| `suppliers` | Pemasok |
| `sales` + `sale_items` | Penjualan dan rincian barangnya |
| `purchases` + `purchase_items` | Pembelian dan rincian barangnya |
| `stock_movements` | Riwayat perubahan stok (v2: sale/purchase/adjustment/return/transfer/opening_balance/adjustment_in/adjustment_out + `effective_date`) — sumber audit |
| `cash_transactions` | Pemasukan/pengeluaran kas di luar penjualan & pembelian |

Aturan: uang disimpan sebagai INTEGER (rupiah) untuk menghindari kesalahan pembulatan float; foreign key aktif (`PRAGMA foreign_keys = ON`); indeks pada `products.category_id`, `stock.outlet_id`, `sales(outlet_id, created_at)`, `sale_items.sale_id`, dan `stock_movements(product_id, created_at)`.

## Ketentuan desain

- Tenant tidak boleh dapat membaca atau mengubah database tenant lain.
- Identitas tenant harus divalidasi pada setiap permintaan yang memerlukan data tenant.
- Operasi transaksi dan stok harus konsisten.
- Perubahan skema database harus memiliki mekanisme migrasi yang aman.
- Backup dan pemulihan harus memperhitungkan database setiap tenant.
- Jangan menganggap struktur aktual sama dengan contoh ini sebelum memeriksa repository/kode aktual.

> Skema di atas adalah skema awal (v1) yang dibuat pada tahap 3 — isi tabelnya mengikuti peta modul di dokumen induk, bukan dari sistem yang sudah berjalan sebelumnya. Perubahan kolom/tabel berikutnya adalah migrasi, bukan edit diam-diam.
