# Laporan — Definisi Metrik & Aturan (P1, 2026-11-25)

Laporan hanya **membaca** data transaksi yang sudah ada. Tidak ada
migrasi skema untuk modul laporan.

## Zona waktu

- Semua `created_at` memakai `datetime('now')` = **UTC**.
- Filter tanggal memakai kalender UTC dengan rentang half-open:
  `created_at >= 'YYYY-MM-DD 00:00:00' AND created_at < 'YYYY-MM-DD+1 00:00:00'`
  (batas awal inklusif, batas akhir eksklusif). Transaksi tepat pukul
  00:00:00 di tanggal akhir **tidak** masuk; transaksi 23:59:59 masuk.
- Tanggal yang tidak valid diabaikan (batas itu tidak dipakai).
- Rentang default: bulan berjalan (UTC).

## Definisi metrik

- **Penjualan kotor** = Σ `total` penjualan berstatus `completed` /
  `returned` (transaksi aktif) dalam rentang.
- **Diskon** = Σ `discount` transaksi aktif dalam rentang.
- **Nilai retur penjualan** = Σ `total` retur kind `sale_return`
  berstatus `completed` dalam rentang.
- **Penjualan bersih** = kotor − nilai retur penjualan.
- **Nilai pembatalan penjualan** = Σ `total` penjualan berstatus
  `void` dalam rentang — ditampilkan terpisah, **tidak** mengurangi
  kotor karena transaksi batal memang tidak dihitung sebagai
  penjualan aktif.
- **Pembelian** = Σ `total` pembelian berstatus `received` /
  `returned`; **nilai retur pembelian** = Σ `total` retur kind
  `purchase_return` completed; **pembelian bersih** = pembelian −
  nilai retur pembelian; pembatalan pembelian (`cancelled`)
  ditampilkan terpisah.
- **Pembayaran per metode** = Σ `sales.paid` per `payment_method`
  untuk transaksi aktif. Non-tunai `pending` bernilai 0 sampai
  owner/admin mengonfirmasi (saat itu `paid` menjadi total).
- **Stok**: saldo adalah saldo **saat ini**; kolom Masuk/Keluar
  dihitung dari ledger `stock_movements` pada rentang (sumber
  kebenaran stok). Indikator Habis (saldo ≤ 0) / Rendah
  (saldo ≤ `min_stock`).
- **Retur bukan refund**: nilai retur adalah informasi transaksi;
  pengembalian uang belum diproses otomatis (modul keuangan belum
  ada). Status pembayaran/utang pembelian belum tersedia.

## Yang sengaja tidak ada

- **Laporan laba/rugi**: tidak ditampilkan — komponen biaya dan
  metode perhitungannya belum tersedia. Omzet bukan laba.
- Laporan hutang/piutang dan laporan keuangan (buku besar/neraca):
  belum ada — menunggu modul keuangan.
