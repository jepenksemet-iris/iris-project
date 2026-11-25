"""Akses database SQLite per tenant (tahap 3: skema v1 + autentikasi).

Pola dari dokumen proyek:
    <DATA_DIR>/<tenant-slug>/iris.db

Aturan penting:
- Slug divalidasi ketat (huruf kecil/angka/tanda hubung saja) supaya
  tidak ada path traversal antar-tenant.
- Skema dibuat oleh init_tenant_db() dari iris_schema.sql dan
  versinya dicatat di PRAGMA user_version. Migrasi berikutnya
  menaikkan versi itu secara eksplisit (jangan ubah skema diam-diam).
- Password TIDAK pernah disimpan mentah: hanya hash Werkzeug
  (scrypt) di kolom users.password_hash.
"""
import os
import re
import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

SCHEMA_VERSION = 1
_SCHEMA_PATH = Path(__file__).with_name("iris_schema.sql")

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


def init_tenant_db(slug, data_dir=None):
    """Buat database tenant bila belum ada dan terapkan skema v1.

    Idempotent: aman dijalankan berulang kali (CREATE TABLE IF NOT
    EXISTS + PRAGMA user_version). Mengembalikan koneksi yang sudah
    terbuka; pemanggil menutupnya.
    """
    conn = get_tenant_db(slug, data_dir=data_dir)
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    return conn


def get_schema_version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


def create_user(conn, username, password, full_name="", role="cashier", outlet_id=None):
    """Buat pengguna tenant. Password langsung di-hash; hash yang disimpan."""
    if role not in ("owner", "admin", "cashier"):
        raise ValueError(f"role tidak valid: {role!r}")
    if len(password) < 8:
        raise ValueError("password minimal 8 karakter")
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, full_name, role, outlet_id)"
        " VALUES (?, ?, ?, ?, ?)",
        (username, generate_password_hash(password), full_name, role, outlet_id),
    )
    conn.commit()
    return cur.lastrowid


def get_user_by_username(conn, username):
    return conn.execute(
        "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
    ).fetchone()


def verify_user(conn, username, password):
    """Return baris user bila username+password cocok, None bila tidak."""
    user = get_user_by_username(conn, username)
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None


def list_tenants(data_dir=None):
    """Daftar slug tenant yang punya direktori di DATA_DIR (nama saja)."""
    base = Path(data_dir or os.environ.get("IRIS_DATA_DIR", "tenants"))
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())
