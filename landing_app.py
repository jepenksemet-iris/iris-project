"""Landing app — POS IRIS (skeleton tahap 2).

Situs publik: informasi produk, paket, pendaftaran.
Jalan di port 5000 (sesuai dokumen proyek; verifikasi sebelum deployment).

Jalankan:
    python landing_app.py
atau:
    flask --app landing_app run --port 5000
"""
import os
from flask import Flask, jsonify, render_template

from config import get_config


def create_app(config_class=None):
    app = Flask(__name__)
    app.config.from_object(config_class or get_config())

    if os.environ.get("FLASK_ENV") == "production" and app.config["SECRET_KEY"] == "dev-only-change-me":
        raise RuntimeError("SECRET_KEY production belum diset di environment")

    @app.get("/")
    def index():
        return render_template("landing/index.html")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "app": "landing"})

    @app.get("/register")
    def register():
        # Placeholder skeleton: alur pendaftaran & provisioning tenant
        # (dokumen: docs/TENANT_PROVISIONING.md) belum diimplementasikan.
        return render_template("landing/register.html"), 200

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
