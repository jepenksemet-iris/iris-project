"""Akses database SQLite per tenant (skeleton tahap 2).

Pola dari dokumen proyek:
    <DATA_DIR>/<tenant-slug>/iris.db

Aturan penting:
- Slug divalidasi ketat (huruf kecil/angka/tanda hubung saja) supaya
  tidak ada path traversal antar-tenant.
- Fungsi ini hanya membuka koneksi; BUKAN membuat skema/tabel.
  Migrasi & skema adalah pekerjaan tahap berikutnya.
"""
import os
import re
import sqlite3
from pathlib import Path

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def validate_tenant_slug(slug):
    """Return True hanya untuk slug yang aman dipakai sebagai nama direktori."""
    return bool(slug) and bool(_SLUG_RE.match(slug))


def tenant_db_path(slug, data_dir=None):
    if not validate_tenant_slug(slug):
        raise ValueError(f"tenant slug tidak valid: {slug!r}")
    base = Path(data_dir or os.environ.get("IRIS_DATA_DIR", "tenants"))
    return base / slug / "iris.db"


def get_tenant_db(slug, data_dir=None):
    """Buka koneksi SQLite tenant. Membuat direktori tenant bila belum ada.

    Pemanggil bertanggung jawab menutup koneksi (``conn.close()``).
    """
    path = tenant_db_path(slug, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def list_tenants(data_dir=None):
    """Daftar slug tenant yang punya direktori di DATA_DIR (nama saja)."""
    base = Path(data_dir or os.environ.get("IRIS_DATA_DIR", "tenants"))
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())
