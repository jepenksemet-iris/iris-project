# Arsitektur Informasi & UX POS IRIS

> **Status:** rancangan UX berdasarkan dokumen benchmark iPOS 4 ("Riset Menu, Fitur, dan UX iPOS 4 untuk Pengembangan POS IRIS") dan audit repository `iris-project` head `71ef6ec0` (2026-11-25).
>
> **Yang sudah ada saat dokumen ini ditulis:** landing page (tahap 4), autentikasi tenant + role (tahap 3), skema DB v1 14 tabel, daftar produk baca saja. Semua menu di bawah ini **kecuali yang ditandai "Sudah Ada"** adalah rancangan — bukan klaim fitur selesai. Lihat `docs/IPOS4_FEATURE_MATRIX.md` untuk status per fitur dengan bukti.
>
> **Prinsip (dari benchmark §15):** task-first · progressive disclosure · interaksi konsisten · operasi cepat (kasir) · safe by default · responsif · aksesibel · dapat ditelusuri · feedback jelas · role-aware (otorisasi tetap diperiksa server).

## 1. Sitemap — aplikasi tenant

```
Tenant App (port 5001, login wajib)
├── /login, /logout                                   [Sudah Ada]
├── /  Dashboard (per role, §3)
├── /kasir  Kasir / POS                               [Belum Ada — P0]
│   ├── /kasir (transaksi berjalan)
│   ├── /penjualan (daftar penjualan)
│   ├── /penjualan/baru (back-office)
│   ├── /penjualan/pesanan (sales order)             [P1]
│   ├── /penjualan/retur                             [P0]
│   └── /piutang (pembayaran piutang)                [P0]
├── /produk                                           [Parsial — daftar baca saja Sudah Ada]
│   ├── /produk (daftar + cari + filter)
│   ├── /produk/baru, /produk/<id>/edit
│   ├── /kategori, /merek, /satuan
│   └── /produk/barcode (cetak label)                [Perlu Keputusan]
├── /pembelian                                         [Belum Ada — P0]
│   ├── /pembelian (daftar)
│   ├── /pembelian/baru (penerimaan)
│   ├── /pembelian/pesanan (PO)
│   ├── /pembelian/retur
│   ├── /supplier
│   └── /hutang (pembayaran hutang)
├── /persediaan                                        [Belum Ada — P0/P1]
│   ├── /persediaan (ringkasan stok per outlet)
│   ├── /persediaan/kartu-stok
│   ├── /persediaan/mutasi
│   ├── /persediaan/transfer                          [P1]
│   ├── /persediaan/opname                            [P1]
│   ├── /persediaan/penyesuaian                       [P1]
│   ├── /persediaan/masuk, /persediaan/keluar         [P1]
│   └── /persediaan/stok-minimum                      [P1]
├── /pelanggan                                         [Belum Ada — P0 dasar]
│   ├── /pelanggan (daftar + tambah/edit)
│   ├── /pelanggan/grup, /pelanggan/poin             [P2]
│   └── /supplier (tautan ke /pembelian/supplier)
├── /keuangan                                          [Belum Ada — P1/P2]
│   ├── /keuangan (ringkasan kas & bank)
│   ├── /keuangan/kas-masuk, /keuangan/kas-keluar, /keuangan/transfer
│   ├── /keuangan/hutang, /keuangan/piutang
│   └── /keuangan/akun, /keuangan/jurnal             [P2]
├── /laporan                                           [Belum Ada — P1/P2]
│   ├── /laporan/penjualan, /laporan/pembelian, /laporan/persediaan
│   ├── /laporan/hutang, /laporan/piutang, /laporan/kas
│   └── /laporan/laba-rugi, /laporan/neraca          [P2]
└── /pengaturan                                        [Parsial — role Sudah Ada]
    ├── /pengaturan/profil-usaha                      [P1]
    ├── /pengaturan/outlet
    ├── /pengaturan/pengguna                          [P0 — UI kelola user]
    ├── /pengaturan/role
    ├── /pengaturan/printer                           [P1]
    ├── /pengaturan/import                            [P1]
    └── /pengaturan/backup                            [P0 — backup teruji]

Landing App (port 5000, publik) — Sudah Ada (tahap 4)
└── / (hero, fitur, harga, FAQ, footer), /register (via WhatsApp)

Super Admin App (port 5002, TERPISAH — tanpa auth, jangan diekspos)
└── / (dashboard platform), /tenant, /provisioning, /paket, /monitoring
    [Belum Ada — jangan tampilkan menu ini kepada pengguna tenant]
```

**Yang sengaja TIDAK ditiru dari iPOS 4:** menu Konsinyasi (historis/opsional, perlu keputusan), Proses Data bulanan/tahunan manual (diganti ledger real-time + tutup periode opsional P2), ribbon dengan banyak ikon (diganti sidebar, §2), tema/background aplikasi.

## 2. Struktur navigasi — sidebar + topbar

**Pola yang dipilih:** sidebar kiri (desktop) yang menyusut jadi menu bawah / hamburger (tablet/ponsel), + topbar. Alasan: pola ini sudah dikenal pengguna web modern, muat 10 kelompok menu tanpa ribbon yang membebani pengguna baru, dan konsisten dengan pola halaman daftar (§4).

- **Sidebar:** logo POS IRIS → pemilih outlet aktif → kelompok menu (§1) → pengguna login + peran → keluar. Menu yang tidak diizinkan role-nya **tidak ditampilkan**, tetapi route-nya tetap diperiksa server (`require_role` / `login_required`).
- **Topbar:** judul halaman + breadcrumb (§4) → pencarian global (produk/transaksi, P1) → tombol aksi utama halaman → avatar/pengguna.
- **Kasir adalah pengecualian:** layout kasir memakai topbar minimal + area kerja penuh (§6), bukan sidebar penuh, supaya keranjang dan total selalu terlihat.
- **Mobile:** sidebar jadi drawer (tombol hamburger, `aria-expanded`, fokus keyboard terlihat); kasir jadi satu kolom: pencarian di atas, keranjang di bawah, total menempel di bawah layar (sticky).

## 3. Dashboard per role

Dashboard menampilkan **hanya KPI yang dapat dihitung secara benar** dari data yang ada, lengkap dengan periode dan sumber data. Angka tanpa sumber tidak ditampilkan.

| Role | Kartu utama | Alasan |
|---|---|---|
| Owner | Omzet hari ini + jumlah transaksi; produk terlaris; stok menipis; hutang/piutang jatuh tempo; grafik penjualan 7/30 hari; performa per outlet | Keputusan bisnis harian |
| Admin | Seperti owner, ditambah aktivitas terbaru (siapa mengubah apa) dan status sistem | Operasional + pengawasan |
| Kasir | Ringkasan shift saya: transaksi, total penjualan, kas di laci (bila kas dikelola); produk favorit | Fokus kerja shift, tanpa data keuangan usaha |
| Gudang (role masa depan — saat ini belum ada di skema) | Stok minimum, penerimaan hari ini, transfer menunggu, opname terjadwal | Perlu Keputusan: tambah role gudang atau pakai admin? |

**Empty state dashboard:** bila tenant baru (belum ada transaksi), tampilkan panduan 3 langkah — tambah produk → tambah stok awal → buka kasir — bukan angka nol tanpa konteks.

## 4. Pola halaman daftar (referensi: daftar produk)

Semua halaman daftar (produk, supplier, pelanggan, transaksi) mengikuti **satu pola yang sama**, supaya pengguna hanya belajar sekali. Pola referensi pertama adalah daftar produk — sebelum mengubah banyak halaman, pola ini diimplementasikan di sana dan diuji konsistensinya.

1. Breadcrumb: `Produk / Daftar Produk`.
2. Judul + deskripsi singkat (1 kalimat).
3. Tombol aksi utama di kanan atas ("+ Tambah Produk") — sesuai hak akses.
4. Search bar (nama/SKU/barcode) + filter relevan (kategori, outlet, status aktif).
5. Filter tanggal bila berupa transaksi; filter outlet/gudang bila relevan. Filter lanjutan di panel "Filter lainnya".
6. Ringkasan di atas tabel bila bermanfaat (mis. "128 produk · total stok 1.240").
7. Tabel: kolom dapat diurutkan, pagination, status badge konsisten (Aktif/Nonaktif, Lunas/Belum Lunas, dll).
8. Aksi per baris sesuai hak akses (Lihat/Edit/Arsipkan). **Arsipkan, bukan Hapus**, untuk data yang sudah dipakai transaksi — hapus historis dilarang.
9. Empty state dengan CTA relevan ("Belum ada produk — Tambah produk pertama").
10. Loading state/skeleton, error state + tombol "Coba lagi".
11. Ekspor (CSV/XLSX) bila diizinkan.

## 5. Pola form transaksi

- Form dibagi section logis (mis. produk: Data Umum · Satuan · Harga · Lain-lain) — bukan satu formulir panjang.
- Fokus awal ke field paling sering dipakai; autocomplete produk/pelanggan/supplier; input barcode.
- Keyboard navigation + shortcut terdokumentasi di halaman kasir.
- Validasi inline **dan** validasi ulang di server; perhitungan total otomatis + preview diskon/biaya.
- Indikator stok tersedia saat memilih produk.
- Simpan draft bila sesuai; ringkasan sebelum finalisasi; konfirmasi sebelum transaksi final.
- Setelah berhasil: nomor transaksi + status, tanpa submit ganda (tombol dinonaktifkan saat proses, idempotency key di server bila diperlukan).
- Semua operasi stok/keuangan dalam **satu transaksi database**; setiap perubahan menulis `stock_movements` / audit log.

## 6. Pola halaman POS Kasir (prioritas tertinggi)

- Search/barcode selalu mudah dijangkau (fokus otomatis, shortcut `/`).
- Keranjang selalu terlihat; nama, harga, kuantitas, diskon, subtotal mudah dibaca; tombol tambah/kurang besar dan mudah disentuh.
- **Total pembayaran sangat menonjol**; metode pembayaran jelas (tunai/kredit); hitung uang kembali otomatis.
- Pelanggan umum sebagai opsi cepat (tanpa wajib memilih pelanggan).
- Produk favorit/sering dijual bila data mendukung.
- Alur pembayaran singkat; cetak struk setelah transaksi berhasil; **recovery bila printer gagal** (transaksi tetap tersimpan, struk dapat dicetak ulang).
- Proteksi transaksi ganda; penanganan koneksi terputus yang aman.
- **Offline mode tidak ditampilkan** sampai sinkronisasi + resolusi konflik benar-benar didukung.

## 7. Alur utama

- **Setup awal:** daftar (via WhatsApp, sampai provisioning mandiri ada) → buat owner (CLI saat ini, UI P0) → isi profil usaha + outlet → tambah kategori/satuan → tambah produk → isi saldo awal stok → buka kasir.
- **Pembelian sampai pembayaran:** PO (opsional) → penerimaan/pembelian (stok +1, hutang bila kredit) → pembayaran hutang (sisa berkurang) → retur bila perlu (stok −1, hutang dikoreksi).
- **Penjualan sampai pelunasan:** pesanan (opsional) → kasir/back-office (stok −1, piutang bila kredit) → pembayaran piutang → retur bila perlu (stok dikoreksi sesuai kondisi, piutang dikoreksi).
- **Transfer & opname:** transfer (asal −1, tujuan +1, satu transaksi DB) → opname (sistem vs fisik → selisih + alasan + persetujuan → mutasi penyesuaian).
- **Laporan & drill-down:** pilih laporan → filter periode/outlet → KPI ringkasan → tabel → klik baris untuk melihat transaksi sumber → ekspor.

## 8. Hak akses per menu dan aksi (rancangan — otorisasi diperiksa server)

| Menu / aksi | Owner | Admin | Kasir |
|---|---|---|---|
| Dashboard (semua KPI) | ✓ | ✓ | Ringkasan shift saja |
| Kasir | ✓ | ✓ | ✓ |
| Produk: lihat | ✓ | ✓ | ✓ |
| Produk: tambah/edit/arsip | ✓ | ✓ | — |
| Pembelian, Persediaan, Keuangan | ✓ | ✓ | — (lihat stok saja bila perlu) |
| Pelanggan: lihat/tambah | ✓ | ✓ | ✓ (tambah saat transaksi) |
| Laporan keuangan (laba rugi, neraca) | ✓ | ✓ | — |
| Pengaturan pengguna/role/backup | ✓ | — (pengguna: tidak) | — |
| Super Admin | — | — | — (aplikasi terpisah) |

Catatan: role Gudang belum ada di skema v1 — keputusan produk sebelum modul persediaan dibangun.

## 9. States, feedback, dan aksesibilitas

- **Loading:** skeleton, bukan spinner kosong; tombol submit menunjukkan status proses dan dinonaktifkan.
- **Sukses:** pesan jelas + nomor transaksi/status + aksi lanjutan ("Cetak struk", "Transaksi baru").
- **Gagal:** pesan kesalahan yang menjelaskan penyebab + apa yang bisa dilakukan pengguna ("Coba lagi", "Periksa stok").
- **Kosong:** ilustrasi/teks + CTA relevan, bukan tabel kosong.
- **Aksesibilitas:** heading semantik berurutan, label form jelas, fokus keyboard terlihat, kontras memadai, `aria-expanded` pada menu/accordion, `prefers-reduced-motion` dihormati (sudah diterapkan di landing CSS).
- **Safe by default:** hapus/arsip, restore, ubah periode, dan ubah nomor transaksi memerlukan konfirmasi kuat + audit log; restore membutuhkan backup valid.

## 10. Urutan implementasi UX (bertahap, bukan sekaligus)

1. **Pola referensi:** CSS dasar tenant + pola halaman daftar di `/produk` (daftar → tambah/edit → arsip) + sidebar/topbar.
2. **P0:** produk & stok (saldo awal, mutasi ledger) → kasir → pembelian → hutang/piutang → retur → audit log → backup teruji.
3. **P1:** transfer, opname, stok minimum, laporan operasional, kas, printer/struk, import tervalidasi.
4. **P2:** akuntansi (CoA, jurnal), laporan keuangan, dashboard analitik.
5. **P3:** PWA/offline, notifikasi, Automation Engine, integrasi.

Setiap tahap: implementasi → tes (pytest + cek HTTP + cek visual) → push setelah persetujuan — pola yang sama seperti tahap 1–4.
