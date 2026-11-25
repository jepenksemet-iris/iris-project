"""Tenant app — POS IRIS (skeleton tahap 2).

Aplikasi operasional milik tenant (kasir, produk, stok, dst — belum
diimplementasikan; lihat docs/MODULES.md untuk peta ruang lingkup).
Jalan di port 5001.

Identitas tenant sementara diambil dari query ``?tenant=<slug>`` HANYA
untuk skeleton lokal. Jangan dipakai begitu saja di production:
identitas tenant harus divalidasi dari sesi/login pada setiap request.

Jalankan:
    python tenant_app.py
atau:
    flask --app tenant_app run --port 5001
"""
import os
from flask import Flask, jsonify, render_template, request

from config import get_config
from iris_db import get_tenant_db, validate_tenant_slug


def create_app(config_class=None):
    app = Flask(__name__)
    app.config.from_object(config_class or get_config())

    if os.environ.get("FLASK_ENV") == "production" and app.config["SECRET_KEY"] == "dev-only-change-me":
        raise RuntimeError("SECRET_KEY production belum diset di environment")

    @app.get("/")
    def index():
        slug = request.args.get("tenant", "")
        if not validate_tenant_slug(slug):
            return jsonify({"error": "parameter tenant tidak valid"}), 400
        # Buka (dan bila perlu buat file) database tenant, lalu tutup lagi.
        # Skeleton ini belum membuat tabel apa pun di dalamnya.
        conn = get_tenant_db(slug, data_dir=app.config["DATA_DIR"])
        try:
            db_path = conn.execute("PRAGMA database_list").fetchone()["file"]
        finally:
            conn.close()
        return render_template("tenant/index.html", tenant=slug, db_path=db_path)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "app": "tenant"})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001)
