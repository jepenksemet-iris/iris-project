# Testing — Strategi Pengujian dan Audit

Dari dokumen induk: [DOKUMENTASI_PROYEK_IRIS.md](DOKUMENTASI_PROYEK_IRIS.md) bagian 9.

## Audit read-only

Audit dimulai dengan pendekatan **read-only** untuk memahami kondisi aktual.

Area audit: struktur direktori dan entry point; routes, services, models, templates, dan dependensi; skema database dan relasi data; alur transaksi penjualan; konsistensi stok saat penjualan, retur, pembelian, dan pembatalan; hak akses dan isolasi tenant; keamanan endpoint; kinerja query dan proses berat; duplikasi kode; kualitas pesan error dan logging; cakupan serta hasil pengujian.

Prinsip audit:

- Sertakan bukti file dan nomor baris untuk temuan kode.
- Pisahkan temuan kritis, tinggi, sedang, dan rendah; jelaskan dampak, penyebab, dan rekomendasi.
- Jangan mengubah file atau database saat audit read-only.
- Jangan membuka `.env`, secret, database produksi, atau backup yang dikecualikan dari ruang lingkup audit.
- Jangan menjalankan migrasi atau perintah yang mengubah data tanpa persetujuan.

## Pengujian

Gunakan pytest dan pengujian smoke sesuai konfigurasi proyek aktual.

Pengujian penting: landing dan pendaftaran; login dan logout; hak akses; isolasi tenant; transaksi POS; pembelian dan penerimaan barang; mutasi dan penyesuaian stok; retur dan pembatalan; laporan; keuangan; upload dan konversi file; provisioning tenant; keamanan endpoint.

> Hasil pengujian terdahulu pernah dilaporkan lulus **162/162 tes** pada salah satu kondisi proyek. Angka ini adalah catatan historis, bukan jaminan kondisi repository saat ini; jalankan ulang tes untuk memperoleh status terbaru.
