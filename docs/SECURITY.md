# Security — POS IRIS

Dari dokumen induk: [DOKUMENTASI_PROYEK_IRIS.md](DOKUMENTASI_PROYEK_IRIS.md) bagian 5.11 dan 8.

## Keamanan dan administrasi sistem

- Role-based access control.
- Perlindungan CSRF pada formulir dan endpoint yang relevan.
- Pembatasan percobaan login dan rate limiting.
- Validasi input di sisi server.
- Pengamanan sesi dan cookie.
- Audit log untuk aktivitas penting.
- Isolasi data tenant.
- Backup dan pemulihan.
- Pemantauan kesehatan aplikasi.
- Pengelolaan konfigurasi dan secret secara aman.

## Prioritas

1. Menjaga data transaksi dan stok tetap benar.
2. Memastikan isolasi antar-tenant.
3. Melindungi autentikasi dan otorisasi.
4. Menjaga kestabilan aplikasi yang sudah berjalan.
5. Memastikan perubahan memiliki pengujian.
6. Menghindari perubahan besar yang tidak diperlukan.

## Pemeriksaan keamanan

- CSRF untuk seluruh endpoint yang mengubah data melalui permintaan yang relevan.
- Validasi otorisasi di server, bukan hanya menyembunyikan tombol di antarmuka.
- Rate limiting pada login dan endpoint sensitif.
- Penanganan sesi, cookie, dan password.
- Validasi file upload dan pembatasan tipe/ukuran.
- Pencegahan akses lintas tenant.
- Pengamanan log dan pesan error.
- Pengelolaan secret di luar repository.
- Backup dan uji pemulihan.
