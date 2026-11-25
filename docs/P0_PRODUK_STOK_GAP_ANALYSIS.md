# Gap Analysis — Spesifikasi P0 Modul Produk & Stok vs Implementasi Tahap 6

> **Dokumen acuan:** spesifikasi "IRIS — P0: Modul Produk & Stok" (diunggah pemilik 2026-11-25).
> **Implementasi yang diaudit:** tahap 6 di `~/workspace/iris-project`, belum di-push (head remote `ffd0b631`, tahap 5). Audit read-only 2026-11-25.
> **Kesimpulan singkat:** fondasi tahap 6 sudah memenuhi sebagian besar P0. Sisa gap terbesar adalah **jenis mutasi saldo awal** (skema v1 tidak mengenal `opening_balance` / `adjustment_in` / `adjustment_out`) dan **pencegahan saldo awal ganda** — keduanya butuh keputusan pemilik sebelum dikerjakan, karena yang pertama menyentuh skema database.
>
> **Update tahap 7 (2026-11-25, Paket B — diputuskan pemilik):** semua gap di bawah ditutup dengan migrasi skema v2. Status per kriteria diperbarui di §2; keputusan pemilik dicatat di §5.

## 1. Temuan audit skema (spesifikasi §2–§5)

| Nama di spesifikasi | Kondisi aktual di `iris_schema.sql` (v1) | Keputusan |
|---|---|---|
| `products` | Ada (sku, barcode, nama, category_id, unit_id, buy_price, sell_price, min_stock, is_active) | Pakai yang ada |
| `product_units` | **Tidak ada.** Yang ada: `units` (id, name UNIQUE) | Jangan buat duplikat — pakai `units` |
| `product_stocks` | **Tidak ada.** Yang ada: `stock` (product_id, outlet_id, qty; PK komposit) | Jangan buat duplikat — pakai `stock` |
| `stock_movements` | Ada (product_id, outlet_id, qty, kind, ref_type, ref_id, note, user_id, created_at) | Pakai yang ada |
| `categories`, `outlets`, `users` | Ada | Pakai yang ada |
| Merek, gudang terpisah, audit log | Tidak ada (outlet berperan sebagai gudang/lokasi) | Di luar P0 / keputusan produk |

**Jenis mutasi di skema v1:** `kind CHECK (kind IN ('sale', 'purchase', 'adjustment', 'return', 'transfer'))`.
Spesifikasi §P0.5 meminta minimal `opening_balance`, `adjustment_in`, `adjustment_out` — **ketiganya tidak ada di CHECK constraint v1**. Menambahkannya = migrasi skema v2 (`PRAGMA user_version = 2`, ALTER/CREATE ulang CHECK) + migrasi database tenant lama. Spesifikasi sendiri mengizinkan "tipe ekuivalen yang mengikuti konvensi database saat ini" (§P0.4 aturan 1) — saat ini ekuivalennya adalah `kind='adjustment'` + `note='Saldo awal'`.

## 2. Kriteria penerimaan P0 (§9) — status per poin

| # | Kriteria | Status | Bukti / gap |
|---|---|---|---|
| 1 | Audit skema & struktur selesai; tidak ada tabel duplikat | ✅ Terpenuhi (dokumen ini) | `units`/`stock` dipakai, `product_units`/`product_stocks` tidak dibuat |
| 2 | Tenant dapat melihat daftar dan mencari produk | ✅ Terpenuhi | `GET /products`, cari SKU/nama, `tests/test_products_stock.py::test_create_and_list_product` |
| 3 | Tenant dapat menambah produk dengan validasi server | ✅ Terpenuhi | `ProductForm` + `create_product()`; SKU duplikat ditolak (tes) |
| 4 | Tenant dapat mengedit produk tanpa merusak histori | ✅ Terpenuhi (tahap 7) | Edit + arsip teruji; ganti satuan kini ditolak bila produk sudah punya stok/mutasi (`update_product()`, teruji) |
| 5 | Tenant dapat memasukkan saldo awal per produk & gudang | ✅ Terpenuhi (tahap 7) | Form jenis mutasi "Saldo awal" + tanggal efektif (`effective_date`); jenis `opening_balance` (skema v2); duplikat per produk×outlet ditolak (`record_opening_balance()`, teruji) |
| 6 | Saldo awal selalu memiliki catatan ledger | ✅ Terpenuhi | `adjust_stock()` atomik: ubah `stock` + tulis `stock_movements` satu transaksi |
| 7 | Mutasi masuk/keluar tercatat dengan referensi, waktu, pengguna | ✅ Terpenuhi (tahap 7) | Waktu, pengguna, keterangan, tanggal efektif tercatat; tampilan kartu stok punya kolom masuk/keluar + saldo berjalan; filter jenis + rentang tanggal. `ref_type`/`ref_id` masih kosong (belum ada transaksi sumber — kasir/pembelian belum ada) |
| 8 | Saldo tidak dapat menjadi negatif melalui alur normal | ✅ Terpenuhi | `adjust_stock()` menolak hasil negatif; teruji (`test_stock_cannot_go_negative`) |
| 9 | Saldo terkini konsisten dengan ledger | ✅ Terpenuhi (tahap 7) | `reconcile_stock()` + tes rekonsiliasi dan atomicity (trigger) di `test_reconciliation_and_atomicity` |
| 10 | Mutasi yang sudah diposting tidak dapat diubah/hapus diam-diam | ✅ Terpenuhi | Tidak ada route/template untuk edit/hapus mutasi |
| 11 | Isolasi tenant dan permission teruji | ✅ Terpenuhi | Kasir 403 untuk kelola produk/stok; produk tenant A tak terlihat di tenant B (tes) |
| 12 | Pengujian baru + seluruh regresi lulus | ✅ Terpenuhi | `pytest`: 16 passed (10 lama + 6 baru) |
| 13 | Tidak ada perubahan file rahasia / data tenant nyata | ✅ Terpenuhi | Tes memakai `tmp_path`; tidak ada `.env`/DB produksi disentuh |
| 14 | Ringkasan, file, migrasi, hasil tes, risiko disampaikan | ✅ Terpenuhi (tahap 7) | Dokumen ini + CHANGELOG tahap 7; 25 tes lolos |

## 5. Keputusan pemilik (ditetapkan 2026-11-25 — Paket B)

1. Jenis mutasi saldo awal: **(B) migrasi v2** ke `opening_balance` / `adjustment_in` / `adjustment_out` — diterapkan di tahap 7.
2. Satuan dasar produk: **wajib** — diterapkan di tahap 7 (`ProductForm.unit` kini `DataRequired`).
3. Pagination daftar produk: **tidak dibuat** — pola ini belum dipakai aplikasi mana pun, sesuai spesifikasi §P0.1 ("jika pola tersebut sudah digunakan").
4. Push tahap 6: **tidak di-push terpisah** — tahap 6 + tahap 7 di-push bersama sebagai satu commit setelah gap ditutup.

## 3. Gap detail (di luar tabel di atas)

> **Update tahap 7:** gap 1–8 di bawah ini sudah ditutup, kecuali `ref_type`/`ref_id` (baru terisi saat kasir/pembelian ada) dan pagination (diputuskan tidak dibuat). Daftar ini dipertahankan sebagai catatan audit.

1. **Jenis mutasi saldo awal.** Skema v1 hanya mengenal `adjustment`. Opsi: (A) tetap `adjustment` + note "Saldo awal" (tanpa migrasi, sesuai klausul "tipe ekuivalen" spesifikasi); (B) migrasi v2 menambah `opening_balance`, `adjustment_in`, `adjustment_out` ke CHECK `stock_movements.kind` (perlu migrasi DB lama + tes migrasi).
2. **Saldo awal ganda.** Tidak ada pencegahan input saldo awal kedua untuk produk×outlet yang sama. Opsi: (A) tolak penyesuaian ber-note "Saldo awal" kedua bila sudah ada mutasi saldo awal untuk produk×outlet itu (tanpa migrasi); (B) aturan periode/inisialisasi formal (butuh kolom periode — di luar P0 minimal).
3. **Filter daftar produk.** Belum ada filter kategori (spesifikasi: "jika struktur mendukung" — struktur mendukung, `category_id` ada). Belum ada pagination (pola ini belum dipakai aplikasi mana pun; daftar memakai LIMIT implisit sebelumnya 100 — tahap 6 menghapus limit itu, daftar kini tanpa batas; perlu diputuskan: kembalikan limit 100 + pagination, atau biarkan).
4. **Indikator stok habis/rendah.** `min_stock` bisa diisi lewat form, tapi daftar produk tidak menampilkan peringatan stok ≤ minimum.
5. **Satuan dasar wajib.** Spesifikasi §P0.2: satuan dasar wajib dan mengacu satuan valid. Form tahap 6 menjadikan satuan opsional (teks bebas, dibuat otomatis bila baru). Perlu diputuskan: wajibkan satuan (default "pcs" bila kosong?) atau biarkan opsional.
6. **Stok minimum di form wajib diisi.** Spesifikasi: opsional. Form tahap 6 memakai `DataRequired` — pengguna harus mengisi (0 bila tidak ada). Kecil, tapi menyimpang dari spesifikasi.
7. **Ledger: filter & kolom.** Halaman stok menampilkan mutasi per produk saja — belum ada filter jenis/tanggal, kolom masuk/keluar terpisah, dan saldo berjalan per baris.
8. **Tes yang diminta spesifikasi §8 tapi belum ada:** nama kosong ditolak; SKU sama saat edit diperbolehkan; edit tidak mengubah ID; kegagalan simpan mutasi membatalkan saldo (dan sebaliknya — atomicity failure test); POST tanpa CSRF ditolak; input SQL berbahaya diperlakukan sebagai data; rekonsiliasi ledger == saldo.

## 4. Rencana perubahan minimal (menunggu persetujuan)

**Paket A — tanpa migrasi skema (disarankan dulu):**
- `iris_db.py`: `adjust_stock()` tambah parameter `is_opening_balance` → tolak bila sudah ada mutasi saldo awal untuk produk×outlet (gap 2, opsi A); fungsi `reconcile_stock()` (jumlah mutasi vs saldo `stock`).
- `tenant_app.py` + template: filter kategori di `/products`; indikator stok rendah/habis di daftar; larang ganti satuan bila produk sudah punya stok > 0 atau mutasi (gap 4); form saldo awal khusus (tanggal efektif dicatat di `note` + `created_at` tidak diubah — tanggal efektif eksplisit butuh kolom baru, jadi dicatat sebagai keterangan bila tanpa migrasi).
- `forms.py`: `min_stock` jadi opsional (default 0); satuan tetap opsional **atau** wajib — sesuai keputusan pemilik (gap 5).
- `tests/test_products_stock.py`: tambah tes nama kosong, SKU sama saat edit, atomicity failure (mock gagal di tengah), rekonsiliasi, CSRF ditolak (aktifkan CSRF di tes khusus), SQL injection sebagai data.
- Dokumen: perbarui `docs/CHANGELOG.md`, `README.md`, matriks iPOS 4.

**Paket B — dengan migrasi skema v2 (hanya bila pemilik memilih):**
- `iris_schema.sql` + migrasi: `user_version = 2`; CHECK `kind` ditambah `opening_balance`, `adjustment_in`, `adjustment_out`; migrasi data lama (`adjustment` + note "Saldo awal" → `opening_balance`) diuji di DB sementara.
- `adjust_stock()` memakai jenis baru; saldo awal memakai `opening_balance`; penyesuaian memakai `adjustment_in`/`adjustment_out`.
- Risiko: database tenant yang sudah ada harus dimigrasi; CHECK constraint SQLite tidak bisa diubah dengan ALTER sederhana — perlu buat ulang tabel (backup dulu, uji di DB sementara).

**Tidak dikerjakan dalam P0 ini (sesuai spesifikasi §11):** kasir, pembayaran/diskon/pajak/struk, pembelian lengkap, retur, transfer antar-gudang, batch/serial/kedaluwarsa, marketplace, AI/OCR.

## 5. Keputusan yang diminta dari pemilik

1. Jenis mutasi saldo awal: **(A)** tetap `adjustment` + keterangan (tanpa migrasi) atau **(B)** migrasi v2 ke `opening_balance` / `adjustment_in` / `adjustment_out`?
2. Satuan dasar produk: wajib (dengan default bila kosong?) atau tetap opsional?
3. Pagination daftar produk: kembalikan batas 100 + pagination, atau biarkan tanpa batas untuk sekarang?
4. Apakah tahap 6 (yang sudah jadi) boleh di-push apa adanya dulu, atau tunggu sampai gap Paket A selesai?
