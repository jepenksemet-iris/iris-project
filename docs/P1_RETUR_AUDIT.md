# Audit Retur — P1 Tahap 7 (2026-11-25)

Audit read-only terhadap skema v5 + kode Tahap 3/5/6 sebelum implementasi retur.

## Temuan

- **Skema v5** (`SCHEMA_VERSION = 5`): 15 tabel. `sales` punya status
  `CHECK ('completed','pending','void','returned')` — status `returned`
  sudah dicadangkan tapi belum pernah dipakai. `purchases` punya status
  yang sama (`ordered/received/returned/cancelled`). `sale_items` dan
  `purchase_items` sudah menyimpan snapshot `product_name`/`sku`/`unit`
  dan harga historis (`price`, plus `discount` di `sale_items`).
- **Ledger**: `stock_movements.kind` sudah memuat `'return'` (belum
  pernah dipakai — dicadangkan untuk retur penjualan). Jenis untuk
  retur pembelian (`purchase_return`) belum ada → ditambah di migrasi v6.
  Stok hanya berubah lewat `_apply_stock_change()`; `reconcile_stock()`
  tersedia untuk verifikasi.
- **Pembatalan**: `void_sale()` (status `completed`/`pending`, mutasi
  `sale_void`) dan `cancel_purchase()` (status `received`, mutasi
  `purchase_void`, tolak bila stok tidak cukup). Keduanya **tidak**
  memperhitungkan retur — penjualaan/pembelian yang sudah diretur
  sebagian lalu dibatalkan akan mengembalikan stok dua kali. Maka
  pembatalan diblokir bila ada retur yang sudah diproses.
- **Pembayaran**: `sales.paid` + `sale_payments`; tidak ada mekanisme
  refund/utang yang bisa diaudit. Nilai retur dicatat sebagai informasi;
  pengembalian uang **tidak** otomatis (ditandai jelas di UI + dokumen).
- **Stok rusak/karantina**: tidak ada konsepnya di skema. Retur
  penjualan selalu menambah stok tersedia (barang layak jual). Barang
  rusak dicatat sebagai batasan, bukan kategori stok baru.
- **Pola yang dipakai ulang**: transaksi `BEGIN IMMEDIATE` + idempotensi
  token/hash (seperti `create_sale`), validasi server, CSRF, role
  owner/admin untuk aksi yang mengubah stok/uang, `VoidForm` untuk
  alasan pembatalan.

## Rancangan (Tahap 7)

- Tabel baru `returns` (kind `sale_return`/`purchase_return`, nomor
  `RS-YYYYMMDD-NNNN` / `RP-YYYYMMDD-NNNN`, status `completed`/
  `cancelled`, alasan wajib, total dari harga historis asal,
  `idempotency_key` UNIQUE) + `return_items` (snapshot + qty + harga).
- Retur penjualan: stok masuk `kind='return'`; retur pembelian: stok
  keluar `kind='purchase_return'` (baru di v6). Pembatalan retur:
  mutasi kompensasi dengan `ref_type='return_void'`.
- Batas kuantitas: kumulatif retur per produk tidak boleh melebihi
  kuantitas asal dikurangi retur terdahulu yang sudah diproses.
- Status asal: penjualan/pembelian yang diretur **penuh** menjadi
  `returned`; retur sebagian tidak mengubah status asal.
- Tidak ada draft retur: retur langsung diproses saat disimpan.
