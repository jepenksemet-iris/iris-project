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
