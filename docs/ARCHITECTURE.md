# Architecture — POS IRIS

Dari dokumen induk: [DOKUMENTASI_PROYEK_IRIS.md](DOKUMENTASI_PROYEK_IRIS.md) bagian 4.

## Stack

- Python 3.12
- Flask
- Jinja2
- SQLite, diakses dengan `sqlite3`
- `get_tenant_db` untuk memperoleh koneksi database tenant

Dependensi yang pernah disebut: Flask-WTF, Flask-Limiter, Gunicorn, pytest, pytest-flask.

**Prinsip utama:** pertahankan stack Flask + Jinja2 + SQLite yang sudah berjalan. Jangan mengganti proyek menjadi Next.js, TypeScript, Prisma, atau stack lain tanpa keputusan dan analisis migrasi yang eksplisit.

## Aplikasi utama

| Aplikasi | File/komponen | Fungsi |
|---|---|---|
| Landing | `landing_app.py` | Situs publik, informasi produk, pendaftaran |
| Tenant | `tenant_app.py` | Aplikasi operasional milik tenant |
| Super Admin | `superadmin_app.py` | Pengelolaan platform dan tenant |

Port pengembangan yang pernah digunakan (verifikasi sebelum digunakan):

- Landing: `5000`
- Tenant: `5001`
- Super Admin: `5002`

Nama file, struktur direktori, port, dan cara menjalankan aplikasi harus selalu diperiksa dari kondisi repository terkini sebelum melakukan perubahan.

## Isolasi database tenant

Lihat [DATABASE.md](DATABASE.md).
