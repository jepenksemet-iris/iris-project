# POS IRIS --- Dokumentasi Proyek

> **Status dokumen:** Dokumen induk/rancangan proyek\
> **Nama proyek:** IRIS Platform\
> **Nama aplikasi:** POS IRIS\
> **Domain:** `posiris.biz.id`\
> **Folder proyek:** `iris-platform` (berada di SSD 2; lokasi mount/path
> lengkap belum diverifikasi)\
> **Bahasa dokumen:** Indonesia

------------------------------------------------------------------------

## 1. Ringkasan Proyek

POS IRIS adalah platform Point of Sale (POS) berbasis web yang ditujukan
untuk toko retail, usaha kecil, dan UMKM. Arah pengembangan IRIS adalah
menjadi platform operasional bisnis modular berbasis SaaS, bukan hanya
aplikasi kasir.

Sistem dirancang untuk membantu pemilik usaha mengelola transaksi,
produk, persediaan, pembelian, pelanggan, pemasok, keuangan, dan laporan
dari satu aplikasi. Platform juga direncanakan memiliki otomatisasi
proses, pemantauan kesalahan, serta alat pengolahan dokumen dan gambar.

**Tujuan bisnis utama:** - Mendapatkan pendaftaran pengguna baru. -
Menghasilkan prospek penjualan melalui WhatsApp dan tim sales. -
Menyediakan sistem yang mudah digunakan oleh toko retail dan UMKM. -
Mengembangkan layanan berlangganan dengan paket yang jelas. - Menjaga
aplikasi tetap stabil, aman, dan dapat dikembangkan tanpa merusak fitur
yang sudah berjalan.

## 2. Sasaran Pengguna

Target pasar utama adalah **semua toko retail dan UMKM**.

Contoh pengguna: - Toko kelontong dan sembako. - Toko bangunan. - Toko
pakaian dan perlengkapan. - Toko elektronik. - Usaha dagang dengan satu
atau beberapa outlet. - Pemilik usaha yang membutuhkan pencatatan
transaksi dan stok terpusat.

Kebutuhan utama pengguna: - Transaksi kasir yang cepat dan mudah. -
Informasi stok yang akurat. - Pengelolaan pembelian dan penjualan. -
Laporan usaha yang mudah dipahami. - Pengaturan pegawai dan hak akses. -
Pengelolaan beberapa outlet sesuai paket. - Data usaha yang terpisah dan
aman antar-tenant.

## 3. Model Bisnis dan Paket Harga

Harga paket yang pernah ditetapkan dalam rancangan bisnis:

  ------------------------------------------------------------------------
  Paket                                        Harga Keterangan
  --------------------- ---------------------------- ---------------------
  Starter                             Rp10.000/bulan Paket awal

  Growth                             Rp189.000/bulan Harga tetap untuk
                                                     seluruh outlet selama
                                                     masih dalam batas
                                                     paket

  Scale                              Rp499.000/bulan Harga tetap untuk
                                                     seluruh outlet selama
                                                     masih dalam batas
                                                     paket
  ------------------------------------------------------------------------

**Catatan penting:** - Batas jumlah outlet dan fitur tiap paket harus
ditetapkan secara eksplisit pada halaman harga dan aturan sistem. -
Harga Growth dan Scale bukan harga per outlet; harga berlaku untuk paket
sesuai batas yang ditentukan. - Detail kuota produk, pengguna,
transaksi, penyimpanan, dan fitur harus menjadi konfigurasi paket, bukan
angka yang tersebar di banyak bagian kode. - Harga di atas adalah
rancangan harga yang pernah dipilih dan perlu diverifikasi sebelum
dipublikasikan.

### Program pendaftaran

Program promosi yang pernah dipertimbangkan: - 10 pendaftar pertama
memperoleh akses gratis selamanya dengan ketentuan memberikan ulasan. -
Alternatif lain: uji coba gratis selama 14 hari.

Kedua skema tersebut merupakan opsi promosi yang pernah dibahas;
keputusan final, syarat, dan mekanisme validasinya perlu ditetapkan
sebelum diterapkan.

## 4. Teknologi dan Arsitektur

### 4.1 Stack yang diketahui

Stack proyek yang dinyatakan pengguna:

-   Python 3.12
-   Flask
-   Jinja2
-   SQLite
-   `sqlite3` untuk akses database
-   `get_tenant_db` untuk memperoleh koneksi database tenant

Dependensi yang pernah disebut dalam proyek: - Flask-WTF -
Flask-Limiter - Gunicorn - pytest - pytest-flask

**Prinsip utama:** pertahankan stack Flask + Jinja2 + SQLite yang sudah
berjalan. Jangan mengganti proyek menjadi Next.js, TypeScript, Prisma,
atau stack lain tanpa keputusan dan analisis migrasi yang eksplisit.

### 4.2 Aplikasi utama

Komponen aplikasi yang diketahui:

  -----------------------------------------------------------------------
  Aplikasi                File/komponen           Fungsi
  ----------------------- ----------------------- -----------------------
  Landing                 `landing_app.py`        Situs publik, informasi
                                                  produk, pendaftaran

  Tenant                  `tenant_app.py`         Aplikasi operasional
                                                  milik tenant

  Super Admin             `superadmin_app.py`     Pengelolaan platform
                                                  dan tenant
  -----------------------------------------------------------------------

Port pengembangan yang pernah digunakan: - Landing: `5000` - Tenant:
`5001` - Super Admin: `5002` (pernah disebut dalam konfigurasi/riwayat
proyek; verifikasi sebelum digunakan)

Nama file, struktur direktori, port, dan cara menjalankan aplikasi harus
selalu diperiksa dari kondisi repository terkini sebelum melakukan
perubahan.

### 4.3 Isolasi database tenant

Pola penyimpanan yang diketahui adalah database SQLite terpisah untuk
setiap tenant, dengan pola direktori:

``` text
tenants/
└── <tenant-slug>/
    └── iris.db
```

Akses database tenant dilakukan melalui mekanisme seperti
`get_tenant_db`.

Ketentuan desain: - Tenant tidak boleh dapat membaca atau mengubah
database tenant lain. - Identitas tenant harus divalidasi pada setiap
permintaan yang memerlukan data tenant. - Operasi transaksi dan stok
harus konsisten. - Perubahan skema database harus memiliki mekanisme
migrasi yang aman. - Backup dan pemulihan harus memperhitungkan database
setiap tenant. - Jangan menganggap struktur aktual sama dengan contoh
ini sebelum memeriksa repository.

## 5. Modul dan Ruang Lingkup Fitur

Daftar berikut merupakan peta ruang lingkup produk. Daftar ini **tidak
menyatakan bahwa semua fitur sudah selesai atau tersedia**. Status
implementasi harus ditentukan melalui audit kode dan pengujian.

### 5.1 Core Platform

-   Autentikasi dan manajemen sesi.
-   Manajemen pengguna.
-   Role dan permission.
-   Multi-tenant.
-   Multi-outlet/cabang.
-   Pengaturan profil usaha.
-   Pengaturan paket dan masa berlangganan.
-   Provisioning tenant dan aktivasi akun.

### 5.2 Point of Sale (POS)

-   Antarmuka kasir.
-   Pencarian dan pemilihan produk.
-   Keranjang transaksi.
-   Diskon dan pajak sesuai konfigurasi.
-   Berbagai metode pembayaran.
-   Penyelesaian transaksi.
-   Cetak atau unduh struk.
-   Riwayat transaksi.
-   Retur dan pembatalan sesuai aturan otorisasi.

### 5.3 Produk dan Persediaan

-   Kategori dan satuan produk.
-   SKU/kode barang dan barcode.
-   Harga beli dan harga jual.
-   Stok per outlet.
-   Mutasi stok.
-   Penyesuaian stok.
-   Stok minimum dan peringatan persediaan.
-   Kartu stok dan riwayat perubahan.
-   Dukungan produk dengan variasi bila diperlukan.

### 5.4 Pembelian dan Pemasok

-   Data pemasok.
-   Permintaan atau pesanan pembelian.
-   Penerimaan barang.
-   Pembaruan stok dari penerimaan.
-   Retur pembelian.
-   Riwayat pembelian dan kewajiban pembayaran.

### 5.5 Penjualan dan Pelanggan

-   Data pelanggan.
-   Riwayat pembelian pelanggan.
-   Penjualan tunai dan metode pembayaran lain.
-   Retur penjualan.
-   Diskon dan promosi.
-   Ringkasan penjualan per periode, outlet, produk, dan kasir.

### 5.6 Keuangan

-   Pencatatan pemasukan dan pengeluaran.
-   Kas dan rekening.
-   Arus kas.
-   Hutang dan piutang jika termasuk ruang lingkup paket.
-   Rekonsiliasi transaksi.
-   Ringkasan laba/rugi sesuai kelengkapan data.

### 5.7 Laporan

-   Laporan penjualan.
-   Laporan pembelian.
-   Laporan persediaan.
-   Laporan produk terlaris.
-   Laporan kasir.
-   Laporan keuangan.
-   Filter periode dan outlet.
-   Ekspor data ke format yang diperlukan.

### 5.8 Otomatisasi --- IRIS Automation Engine

Modul otomatisasi merupakan bagian penting dari arah pengembangan IRIS.

Contoh kemampuan: - Peringatan stok minimum. - Pengingat pembayaran atau
jatuh tempo. - Ringkasan penjualan terjadwal. - Tugas rutin yang dapat
dijadwalkan. - Notifikasi kepada pemilik atau staf berwenang. -
Otomatisasi berdasarkan pemicu transaksi atau perubahan data.

Otomatisasi harus memiliki: - Pengaturan aktif/nonaktif. - Riwayat
eksekusi. - Status berhasil/gagal. - Mekanisme retry yang terkendali. -
Batas percobaan dan pencegahan proses ganda. - Log yang dapat ditinjau
administrator.

### 5.9 Pemantauan Error dan Perbaikan

Arah produk mencakup pemantauan error dan bantuan perbaikan.

Kemampuan yang direncanakan: - Pencatatan error aplikasi. -
Pengelompokan error berdasarkan modul. - Informasi waktu dan konteks
kejadian. - Pemantauan kesehatan aplikasi. - Rekomendasi langkah
perbaikan. - Alur perbaikan otomatis yang dibatasi dan dapat diaudit.

**Batas keselamatan:** - Jangan menjalankan perbaikan otomatis yang
mengubah atau menghapus data produksi tanpa validasi. - Perubahan kode
otomatis harus melalui pemeriksaan, pengujian, dan persetujuan sesuai
tingkat risikonya. - Jangan pernah menampilkan password, token, secret
key, atau data sensitif dalam log. - Sediakan mekanisme rollback untuk
perubahan yang berisiko.

### 5.10 IRIS File Studio

Modul pengolahan file direncanakan untuk membantu pengguna mengubah dan
mengolah dokumen/gambar.

Ruang lingkup yang dapat dikembangkan: - Konversi gambar menjadi PDF. -
Penggabungan gambar menjadi satu dokumen. - Konversi PDF ke gambar. -
OCR untuk mengambil teks dari gambar atau dokumen hasil pemindaian. -
Pengubahan ukuran dan kompresi gambar. - Pengelolaan hasil ekspor.

Format yang didukung, batas ukuran, kualitas hasil, dan kebijakan
penyimpanan harus ditentukan berdasarkan kemampuan implementasi aktual.

### 5.11 Keamanan dan Administrasi Sistem

-   Role-based access control.
-   Perlindungan CSRF pada formulir dan endpoint yang relevan.
-   Pembatasan percobaan login dan rate limiting.
-   Validasi input di sisi server.
-   Pengamanan sesi dan cookie.
-   Audit log untuk aktivitas penting.
-   Isolasi data tenant.
-   Backup dan pemulihan.
-   Pemantauan kesehatan aplikasi.
-   Pengelolaan konfigurasi dan secret secara aman.

### 5.12 Integrasi

Integrasi eksternal dapat ditambahkan secara bertahap, misalnya: -
WhatsApp untuk prospek, notifikasi, atau komunikasi sales. - Printer
struk. - Barcode scanner. - Ekspor/impor spreadsheet. - Payment gateway
jika sudah diperlukan dan disetujui.

Integrasi harus menggunakan dokumentasi resmi, menjaga keamanan
kredensial, dan tidak membuat biaya eksternal tanpa persetujuan.

## 6. Alur Pendaftaran dan Pembuatan Tenant

Pengalaman pendaftaran harus sederhana dan memberikan informasi yang
jelas kepada pengguna.

Alur konseptual: 1. Pengunjung membuka halaman pendaftaran. 2. Pengguna
mengisi identitas dan informasi usaha. 3. Server memvalidasi data. 4.
Sistem membuat identitas tenant. 5. Sistem menyiapkan database dan
konfigurasi tenant. 6. Sistem menyiapkan akun pemilik dan hak akses
awal. 7. Sistem menjalankan pemeriksaan kesehatan. 8. Tenant diaktifkan
setelah langkah kritis berhasil. 9. Pengguna diarahkan ke aplikasi
tenant.

### Tenant Provisioning Engine

Proses pembuatan tenant sebaiknya: - Dijalankan sebagai pekerjaan
terkelola jika prosesnya memerlukan waktu. - Menyimpan status proses
agar tidak hilang saat halaman dimuat ulang. - Menampilkan progres
kepada pengguna. - Mencatat log dan pesan kesalahan yang aman. -
Mendukung retry tanpa membuat tenant atau data ganda. - Memastikan
database dan konfigurasi siap sebelum aktivasi. - Menyediakan pemantauan
dari Super Admin.

Teks pengalaman pengguna yang pernah diinginkan adalah seperti **"POS
saya sedang dibuat"**. Pesan progres harus jujur dan sesuai status
proses sebenarnya; jangan menampilkan keberhasilan sebelum tenant siap
digunakan.

## 7. Landing Page dan Akuisisi Pengguna

Landing page `posiris.biz.id` diarahkan untuk: - Menjelaskan manfaat POS
IRIS. - Menampilkan fitur utama. - Menampilkan paket harga. - Mendorong
pendaftaran. - Mengarahkan calon pelanggan ke WhatsApp atau tim sales. -
Menyediakan informasi kebijakan privasi dan syarat layanan.

Bagian konten yang perlu tersedia: - Hero/identitas produk. - Manfaat
utama. - Fitur. - Cara kerja. - Paket harga. - Pertanyaan umum. - Ajakan
mendaftar. - Kontak/WhatsApp. - Kebijakan privasi. - Syarat dan
ketentuan. - Footer dan navigasi.

## 8. Prinsip Keamanan dan Kualitas

Prioritas pengembangan: 1. Menjaga data transaksi dan stok tetap benar.
2. Memastikan isolasi antar-tenant. 3. Melindungi autentikasi dan
otorisasi. 4. Menjaga kestabilan aplikasi yang sudah berjalan. 5.
Memastikan perubahan memiliki pengujian. 6. Menghindari perubahan besar
yang tidak diperlukan.

Pemeriksaan keamanan yang perlu dilakukan: - CSRF untuk seluruh endpoint
yang mengubah data melalui permintaan yang relevan. - Validasi otorisasi
di server, bukan hanya menyembunyikan tombol di antarmuka. - Rate
limiting pada login dan endpoint sensitif. - Penanganan sesi, cookie,
dan password. - Validasi file upload dan pembatasan tipe/ukuran. -
Pencegahan akses lintas tenant. - Pengamanan log dan pesan error. -
Pengelolaan secret di luar repository. - Backup dan uji pemulihan.

## 9. Strategi Pengujian dan Audit

Audit harus dimulai dengan pendekatan **read-only** untuk memahami
kondisi aktual.

Area audit: - Struktur direktori dan entry point aplikasi. - Routes,
services, models, templates, dan dependensi. - Skema database dan relasi
data. - Alur transaksi penjualan. - Konsistensi stok saat penjualan,
retur, pembelian, dan pembatalan. - Hak akses dan isolasi tenant. -
Keamanan endpoint. - Kinerja query dan proses berat. - Duplikasi kode. -
Kualitas pesan error dan logging. - Cakupan serta hasil pengujian.

Prinsip audit: - Sertakan bukti file dan nomor baris untuk temuan
kode. - Pisahkan temuan kritis, tinggi, sedang, dan rendah. - Jelaskan
dampak, penyebab, dan rekomendasi. - Jangan mengubah file atau database
saat audit read-only. - Jangan membuka `.env`, secret, database
produksi, atau backup yang dikecualikan dari ruang lingkup audit. -
Jangan menjalankan migrasi atau perintah yang mengubah data tanpa
persetujuan.

### Pengujian

Gunakan pytest dan pengujian smoke sesuai konfigurasi proyek aktual.

Pengujian penting: - Landing dan pendaftaran. - Login dan logout. - Hak
akses. - Isolasi tenant. - Transaksi POS. - Pembelian dan penerimaan
barang. - Mutasi dan penyesuaian stok. - Retur dan pembatalan. -
Laporan. - Keuangan. - Upload dan konversi file. - Provisioning
tenant. - Keamanan endpoint.

Hasil pengujian terdahulu pernah dilaporkan lulus **162/162 tes** pada
salah satu kondisi proyek. Angka ini adalah catatan historis, bukan
jaminan kondisi repository saat ini; jalankan ulang tes untuk memperoleh
status terbaru.

## 10. Lingkungan Pengembangan dan Deployment

Preferensi pengembangan yang pernah ditetapkan: - Proyek utama tetap
berada di komputer lokal/SSD. - Pengembangan dilakukan melalui VS
Code. - Salinan cloud dapat digunakan untuk deployment atau pengujian
bila diperlukan. - Hindari pemindahan proyek ke cloud tanpa kebutuhan
yang jelas. - Utamakan layanan gratis atau biaya yang transparan. -
Jangan menggunakan layanan yang dapat menagih otomatis tanpa
persetujuan. - Jangan memasukkan secret ke Git.

Sebelum deployment: - Pastikan konfigurasi production terpisah dari
development. - Gunakan environment variables untuk secret. - Pastikan
database dan direktori data memiliki penyimpanan persisten. - Pastikan
proses backup tersedia. - Jalankan tes dan smoke test. - Periksa log dan
health check. - Dokumentasikan prosedur rollback.

**Catatan lokasi proyek:** folder `iris-platform` diketahui berada di
SSD 2. Jangan mengasumsikan path seperti `~/Unduhan/iris-platform` atau
mount point tertentu. Periksa lokasi aktual dari sistem sebelum
menjalankan perintah terminal.

## 11. Struktur Dokumentasi yang Disarankan

Dokumentasi proyek dapat dikembangkan menjadi beberapa file:

``` text
docs/
├── README.md
├── PROJECT_OVERVIEW.md
├── ARCHITECTURE.md
├── MODULES.md
├── DATABASE.md
├── SECURITY.md
├── TESTING.md
├── DEPLOYMENT.md
├── TENANT_PROVISIONING.md
└── CHANGELOG.md
```

Daftar tersebut adalah usulan dokumentasi, bukan pernyataan bahwa
file-file itu sudah ada di repository.

## 12. Tahapan Pengembangan

Urutan kerja yang disarankan:

  -----------------------------------------------------------------------
  Tahap                   Fokus                   Hasil yang diharapkan
  ----------------------- ----------------------- -----------------------
  1                       Inventarisasi dan audit Peta kondisi aktual dan
                          read-only               daftar risiko

  2                       Stabilitas Core POS     Transaksi, produk,
                                                  stok, dan pembelian
                                                  konsisten

  3                       Keamanan dan isolasi    Hak akses dan
                          tenant                  perlindungan data kuat

  4                       Pendaftaran dan         Tenant dibuat dengan
                          provisioning            aman dan progres
                                                  terpantau

  5                       Laporan dan keuangan    Data operasional dapat
                                                  dipantau

  6                       Landing dan paket       Akuisisi pengguna dan
                                                  aturan paket jelas

  7                       Automation Engine       Proses rutin dapat
                                                  diotomatisasi

  8                       Error monitoring        Error terpantau dan
                                                  ditangani secara aman

  9                       IRIS File Studio        Pengolahan gambar dan
                                                  dokumen

  10                      Deployment dan          Rilis stabil, backup,
                          pemeliharaan            monitoring, dan
                                                  rollback
  -----------------------------------------------------------------------

Urutan dapat disesuaikan setelah audit menemukan kondisi dan prioritas
sebenarnya.

## 13. Aturan Kerja untuk Pengembangan dengan AI/Copilot

Saat AI coding agent membantu proyek IRIS, ikuti aturan berikut:

1.  Baca struktur dan dokumentasi repository sebelum mengusulkan
    perubahan.
2.  Jangan mengarang nama file, fungsi, tabel, atau route.
3.  Pertahankan Flask + Python + Jinja2 + SQLite kecuali ada keputusan
    eksplisit untuk migrasi.
4.  Jangan menghapus atau mengganti fitur yang sudah berjalan tanpa
    analisis dampak.
5.  Lakukan perubahan sekecil mungkin dan sesuai pola proyek.
6.  Periksa seluruh pemanggil fungsi dan dependensi sebelum mengubah
    antarmuka fungsi.
7.  Jangan membaca atau menampilkan `.env`, token, password, secret,
    atau data pribadi.
8.  Jangan mengubah database, menjalankan migrasi, menghapus file, atau
    melakukan deployment tanpa persetujuan.
9.  Tambahkan atau perbarui tes untuk setiap perubahan perilaku.
10. Jalankan tes yang relevan dan laporkan hasil sebenarnya.
11. Sertakan daftar file yang berubah, alasan, risiko, dan cara
    verifikasi.
12. Jangan menyatakan fitur selesai jika belum diuji.

## 14. Hal yang Masih Harus Diverifikasi

Dokumen ini menggabungkan informasi proyek dan keputusan rancangan yang
pernah dibahas. Sebelum dijadikan spesifikasi implementasi final,
verifikasi:

-   Struktur repository dan daftar modul aktual.
-   Daftar fitur yang sudah selesai, sebagian selesai, atau belum
    dibuat.
-   Skema database aktual.
-   Port dan perintah startup yang benar.
-   Batas outlet, pengguna, produk, dan fitur tiap paket.
-   Keputusan final program promosi.
-   Daftar metode pembayaran.
-   Kebutuhan pajak dan akuntansi.
-   Format file yang benar-benar didukung.
-   Provider deployment dan biaya aktual.
-   Kebijakan backup, retensi, dan pemulihan data.

## 15. Definisi Keberhasilan Proyek

POS IRIS dapat dianggap siap digunakan secara luas apabila: - Pengguna
dapat mendaftar dan membuat tenant tanpa proses yang membingungkan. -
Tenant tidak dapat mengakses data tenant lain. - Transaksi penjualan dan
perubahan stok konsisten. - Pembelian, retur, dan pembatalan tercatat
dengan benar. - Laporan sesuai dengan data sumber. - Hak akses
diterapkan di server. - Error dapat ditelusuri tanpa membocorkan data
sensitif. - Backup dapat dipulihkan. - Tes penting lulus. - Paket dan
batas layanan diterapkan secara konsisten. - Deployment dapat dipantau
dan memiliki prosedur rollback.

------------------------------------------------------------------------

**Catatan pemeliharaan:** Perbarui dokumen ini setiap kali ada keputusan
arsitektur, perubahan modul, perubahan paket harga, atau perubahan
prosedur deployment. Bedakan dengan jelas antara fitur yang sudah
berjalan, sedang dikerjakan, dan masih berupa rencana.
