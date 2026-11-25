# P1 Tahap 4 — Audit Integrasi Ledger & Riwayat Penjualan

Audit read-only atas implementasi Tahap 3 (commit `1a221766`, skema v3),
dilakukan 2026-11-25 sebelum pekerjaan Tahap 5. Sumber kebenaran adalah
kode dan tes aktual di repo, bukan dokumen rencana.

## 1. Integrasi checkout ↔ ledger (Tahap 3)

### Sudah benar dan terbukti oleh kode/tes

| Pernyataan | Bukti |
|---|---|
| Setiap item checkout menghasilkan tepat satu mutasi `sale` | `iris_db.create_sale()` memanggil `_apply_stock_change(..., kind="sale", ref_type="sale", ref_id=sale_id)` sekali per baris keranjang, di dalam transaksi yang sama. `tests/test_checkout.py::test_cash_exact_payment` menegaskan 1 mutasi qty −2 untuk 2 item. |
| Kuantitas mutasi = kuantitas item | Sama seperti di atas; mutasi memakai `-line["qty"]` dari hasil `summarize_cart()` yang sama dengan yang ditulis ke `sale_items`. |
| Referensi dapat ditelusuri | `stock_movements.ref_type='sale'`, `ref_id`=id penjualan; catatan berisi nomor invoice (`"Penjualan INV-..."`). |
| Saldo stok berubah sesuai aturan modul stok | Stok diubah hanya lewat `_apply_stock_change()` (UPSERT tabel `stock` + baris ledger dalam satu langkah); tidak ada `UPDATE stock` lain dari jalur kasir. Stok negatif ditolak sebelum tulis. |
| Semua dalam satu transaksi atomik | `create_sale()` memakai `BEGIN IMMEDIATE` ... `COMMIT`, `ROLLBACK` di `except`. `adjust_stock()` memakai `with conn:` dan TIDAK dipanggil di dalam checkout (inti `_apply_stock_change()` yang dipakai, tanpa commit sendiri). |
| Checkout gagal = rollback penuh | `tests/test_checkout.py::test_rollback_on_ledger_failure` (trigger `RAISE(ABORT)` pada insert `stock_movements` kind='sale'): tidak ada sale, tidak ada `sale_payments`, tidak ada mutasi, stok tetap. |
| Request ulang tidak menggandakan mutasi | Token idempotensi + hash payload (`idempotency_key UNIQUE`); replay mengembalikan sale lama tanpa tulis baru. `test_idempotency_same_token_once` menegaskan 1 sale + stok berkurang sekali. Token sama + payload berbeda ditolak. |
| Checkout bersamaan tidak merusak stok | `BEGIN IMMEDIATE` menyerikan penulis; `test_concurrent_last_stock`: 2 thread untuk stok terakhir → tepat 1 berhasil, stok akhir 0. |
| Tidak ada sistem pengurangan stok kedua | Satu-satunya penulis stok dari kasir adalah `_apply_stock_change()` lewat `create_sale()`. |
| Rekonsiliasi saldo vs ledger | `iris_db.reconcile_stock()` membandingkan `stock.qty` dengan jumlah `stock_movements`; dipakai di tes produk/stok. |

### Sudah ada tetapi belum diuji (ditambah pada Tahap 4/5)

- Checkout beberapa item sekaligus: kuantitas mutasi per item — belum ada tes multi-item eksplisit (baru 1 item per tes checkout). Ditambah `tests/test_void.py::test_multi_item_checkout_ledger_matches_items`.

### Kesimpulan Tahap 4

Integrasi ledger Tahap 3 sudah benar dan terbukti; **tidak ada perubahan
kode integrasi yang diperlukan**. Tahap 4 dinyatakan selesai melalui
audit ini + tes tambahan di atas. Satu-satunya perubahan skema yang
dibutuhkan adalah untuk Tahap 5 (lihat §3).

## 2. Audit riwayat / detail / struk (sebelum Tahap 5)

| Fitur | Kondisi | Tindakan Tahap 5 |
|---|---|---|
| `GET /sales` — cari invoice, filter tanggal/status, batas 100 | Ada dan berfungsi (`tests/test_checkout.py::test_history_list_detail_receipt`) | Dilengkapi: filter metode pembayaran, pilihan urut terbaru/terlama, validasi filter tidak valid (diabaikan dengan aman, tidak crash/tidak menampilkan data tenant lain) |
| `GET /sales/<id>` — snapshot item, total, pembayaran, kembalian | Ada dan berfungsi; snapshot bertahan setelah edit produk (tes) | Dilengkapi: status pembayaran turunan (Lunas / Belum terverifikasi), kolom diskon item, info pembatalan (alasan, oleh, waktu), form pembatalan untuk owner/admin |
| `GET /sales/<id>/receipt` — `@media print` | Ada; data dari transaksi tersimpan | Dilengkapi: tanda **DIBATALKAN** untuk transaksi batal, alamat/telepon outlet |
| Pembatalan penjualan | **Belum ada** (hanya kolom `void_*` di skema v3) | Diimplementasikan (lihat §3) |

## 3. Pembatalan (Tahap 5)

- Service: `iris_db.void_sale(conn, sale_id, user_id, reason)` — atomik
  (`BEGIN IMMEDIATE`): validasi status (`completed`/`pending` saja),
  alasan wajib, cegah pembatalan ganda (status + pemeriksaan mutasi
  pembalik), tulis `void_reason`/`voided_by`/`voided_at`, lalu satu
  mutasi pembalik per item.
- Jenis mutasi pembalik: **`sale_void`** (baru di skema v4, lihat
  `docs/DATABASE.md`). Mutasi `sale` asli, `sale_items`, dan
  `sale_payments` asli **tidak** dihapus/diubah.
- Otorisasi: hanya owner/admin (`@require_role`), CSRF, alasan wajib
  (maks. 500 karakter), route `POST /sales/<id>/void`.
- Kebijakan pembayaran/refund: pembatalan **bukan** pengembalian uang.
  `sales.paid` dan `sale_payments` tetap tercatat apa adanya; tidak ada
  status `refunded` yang dipalsukan. Pengembalian uang (jika ada)
  adalah proses terpisah dan belum diimplementasikan — detail transaksi
  batal menampilkan peringatan ini.
- Pembatalan transaksi `pending` (non-tunai belum terverifikasi) juga
  mengembalikan stok, karena barang sudah diserahkan.
- Tidak ada batas waktu pembatalan yang diarang — tidak ada konfigurasi
  batas waktu di proyek; pembatalan selalu diizinkan selama status
  memenuhi syarat (retur sebagian adalah tahap terpisah).
