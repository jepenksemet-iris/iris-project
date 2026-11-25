# Tenant Provisioning — Pendaftaran dan Pembuatan Tenant

Dari dokumen induk: [DOKUMENTASI_PROYEK_IRIS.md](DOKUMENTASI_PROYEK_IRIS.md) bagian 6.

## Alur konseptual

1. Pengunjung membuka halaman pendaftaran.
2. Pengguna mengisi identitas dan informasi usaha.
3. Server memvalidasi data.
4. Sistem membuat identitas tenant.
5. Sistem menyiapkan database dan konfigurasi tenant.
6. Sistem menyiapkan akun pemilik dan hak akses awal.
7. Sistem menjalankan pemeriksaan kesehatan.
8. Tenant diaktifkan setelah langkah kritis berhasil.
9. Pengguna diarahkan ke aplikasi tenant.

## Tenant Provisioning Engine

Proses pembuatan tenant sebaiknya:

- Dijalankan sebagai pekerjaan terkelola jika prosesnya memerlukan waktu.
- Menyimpan status proses agar tidak hilang saat halaman dimuat ulang.
- Menampilkan progres kepada pengguna.
- Mencatat log dan pesan kesalahan yang aman.
- Mendukung retry tanpa membuat tenant atau data ganda.
- Memastikan database dan konfigurasi siap sebelum aktivasi.
- Menyediakan pemantauan dari Super Admin.

Teks pengalaman pengguna yang pernah diinginkan: **"POS saya sedang dibuat"**. Pesan progres harus jujur dan sesuai status proses sebenarnya; jangan menampilkan keberhasilan sebelum tenant siap digunakan.
