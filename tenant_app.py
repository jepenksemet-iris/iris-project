"""Tenant app — POS IRIS (tahap 7: produk & stok, skema v2).

Aplikasi operasional milik tenant. Modul produk & stok sudah ada:
tambah/edit/arsip produk, penyesuaian stok atomik dengan ledger
mutasi (stock_movements). Modul kasir/pembelian/penjualan/keuangan/
laporan masih belum diimplementasikan (lihat docs/MODULES.md).

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
import sqlite3

import click
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from config import get_config
from forms import ConfirmForm, LoginForm, ProductForm, StockAdjustForm
from iris_auth import TenantUser, require_role, setup_auth
from iris_db import (
    adjust_stock,
    create_product,
    create_user,
    get_default_outlet,
    get_or_create_category,
    get_or_create_unit,
    get_product,
    get_schema_version,
    get_stock_qty,
    get_tenant_db,
    init_tenant_db,
    list_categories,
    list_outlets,
    list_products,
    list_stock_movements,
    record_opening_balance,
    set_product_active,
    update_product,
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

    def _product_or_404(conn, product_id):
        product = get_product(conn, product_id)
        if product is None:
            abort(404)
        return product

    def _save_product(conn, form, product_id=None):
        """Simpan produk baru/edit dari ProductForm. Return (ok, pesan)."""
        category_id = get_or_create_category(conn, form.category.data)
        unit_id = get_or_create_unit(conn, form.unit.data)
        try:
            if product_id is None:
                create_product(
                    conn,
                    sku=form.sku.data,
                    name=form.name.data,
                    category_id=category_id,
                    unit_id=unit_id,
                    barcode=form.barcode.data,
                    buy_price=form.buy_price.data,
                    sell_price=form.sell_price.data,
                    min_stock=form.min_stock.data or 0,
                )
            else:
                update_product(
                    conn,
                    product_id,
                    sku=form.sku.data,
                    name=form.name.data,
                    category_id=category_id,
                    unit_id=unit_id,
                    barcode=form.barcode.data,
                    buy_price=form.buy_price.data,
                    sell_price=form.sell_price.data,
                    min_stock=form.min_stock.data or 0,
                )
        except sqlite3.IntegrityError:
            return False, "SKU atau barcode sudah dipakai produk lain."
        except ValueError as exc:
            return False, str(exc)
        return True, "Produk disimpan."

    @app.get("/products")
    @login_required
    def products():
        slug = session["tenant"]
        q = (request.args.get("q") or "").strip()
        include_inactive = request.args.get("tampilkan_nonaktif") == "1"
        try:
            category_id = int(request.args.get("kategori") or 0) or None
        except ValueError:
            category_id = None
        conn = get_tenant_db(slug, data_dir=app.config["DATA_DIR"])
        try:
            rows = list_products(
                conn, q=q or None, category_id=category_id,
                include_inactive=include_inactive,
            )
            categories = list_categories(conn)
        finally:
            conn.close()
        return render_template(
            "tenant/products.html",
            tenant=slug,
            products=rows,
            q=q,
            category_id=category_id,
            categories=categories,
            include_inactive=include_inactive,
            can_manage=current_user.role in ("owner", "admin"),
            confirm_form=ConfirmForm(),
        )

    @app.route("/products/new", methods=["GET", "POST"])
    @require_role("owner", "admin")
    def product_new():
        slug = session["tenant"]
        form = ProductForm()
        if form.validate_on_submit():
            conn = _db(slug)
            try:
                ok, msg = _save_product(conn, form)
            finally:
                conn.close()
            flash(msg, "success" if ok else "error")
            if ok:
                return redirect(url_for("products"))
        return render_template(
            "tenant/product_form.html", tenant=slug, form=form, product=None
        )

    @app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
    @require_role("owner", "admin")
    def product_edit(product_id):
        slug = session["tenant"]
        conn = _db(slug)
        try:
            product = _product_or_404(conn, product_id)
            form = ProductForm(obj=product)
            # obj tidak mengisi field teks kategori/satuan (disimpan sebagai id).
            if request.method == "GET":
                category = conn.execute(
                    "SELECT name FROM categories WHERE id = ?",
                    (product["category_id"],),
                ).fetchone() if product["category_id"] else None
                unit = conn.execute(
                    "SELECT name FROM units WHERE id = ?",
                    (product["unit_id"],),
                ).fetchone() if product["unit_id"] else None
                form.category.data = category["name"] if category else ""
                form.unit.data = unit["name"] if unit else ""
                form.barcode.data = product["barcode"] or ""
            if form.validate_on_submit():
                ok, msg = _save_product(conn, form, product_id=product_id)
                flash(msg, "success" if ok else "error")
                if ok:
                    return redirect(url_for("products"))
        finally:
            conn.close()
        return render_template(
            "tenant/product_form.html", tenant=slug, form=form, product=product
        )

    @app.post("/products/<int:product_id>/archive")
    @require_role("owner", "admin")
    def product_archive(product_id):
        slug = session["tenant"]
        form = ConfirmForm()
        if not form.validate_on_submit():
            abort(400)
        conn = _db(slug)
        try:
            _product_or_404(conn, product_id)
            set_product_active(conn, product_id, False)
        finally:
            conn.close()
        flash("Produk diarsipkan (nonaktif). Data historis tetap tersimpan.", "success")
        return redirect(url_for("products"))

    @app.post("/products/<int:product_id>/activate")
    @require_role("owner", "admin")
    def product_activate(product_id):
        slug = session["tenant"]
        form = ConfirmForm()
        if not form.validate_on_submit():
            abort(400)
        conn = _db(slug)
        try:
            _product_or_404(conn, product_id)
            set_product_active(conn, product_id, True)
        finally:
            conn.close()
        flash("Produk diaktifkan kembali.", "success")
        return redirect(url_for("products"))

    @app.route("/products/<int:product_id>/stock", methods=["GET", "POST"])
    @require_role("owner", "admin")
    def product_stock(product_id):
        slug = session["tenant"]
        form = StockAdjustForm()
        kind_filter = request.args.get("jenis") or ""
        date_from = request.args.get("dari") or ""
        date_to = request.args.get("sampai") or ""
        conn = _db(slug)
        try:
            product = _product_or_404(conn, product_id)
            get_default_outlet(conn)  # pastikan ada outlet untuk penyesuaian
            outlets = list_outlets(conn)
            form.outlet_id.choices = [(o["id"], o["name"]) for o in outlets]
            if form.validate_on_submit():
                qty = form.qty_delta.data
                effective = (
                    form.effective_date.data.isoformat()
                    if form.effective_date.data else None
                )
                try:
                    if not qty or qty <= 0:
                        raise ValueError("Jumlah harus lebih dari 0.")
                    if form.kind.data == "opening_balance":
                        new_qty = record_opening_balance(
                            conn, product_id, form.outlet_id.data, qty,
                            note=form.note.data or "",
                            user_id=current_user.row_id,
                            effective_date=effective,
                        )
                        flash(f"Saldo awal dicatat. Stok sekarang: {new_qty:g}.", "success")
                    else:
                        delta = qty if form.kind.data == "adjustment_in" else -qty
                        new_qty = adjust_stock(
                            conn, product_id, form.outlet_id.data, delta,
                            note=form.note.data or "",
                            user_id=current_user.row_id,
                            kind=form.kind.data, effective_date=effective,
                        )
                        flash(f"Stok disesuaikan. Stok sekarang: {new_qty:g}.", "success")
                    return redirect(url_for("product_stock", product_id=product_id))
                except ValueError as exc:
                    flash(str(exc), "error")
            stock_rows = [
                {"outlet": o, "qty": get_stock_qty(conn, product_id, o["id"])}
                for o in outlets
            ]
            movements = list_stock_movements(
                conn, product_id=product_id,
                kind=kind_filter or None,
                date_from=date_from or None, date_to=date_to or None,
                limit=100,
            )
            # Saldo berjalan dihitung dari mutasi tertua; hanya benar
            # bila tidak ada filter (semua mutasi produk ditampilkan).
            movements = [dict(m) for m in movements]
            if not kind_filter and not date_from and not date_to:
                running = 0
                for m in reversed(movements):
                    running += m["qty"]
                    m["balance"] = running
                for m in movements:
                    m["in_qty"] = m["qty"] if m["qty"] > 0 else None
                    m["out_qty"] = -m["qty"] if m["qty"] < 0 else None
            else:
                for m in movements:
                    m["balance"] = None
                    m["in_qty"] = m["qty"] if m["qty"] > 0 else None
                    m["out_qty"] = -m["qty"] if m["qty"] < 0 else None
        finally:
            conn.close()
        return render_template(
            "tenant/product_stock.html",
            tenant=slug,
            product=product,
            form=form,
            stock_rows=stock_rows,
            movements=movements,
            kind_filter=kind_filter,
            date_from=date_from,
            date_to=date_to,
        )

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
