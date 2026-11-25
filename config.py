"""Konfigurasi bersama POS IRIS (skeleton tahap 2).

Semua secret dibaca dari environment — tidak ada secret di dalam kode
atau repository. Lihat `.env.example`.
"""
import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    # Direktori berisi database tenant: <IRIS_DATA_DIR>/<tenant-slug>/iris.db
    DATA_DIR = os.environ.get("IRIS_DATA_DIR", "tenants")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    # Di production, SECRET_KEY wajib diset dari environment.
    # Aplikasi menolak jalan dengan nilai dev di create_app() masing-masing.


def get_config():
    return (
        ProductionConfig
        if os.environ.get("FLASK_ENV") == "production"
        else DevelopmentConfig
    )
