"""Autentikasi tenant POS IRIS (tahap 3).

Menggunakan Flask-Login. Identitas pengguna disimpan di session
Flask (cookie, HttpOnly, SameSite=Lax — lihat config.py).

PENTING (batas tahap 3):
- Login ini berlaku per aplikasi tenant dan per database tenant:
  user id di session selalu dipasangkan dengan slug tenant di
  session (`session["tenant"]`). Tanpa slug, user tidak bisa
  dimuat — ini mencegah session satu tenant dipakai di tenant lain.
- Role: owner > admin > cashier. Decorator require_role() dipakai
  di route yang butuh peran tertentu; login_required saja tidak
  cukup untuk aksi admin/owner.
- Belum ada: rate limiting login, penguncian akun, reset password,
  dan autentikasi Super Admin (aplikasi superadmin masih tanpa auth
  dan tidak boleh diekspos — lihat README).
"""
from functools import wraps

from flask import abort, current_app, session
from flask_login import LoginManager, UserMixin, current_user

from iris_db import get_tenant_db

login_manager = LoginManager()
login_manager.login_view = "login"


class TenantUser(UserMixin):
    """User Flask-Login. id berbentuk "slug:row_id" supaya unik antar-tenant."""

    def __init__(self, slug, row):
        self.slug = slug
        self.row_id = row["id"]
        self.id = f"{slug}:{row['id']}"
        self.username = row["username"]
        self.full_name = row["full_name"]
        self.role = row["role"]
        self.outlet_id = row["outlet_id"]


@login_manager.user_loader
def load_user(user_id):
    try:
        slug, row_id = user_id.split(":", 1)
    except ValueError:
        return None
    # Session harus membawa tenant yang sama dengan user id.
    if session.get("tenant") != slug:
        return None
    data_dir = current_app.config.get("DATA_DIR") if current_app else None
    conn = get_tenant_db(slug, data_dir=data_dir)
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ? AND is_active = 1", (int(row_id),)
        ).fetchone()
    finally:
        conn.close()
    return TenantUser(slug, row) if row else None


def setup_auth(app):
    login_manager.init_app(app)
    return login_manager


def require_role(*roles):
    """Decorator: login wajib + role harus salah satu yang disebut."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator
