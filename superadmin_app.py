"""Super Admin app — POS IRIS (skeleton tahap 2).

Pengelolaan platform dan tenant (belum diimplementasikan).
Jalan di port 5002.

PERINGATAN: skeleton ini BELUM memiliki autentikasi/otorisasi.
Jangan mengekspos aplikasi ini ke internet sebelum login dan
role-based access control ditambahkan.

Jalankan:
    python superadmin_app.py
atau:
    flask --app superadmin_app run --port 5002
"""
import os
from flask import Flask, jsonify, render_template

from config import get_config
from iris_db import list_tenants


def create_app(config_class=None):
    app = Flask(__name__)
    app.config.from_object(config_class or get_config())

    if os.environ.get("FLASK_ENV") == "production" and app.config["SECRET_KEY"] == "dev-only-change-me":
        raise RuntimeError("SECRET_KEY production belum diset di environment")

    @app.get("/")
    def index():
        return render_template(
            "superadmin/index.html",
            tenants=list_tenants(data_dir=app.config["DATA_DIR"]),
        )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "app": "superadmin"})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002)
