# Project Overview — POS IRIS

Ringkasan dari dokumen induk: [DOKUMENTASI_PROYEK_IRIS.md](DOKUMENTASI_PROYEK_IRIS.md) bagian 1–3.

## Ringkasan

POS IRIS adalah platform Point of Sale berbasis web untuk toko retail, usaha kecil, dan UMKM, yang diarahkan menjadi platform operasional bisnis modular berbasis SaaS — bukan hanya aplikasi kasir.

Sistem membantu pemilik usaha mengelola transaksi, produk, persediaan, pembelian, pelanggan, pemasok, keuangan, dan laporan dari satu aplikasi. Platform juga direncanakan memiliki otomatisasi proses, pemantauan kesalahan, serta alat pengolahan dokumen dan gambar.

**Tujuan bisnis utama:**

- Mendapatkan pendaftaran pengguna baru.
- Menghasilkan prospek penjualan melalui WhatsApp dan tim sales.
- Menyediakan sistem yang mudah digunakan oleh toko retail dan UMKM.
- Mengembangkan layanan berlangganan dengan paket yang jelas.
- Menjaga aplikasi tetap stabil, aman, dan dapat dikembangkan tanpa merusak fitur yang sudah berjalan.

## Sasaran pengguna

Target pasar utama: **semua toko retail dan UMKM** — toko kelontong dan sembako, toko bangunan, toko pakaian dan perlengkapan, toko elektronik, usaha dagang dengan satu atau beberapa outlet, pemilik usaha yang membutuhkan pencatatan transaksi dan stok terpusat.

Kebutuhan utama: transaksi kasir yang cepat dan mudah; informasi stok yang akurat; pengelolaan pembelian dan penjualan; laporan usaha yang mudah dipahami; pengaturan pegawai dan hak akses; pengelolaan beberapa outlet sesuai paket; data usaha yang terpisah dan aman antar-tenant.

## Model bisnis dan paket harga

Harga berikut adalah **rancangan yang pernah dipilih dan perlu diverifikasi sebelum dipublikasikan**.

| Paket | Harga | Keterangan |
|---|---|---|
| Starter | Rp10.000/bulan | Paket awal |
| Growth | Rp189.000/bulan | Harga tetap untuk seluruh outlet selama masih dalam batas paket |
| Scale | Rp499.000/bulan | Harga tetap untuk seluruh outlet selama masih dalam batas paket |

Catatan:

- Harga Growth dan Scale **bukan** harga per outlet.
- Batas jumlah outlet dan fitur tiap paket harus ditetapkan eksplisit pada halaman harga dan aturan sistem.
- Detail kuota produk, pengguna, transaksi, penyimpanan, dan fitur harus menjadi konfigurasi paket, bukan angka yang tersebar di banyak bagian kode.

### Program pendaftaran (belum final)

Opsi promosi yang pernah dibahas — keputusan final, syarat, dan mekanisme validasinya perlu ditetapkan sebelum diterapkan:

- 10 pendaftar pertama memperoleh akses gratis selamanya dengan ketentuan memberikan ulasan.
- Alternatif: uji coba gratis selama 14 hari.
