# Modules — Peta Ruang Lingkup Fitur

Dari dokumen induk: [DOKUMENTASI_PROYEK_IRIS.md](DOKUMENTASI_PROYEK_IRIS.md) bagian 5.

> Daftar ini adalah peta ruang lingkup produk. Daftar ini **tidak menyatakan bahwa semua fitur sudah selesai atau tersedia**. Status implementasi harus ditentukan melalui audit kode dan pengujian.

## 5.1 Core Platform
Autentikasi dan manajemen sesi; manajemen pengguna; role dan permission; multi-tenant; multi-outlet/cabang; pengaturan profil usaha; pengaturan paket dan masa berlangganan; provisioning tenant dan aktivasi akun.

## 5.2 Point of Sale (POS)
Antarmuka kasir; pencarian dan pemilihan produk; keranjang transaksi; diskon dan pajak sesuai konfigurasi; berbagai metode pembayaran; penyelesaian transaksi; cetak atau unduh struk; riwayat transaksi; retur dan pembatalan sesuai aturan otorisasi.

## 5.3 Produk dan Persediaan
Kategori dan satuan produk; SKU/kode barang dan barcode; harga beli dan harga jual; stok per outlet; mutasi stok; penyesuaian stok; stok minimum dan peringatan persediaan; kartu stok dan riwayat perubahan; dukungan produk dengan variasi bila diperlukan.

## 5.4 Pembelian dan Pemasok
Data pemasok; permintaan atau pesanan pembelian; penerimaan barang; pembaruan stok dari penerimaan; retur pembelian; riwayat pembelian dan kewajiban pembayaran.

## 5.5 Penjualan dan Pelanggan
Data pelanggan; riwayat pembelian pelanggan; penjualan tunai dan metode pembayaran lain; retur penjualan; diskon dan promosi; ringkasan penjualan per periode, outlet, produk, dan kasir.

## 5.6 Keuangan
Pencatatan pemasukan dan pengeluaran; kas dan rekening; arus kas; hutang dan piutang jika termasuk ruang lingkup paket; rekonsiliasi transaksi; ringkasan laba/rugi sesuai kelengkapan data.

## 5.7 Laporan
Laporan penjualan, pembelian, persediaan, produk terlaris, kasir, dan keuangan; filter periode dan outlet; ekspor data ke format yang diperlukan.

## 5.8 Otomatisasi — IRIS Automation Engine
Contoh: peringatan stok minimum; pengingat pembayaran/jatuh tempo; ringkasan penjualan terjadwal; tugas rutin terjadwal; notifikasi kepada pemilik/staf berwenang; otomatisasi berdasarkan pemicu transaksi atau perubahan data.

Otomatisasi harus memiliki: pengaturan aktif/nonaktif; riwayat eksekusi; status berhasil/gagal; mekanisme retry yang terkendali; batas percobaan dan pencegahan proses ganda; log yang dapat ditinjau administrator.

## 5.9 Pemantauan Error dan Perbaikan
Pencatatan error aplikasi; pengelompokan error berdasarkan modul; informasi waktu dan konteks kejadian; pemantauan kesehatan aplikasi; rekomendasi langkah perbaikan; alur perbaikan otomatis yang dibatasi dan dapat diaudit.

Batas keselamatan: jangan menjalankan perbaikan otomatis yang mengubah/menghapus data produksi tanpa validasi; perubahan kode otomatis harus melalui pemeriksaan, pengujian, dan persetujuan sesuai risiko; jangan pernah menampilkan password/token/secret dalam log; sediakan mekanisme rollback.

## 5.10 IRIS File Studio
Konversi gambar menjadi PDF; penggabungan gambar menjadi satu dokumen; konversi PDF ke gambar; OCR; pengubahan ukuran dan kompresi gambar; pengelolaan hasil ekspor. Format yang didukung, batas ukuran, kualitas hasil, dan kebijakan penyimpanan ditentukan berdasarkan kemampuan implementasi aktual.

## 5.11 Keamanan dan Administrasi Sistem
Lihat [SECURITY.md](SECURITY.md).

## 5.12 Integrasi
Bertahap, misalnya: WhatsApp (prospek, notifikasi, komunikasi sales); printer struk; barcode scanner; ekspor/impor spreadsheet; payment gateway jika sudah diperlukan dan disetujui. Gunakan dokumentasi resmi, jaga keamanan kredensial, dan jangan membuat biaya eksternal tanpa persetujuan.
