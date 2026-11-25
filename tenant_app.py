"""Tenant app — POS IRIS (tahap 3: skema v1 + autentikasi).

Aplikasi operasional milik tenant. Modul kasir/produk/stok/pembelian
masih belum diimplementasikan (lihat docs/MODULES.md), tapi fondasinya
sudah ada: database tenant dibuat dengan skema v1 dan dashboard
dilindungi login.

Jalan di port 5001. Identitas tenant berasal dari LOGIN (disimpan di
session), bukan lagi dari query ``?tenant=``.

Buat pengguna pertama (owner) untuk sebuah tenant:
    flask --app tenant_app create-owner --tenant toko-demo \
        --username owner --password 'minimal-8-karakter'

Jalankan:
    python tenant_app.py
atau:
    flask --app tenant_app run --port 5001
"""
import os

import click
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from config import get_config
from forms import LoginForm
from iris_auth import TenantUser, require_role, setup_auth
from iris_db import (
    create_user,
    get_schema_version,
    get_tenant_db,
    init_tenant_db,
    validate_tenant_slug,
    verify_user,
)


def create_app(config_class=None):
    app = Flask(__name__)
    app.config.from_object(config_class or get_config())
    setup_auth(app)

    if os.environ.get("FLASK_ENV") == "production" and app.config["SECRET_KEY"] == "dev-only-change-me":
        raise RuntimeError("SECRET_KEY production belum diset di environment")

    def _db(slug):
        # Selalu pastikan skema v1 sudah diterapkan sebelum dipakai.
        return init_tenant_db(slug, data_dir=app.config["DATA_DIR"])

    @app.get("/")
    @login_required
    def index():
        slug = session["tenant"]
        conn = get_tenant_db(slug, data_dir=app.config["DATA_DIR"])
        try:
            products = conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
            users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
            schema_version = get_schema_version(conn)
        finally:
            conn.close()
        return render_template(
            "tenant/index.html",
            tenant=slug,
            user=current_user,
            products=products,
            users=users,
            schema_version=schema_version,
        )

    @app.get("/products")
    @login_required
    def products():
        slug = session["tenant"]
        conn = get_tenant_db(slug, data_dir=app.config["DATA_DIR"])
        try:
            rows = conn.execute(
                "SELECT p.sku, p.name, p.sell_price, c.name AS category"
                " FROM products p LEFT JOIN categories c ON c.id = p.category_id"
                " ORDER BY p.name LIMIT 100"
            ).fetchall()
        finally:
            conn.close()
        return render_template("tenant/products.html", tenant=slug, products=rows)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        form = LoginForm()
        if form.validate_on_submit():
            slug = form.tenant.data.strip().lower()
            if not validate_tenant_slug(slug):
                flash("Tenant tidak valid.", "error")
                return render_template("tenant/login.html", form=form)
            conn = _db(slug)
            try:
                user = verify_user(conn, form.username.data.strip(), form.password.data)
            finally:
                conn.close()
            if not user:
                flash("Username, password, atau tenant salah.", "error")
                return render_template("tenant/login.html", form=form)
            login_user(TenantUser(slug, user))
            session["tenant"] = slug
            return redirect(url_for("index"))
        return render_template("tenant/login.html", form=form)

    @app.get("/logout")
    @login_required
    def logout():
        logout_user()
        session.pop("tenant", None)
        return redirect(url_for("login"))

    @app.get("/admin-only")
    @require_role("owner", "admin")
    def admin_only():
        return jsonify({"ok": True, "role": current_user.role})

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "app": "tenant"})

    @app.cli.command("create-owner")
    @click.option("--tenant", required=True, help="Slug tenant, contoh: toko-demo")
    @click.option("--username", required=True)
    @click.option("--password", required=True, help="Minimal 8 karakter")
    @click.option("--full-name", default="")
    def create_owner(tenant, username, password, full_name):
        """Buat pengguna owner pertama untuk sebuah tenant."""
        if not validate_tenant_slug(tenant):
            raise click.ClickException(f"tenant slug tidak valid: {tenant!r}")
        conn = _db(tenant)
        try:
            user_id = create_user(conn, username, password, full_name, role="owner")
        finally:
            conn.close()
        click.echo(f"Owner dibuat: {username} (id={user_id}) untuk tenant {tenant}")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001)
