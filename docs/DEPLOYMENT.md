# Deployment — Lingkungan Pengembangan dan Deployment

Dari dokumen induk: [DOKUMENTASI_PROYEK_IRIS.md](DOKUMENTASI_PROYEK_IRIS.md) bagian 10 dan 12.

## Preferensi pengembangan

- Proyek utama tetap berada di komputer lokal/SSD.
- Pengembangan dilakukan melalui VS Code.
- Salinan cloud dapat digunakan untuk deployment atau pengujian bila diperlukan.
- Hindari pemindahan proyek ke cloud tanpa kebutuhan yang jelas.
- Utamakan layanan gratis atau biaya yang transparan.
- Jangan menggunakan layanan yang dapat menagih otomatis tanpa persetujuan.
- Jangan memasukkan secret ke Git.

> **Catatan lokasi proyek:** folder `iris-platform` diketahui berada di SSD 2; lokasi mount/path lengkap belum diverifikasi. Jangan mengasumsikan path seperti `~/Unduhan/iris-platform` atau mount point tertentu. Periksa lokasi aktual dari sistem sebelum menjalankan perintah terminal.

## Sebelum deployment

- Pastikan konfigurasi production terpisah dari development.
- Gunakan environment variables untuk secret.
- Pastikan database dan direktori data memiliki penyimpanan persisten.
- Pastikan proses backup tersedia.
- Jalankan tes dan smoke test.
- Periksa log dan health check.
- Dokumentasikan prosedur rollback.

## Tahapan pengembangan

| Tahap | Fokus | Hasil yang diharapkan |
|---|---|---|
| 1 | Inventarisasi dan audit read-only | Peta kondisi aktual dan daftar risiko |
| 2 | Stabilitas Core POS | Transaksi, produk, stok, dan pembelian konsisten |
| 3 | Keamanan dan isolasi tenant | Hak akses dan perlindungan data kuat |
| 4 | Pendaftaran dan provisioning | Tenant dibuat dengan aman dan progres terpantau |
| 5 | Laporan dan keuangan | Data operasional dapat dipantau |
| 6 | Landing dan paket | Akuisisi pengguna dan aturan paket jelas |
| 7 | Automation Engine | Proses rutin dapat diotomatisasi |
| 8 | Error monitoring | Error terpantau dan ditangani secara aman |
| 9 | IRIS File Studio | Pengolahan gambar dan dokumen |
| 10 | Deployment dan pemeliharaan | Rilis stabil, backup, monitoring, dan rollback |

Urutan dapat disesuaikan setelah audit menemukan kondisi dan prioritas sebenarnya.
