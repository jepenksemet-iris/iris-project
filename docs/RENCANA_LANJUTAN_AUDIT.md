# Audit Fondasi — Rencana Lanjutan (Tahap 1, 2026-11-25)

Audit read-only terhadap repo (head `45e2ed75`, skema v6) sebelum
membangun laporan, keuangan dasar, dan PO draft.

## Baseline terverifikasi

- **Tes: 101 passed** (`pytest tests/ -q`, Python 3.12.3) — tidak ada
  kegagalan sebelum perubahan.
- **Skema v6, 17 tabel**: users, outlets, categories, units, products,
  stock, customers, suppliers, sales, sale_items, sale_payments,
  purchases, purchase_items, stock_movements, cash_transactions,
  returns, return_items.
- **Ledger adalah satu-satunya jalur perubahan stok.** Satu-satunya
  penulisan langsung ke tabel `stock` ada di `_apply_stock_change()`
  (UPSERT, `iris_db.py:711`); semua alur — checkout (`sale`),
  pembelian (`purchase`), penyesuaian, saldo awal, void (`sale_void` /
  `purchase_void`), retur (`return` / `purchase_return`) — memanggilnya
  dan selalu menyisipkan mutasi ledger dalam transaksi yang sama.
  `reconcile_stock()` tersedia untuk verifikasi saldo vs ledger.
- **Fungsi daftar yang bisa dipakai laporan sudah ada**: `list_sales`
  (cari nomor/tanggal/status/metode/urut), `list_purchases`,
  `list_returns`, `list_stock_movements` (produk/jenis/tanggal),
  `list_products`, `get_sale`/`get_purchase`/`get_return` (detail +
  snapshot item).
- **Status yang dipakai laporan**: penjualan
  `completed/pending/void/returned`; pembelian
  `ordered/received/returned/cancelled`; retur `completed/cancelled`.
  Pembatalan bukan refund: `sales.paid` dan `sale_payments` tetap
  tercatat; tidak ada status `refunded` palsu.

## Yang belum ada ( diverifikasi, bukan asumsi)

- **Laporan**: tidak ada route, template, atau query laporan
  (`/reports`, `/laporan` tidak ditemukan). Ringkasan usaha,
  laporan penjualan/pembelian/stok/retur semuanya belum ada.
- **Keuangan**: tidak ada tabel refund, utang, atau pembayaran utang.
  `cash_transactions` ada di skema (kind `income`/`expense`) tetapi
  **tidak dipakai oleh kode mana pun** — tidak ada route/service yang
  membaca atau menulisnya. Modul keuangan harus merancang tabelnya
  sendiri (atau mengadopsi `cash_transactions` secara sadar), bukan
  mengasumsikannya sudah berfungsi.
- **PO draft**: tidak ada tabel/route. `purchases.status` memuat
  `'ordered'` tetapi tidak pernah dipakai — pembelian selalu dibuat
  langsung `received`.

## Risiko & keputusan desain yang dicatat

- **Definisi metrik laporan harus ditulis dulu** (penjualan kotor vs
  bersih, perlakuan diskon/retur/pembatalan, status `pending` yang
  belum terverifikasi) sebelum membangun halaman laporan — angka yang
  tidak bisa ditelusuri ke transaksi sumber tidak boleh ditampilkan.
- **Zona waktu**: semua `created_at` memakai `datetime('now')` (UTC
  SQLite). Filter tanggal laporan harus konsisten (UTC) dan
  didokumentasikan; jangan mencampur zona waktu lokal.
- **Uang selalu INTEGER rupiah** di seluruh skema — laporan dan
  keuangan wajib mempertahankannya (tanpa float).
- **Urutan yang disarankan dokumen rencana**: Laporan (P1) → Keuangan
  dasar (P1) → PO draft (P2) → penyempurnaan/rekonsiliasi (P2).
  Laporan tidak membutuhkan migrasi skema (baca data yang sudah ada);
  keuangan dan PO membutuhkan migrasi v7+.

## File yang akan terdampak tahap berikutnya

- Laporan: `tenant_app.py` (route `/reports/...`), template baru
  `templates/reports/`, tes baru `tests/test_reports.py` — tanpa
  perubahan skema.
- Keuangan: `iris_schema.sql` + `iris_db.py` (migrasi v7, tabel
  refund/utang + pembayaran), route/template baru, tes baru.
- PO draft: `iris_schema.sql` + `iris_db.py` (migrasi, tabel PO +
  item + status), route/template baru, tes baru.
