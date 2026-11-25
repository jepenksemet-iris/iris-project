# Database — POS IRIS

Dari dokumen induk: [DOKUMENTASI_PROYEK_IRIS.md](DOKUMENTASI_PROYEK_IRIS.md) bagian 4.3.

## Pola penyimpanan

Database SQLite terpisah untuk setiap tenant, dengan pola direktori:

```text
tenants/
└── <tenant-slug>/
    └── iris.db
```

Akses database tenant dilakukan melalui mekanisme seperti `get_tenant_db`.

## Ketentuan desain

- Tenant tidak boleh dapat membaca atau mengubah database tenant lain.
- Identitas tenant harus divalidasi pada setiap permintaan yang memerlukan data tenant.
- Operasi transaksi dan stok harus konsisten.
- Perubahan skema database harus memiliki mekanisme migrasi yang aman.
- Backup dan pemulihan harus memperhitungkan database setiap tenant.
- Jangan menganggap struktur aktual sama dengan contoh ini sebelum memeriksa repository/kode aktual.

> Skema database aktual termasuk hal yang masih harus diverifikasi (dokumen induk bagian 14).
