"""Tenant app — POS IRIS (tahap 11: P1 tahap 6 modul pembelian, skema v5).

Aplikasi operasional milik tenant. Modul produk & stok sudah ada:
tambah/edit/arsip produk, penyesuaian stok atomik dengan ledger
mutasi (stock_movements). Modul kasir: halaman + keranjang (tahap 2),
checkout atomik + riwayat/detail/struk (tahap 3), pembatalan (tahap 5).
Modul pembelian (tahap 6): pemasok + transaksi pembelian yang langsung
diterima (stok bertambah atomik lewat ledger kind='purchase') +
pembatalan pembelian (lihat docs/MODULES.md).

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
import json
import os
import sqlite3
import uuid

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
from forms import (
    CartAddForm,
    CartRemoveForm,
    CartSetForm,
    CheckoutForm,
    ConfirmForm,
    LoginForm,
    ProductForm,
    PurchaseForm,
    ReturnForm,
    StockAdjustForm,
    SupplierForm,
    VoidForm,
)
from iris_auth import TenantUser, require_role, setup_auth
from iris_db import (
    PAYMENT_METHODS,
    PURCHASE_STATUSES,
    RETURN_KINDS,
    RETURN_STATUSES,
    SALE_STATUSES,
    adjust_stock,
    cancel_purchase,
    cancel_return,
    confirm_payment,
    create_product,
    create_purchase,
    create_purchase_return,
    create_sale,
    create_sale_return,
    create_supplier,
    create_user,
    get_default_outlet,
    get_purchase,
    get_return,
    get_sale,
    get_supplier,
    get_or_create_category,
    get_or_create_unit,
    get_product,
    get_schema_version,
    get_stock_qty,
    get_tenant_db,
    init_tenant_db,
    list_categories,
    list_outlets,
    _returned_qty,
    list_products,
    list_purchases,
    list_returns,
    list_returns_for_origin,
    list_sales,
    list_stock_movements,
    list_suppliers,
    set_supplier_active,
    update_supplier,
    void_sale,
    record_opening_balance,
    search_products,
    set_product_active,
    summarize_cart,
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
        # Selalu pastikan skema terbaru sudah diterapkan sebelum dipakai.
        return init_tenant_db(slug, data_dir=app.config["DATA_DIR"])

    # -- Keranjang kasir (session, per tenant) -------------------------
    # Keranjang belum menjadi transaksi: tidak menulis database apa pun.
    # Harga/stok/total selalu dihitung ulang dari database oleh
    # summarize_cart() setiap kali ditampilkan atau diubah.
    def _get_cart(slug):
        cart = session.get("pos_cart") or {}
        if cart.get("tenant") != slug:
            return []
        items = []
        for item in cart.get("items") or []:
            try:
                items.append({
                    "product_id": int(item["product_id"]),
                    "qty": float(item["qty"]),
                })
            except (KeyError, TypeError, ValueError):
                continue
        return items

    def _save_cart(slug, items):
        session["pos_cart"] = {"tenant": slug, "items": items}

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

    # -- Kasir (P1 tahap 2: halaman + keranjang, tanpa posting) --------
    @app.get("/pos")
    @login_required
    def pos():
        slug = session["tenant"]
        q = (request.args.get("q") or "").strip()
        conn = _db(slug)
        try:
            outlet = get_default_outlet(conn)
            results = search_products(conn, q, outlet_id=outlet["id"]) if q else []
            items = _get_cart(slug)
            lines, total_qty, total, errors = summarize_cart(
                conn, items, outlet["id"])
        finally:
            conn.close()
        checkout_form = CheckoutForm()
        checkout_form.idempotency_key.data = uuid.uuid4().hex
        return render_template(
            "pos/cashier.html",
            tenant=slug,
            q=q,
            results=results,
            lines=lines,
            total_qty=total_qty,
            total=total,
            cart_errors=errors,
            add_form=CartAddForm(),
            set_form=CartSetForm(),
            remove_form=CartRemoveForm(),
            clear_form=ConfirmForm(),
            checkout_form=checkout_form,
        )

    @app.post("/pos/checkout")
    @login_required
    def pos_checkout():
        slug = session["tenant"]
        form = CheckoutForm()
        if not form.validate_on_submit():
            for field_errors in form.errors.values():
                for err in field_errors:
                    flash(err, "error")
            return redirect(url_for("pos"))
        conn = _db(slug)
        try:
            items = _get_cart(slug)
            if not items:
                # Keranjang sudah dikosongkan setelah checkout berhasil:
                # pengiriman ulang form yang sama (token sama) tetap
                # mengembalikan transaksi yang sudah terbentuk.
                existing = conn.execute(
                    "SELECT id FROM sales WHERE idempotency_key = ?",
                    (form.idempotency_key.data.strip(),),
                ).fetchone()
                if existing is not None:
                    flash("Transaksi sudah pernah diproses.", "success")
                    return redirect(url_for(
                        "sale_detail", sale_id=existing["id"]))
                flash("Keranjang kosong.", "error")
                return redirect(url_for("pos"))
            outlet = get_default_outlet(conn)
            try:
                sale_id, replayed = create_sale(
                    conn,
                    outlet["id"],
                    current_user.row_id,
                    items,
                    form.payment_method.data,
                    amount_tendered=form.amount_tendered.data,
                    payment_ref=form.payment_ref.data,
                    idempotency_key=form.idempotency_key.data.strip(),
                )
            except (ValueError, sqlite3.IntegrityError) as exc:
                flash(str(exc), "error")
                return redirect(url_for("pos"))
            _save_cart(slug, [])
            data = get_sale(conn, sale_id)
        finally:
            conn.close()
        invoice = data["sale"]["invoice_no"]
        if replayed:
            flash(f"Transaksi sudah pernah diproses: {invoice}.", "success")
        elif data["sale"]["status"] == "pending":
            flash(
                f"Transaksi {invoice} tersimpan (pending) — pembayaran"
                " non-tunai dicatat manual dan menunggu konfirmasi"
                " owner/admin.", "success")
        else:
            flash(
                f"Transaksi {invoice} berhasil."
                f" Kembalian: Rp {data['sale']['change_amount']}.", "success")
        return redirect(url_for("sale_detail", sale_id=sale_id))

    @app.get("/sales")
    @login_required
    def sales_list():
        from datetime import datetime

        def _valid_date(value):
            try:
                datetime.strptime(value, "%Y-%m-%d")
                return value
            except (TypeError, ValueError):
                return None

        slug = session["tenant"]
        q = (request.args.get("q") or "").strip()
        date_from = _valid_date(request.args.get("dari") or "")
        date_to = _valid_date(request.args.get("sampai") or "")
        status = request.args.get("status") or ""
        payment_method = request.args.get("metode") or ""
        order = request.args.get("urut") or "newest"
        if order not in ("newest", "oldest"):
            order = "newest"
        conn = _db(slug)
        try:
            rows = list_sales(
                conn, q=q or None,
                date_from=date_from, date_to=date_to,
                status=status or None,
                payment_method=payment_method or None, order=order,
            )
        finally:
            conn.close()
        return render_template(
            "pos/sales_list.html", tenant=slug, sales=rows, q=q,
            date_from=date_from or "", date_to=date_to or "",
            status=status, payment_method=payment_method, order=order,
            statuses=SALE_STATUSES, methods=PAYMENT_METHODS,
        )

    @app.get("/sales/<int:sale_id>")
    @login_required
    def sale_detail(sale_id):
        slug = session["tenant"]
        conn = _db(slug)
        try:
            data = get_sale(conn, sale_id)
            returns = (list_returns_for_origin(conn, "sale_return", sale_id)
                       if data is not None else [])
        finally:
            conn.close()
        if data is None:
            abort(404)
        sale = data["sale"]
        payment_status = (
            "Lunas" if sale["status"] == "completed" and sale["paid"] >= sale["total"]
            else "Belum terverifikasi" if sale["status"] == "pending"
            else "Dibatalkan" if sale["status"] == "void"
            else "Diretur" if sale["status"] == "returned"
            else sale["status"])
        return render_template(
            "pos/sale_detail.html", tenant=slug, **data,
            confirm_form=ConfirmForm(), void_form=VoidForm(),
            payment_status=payment_status,
            can_void=current_user.role in ("owner", "admin"),
            returns=returns,
            can_return=current_user.role in ("owner", "admin"),
        )

    @app.get("/sales/<int:sale_id>/receipt")
    @login_required
    def sale_receipt(sale_id):
        slug = session["tenant"]
        conn = _db(slug)
        try:
            data = get_sale(conn, sale_id)
        finally:
            conn.close()
        if data is None:
            abort(404)
        return render_template("pos/receipt.html", tenant=slug, **data)

    @app.post("/sales/<int:sale_id>/void")
    @require_role("owner", "admin")
    def sale_void(sale_id):
        slug = session["tenant"]
        form = VoidForm()
        if not form.validate_on_submit():
            for field_errors in form.errors.values():
                for err in field_errors:
                    flash(err, "error")
            return redirect(url_for("sale_detail", sale_id=sale_id))
        conn = _db(slug)
        try:
            if get_sale(conn, sale_id) is None:
                abort(404)
            try:
                void_sale(conn, sale_id, current_user.row_id,
                          form.reason.data)
            except (ValueError, sqlite3.IntegrityError) as exc:
                flash(str(exc), "error")
            else:
                flash("Transaksi dibatalkan dan stok dikembalikan.", "success")
        finally:
            conn.close()
        return redirect(url_for("sale_detail", sale_id=sale_id))

    # ------------------------------------------------------------------
    # Pemasok & pembelian (P1 Tahap 6)
    # ------------------------------------------------------------------
    def _parse_purchase_items():
        """Baca baris item dinamis dari form: product_id/qty/price
        berulang. Baris kosong diabaikan; nilai tidak valid -> ValueError
        dengan pesan yang jelas. Total TIDAK dibaca dari browser."""
        pids = request.form.getlist("product_id")
        qtys = request.form.getlist("qty")
        prices = request.form.getlist("price")
        if not (len(pids) == len(qtys) == len(prices)):
            raise ValueError("baris item tidak konsisten")
        items = []
        for pid, qty, price in zip(pids, qtys, prices):
            if not pid:
                continue
            try:
                product_id = int(pid)
                qty_val = float(qty)
                price_val = int(float(price))
            except (TypeError, ValueError):
                raise ValueError("kuantitas atau harga item tidak valid")
            items.append({"product_id": product_id, "qty": qty_val,
                          "price": price_val})
        return items

    @app.get("/suppliers")
    @login_required
    def suppliers_list():
        slug = session["tenant"]
        q = (request.args.get("q") or "").strip()
        include_inactive = request.args.get("tampilkan_nonaktif") == "1"
        conn = _db(slug)
        try:
            rows = list_suppliers(conn, q=q or None,
                                  include_inactive=include_inactive)
        finally:
            conn.close()
        return render_template(
            "purchases/suppliers.html", tenant=slug, suppliers=rows, q=q,
            include_inactive=include_inactive,
            confirm_form=ConfirmForm(),
        )

    @app.route("/suppliers/new", methods=["GET", "POST"])
    @require_role("owner", "admin")
    def supplier_new():
        slug = session["tenant"]
        form = SupplierForm()
        if form.validate_on_submit():
            conn = _db(slug)
            try:
                try:
                    create_supplier(conn, form.name.data, form.phone.data,
                                    form.address.data, form.notes.data)
                except ValueError as exc:
                    flash(str(exc), "error")
                else:
                    flash("Pemasok ditambahkan.", "success")
                    return redirect(url_for("suppliers_list"))
            finally:
                conn.close()
        return render_template(
            "purchases/supplier_form.html", tenant=slug, form=form,
            title="Tambah Pemasok",
        )

    @app.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
    @require_role("owner", "admin")
    def supplier_edit(supplier_id):
        slug = session["tenant"]
        conn = _db(slug)
        try:
            supplier = get_supplier(conn, supplier_id)
        finally:
            conn.close()
        if supplier is None:
            abort(404)
        form = SupplierForm(obj=supplier)
        if form.validate_on_submit():
            conn = _db(slug)
            try:
                try:
                    update_supplier(conn, supplier_id, form.name.data,
                                    form.phone.data, form.address.data,
                                    form.notes.data)
                except ValueError as exc:
                    flash(str(exc), "error")
                else:
                    flash("Pemasok diperbarui.", "success")
                    return redirect(url_for("suppliers_list"))
            finally:
                conn.close()
        return render_template(
            "purchases/supplier_form.html", tenant=slug, form=form,
            title="Edit Pemasok",
        )

    @app.post("/suppliers/<int:supplier_id>/archive")
    @require_role("owner", "admin")
    def supplier_archive(supplier_id):
        return _set_supplier(supplier_id, False)

    @app.post("/suppliers/<int:supplier_id>/activate")
    @require_role("owner", "admin")
    def supplier_activate(supplier_id):
        return _set_supplier(supplier_id, True)

    def _set_supplier(supplier_id, active):
        slug = session["tenant"]
        form = ConfirmForm()
        if not form.validate_on_submit():
            flash("Token tidak valid.", "error")
            return redirect(url_for("suppliers_list"))
        conn = _db(slug)
        try:
            try:
                set_supplier_active(conn, supplier_id, active)
            except ValueError as exc:
                flash(str(exc), "error")
            else:
                flash("Pemasok " + ("diaktifkan." if active else "diarsipkan."),
                      "success")
        finally:
            conn.close()
        return redirect(url_for("suppliers_list"))

    @app.get("/purchases")
    @login_required
    def purchases_list():
        from datetime import datetime

        def _valid_date(value):
            try:
                datetime.strptime(value, "%Y-%m-%d")
                return value
            except (TypeError, ValueError):
                return None

        slug = session["tenant"]
        q = (request.args.get("q") or "").strip()
        supplier_id = request.args.get("pemasok") or ""
        status = request.args.get("status") or ""
        date_from = _valid_date(request.args.get("dari") or "")
        date_to = _valid_date(request.args.get("sampai") or "")
        order = request.args.get("urut") or "newest"
        if order not in ("newest", "oldest"):
            order = "newest"
        conn = _db(slug)
        try:
            suppliers = list_suppliers(conn, include_inactive=True)
            rows = list_purchases(
                conn, q=q or None,
                supplier_id=int(supplier_id) if supplier_id.isdigit() else None,
                status=status or None, date_from=date_from, date_to=date_to,
                order=order,
            )
        finally:
            conn.close()
        return render_template(
            "purchases/purchases_list.html", tenant=slug, purchases=rows,
            q=q, supplier_id=supplier_id, status=status,
            date_from=date_from or "", date_to=date_to or "",
            order=order, suppliers=suppliers, statuses=PURCHASE_STATUSES,
        )

    @app.route("/purchases/new", methods=["GET", "POST"])
    @require_role("owner", "admin")
    def purchase_new():
        slug = session["tenant"]
        conn = _db(slug)
        try:
            suppliers = list_suppliers(conn)
            products = list_products(conn, limit=500)
            form = PurchaseForm()
            form.supplier_id.choices = [(0, "— Tanpa pemasok —")] + [
                (s["id"], s["name"]) for s in suppliers
            ]
        finally:
            conn.close()
        if form.validate_on_submit():
            try:
                items = _parse_purchase_items()
            except ValueError as exc:
                flash(str(exc), "error")
                return render_template(
                    "purchases/purchase_form.html", tenant=slug, form=form,
                    products=products, suppliers=suppliers)
            conn = _db(slug)
            try:
                outlet = get_default_outlet(conn)
                try:
                    purchase_id = create_purchase(
                        conn, outlet["id"], current_user.row_id, items,
                        supplier_id=(form.supplier_id.data or None),
                        notes=form.notes.data,
                    )
                except (ValueError, sqlite3.IntegrityError) as exc:
                    flash(str(exc), "error")
                    return render_template(
                        "purchases/purchase_form.html", tenant=slug,
                        form=form, products=products, suppliers=suppliers)
            finally:
                conn.close()
            flash("Pembelian tersimpan dan stok bertambah.", "success")
            return redirect(url_for("purchase_detail",
                                    purchase_id=purchase_id))
        if request.method == "POST":
            for field_errors in form.errors.values():
                for err in field_errors:
                    flash(err, "error")
        return render_template(
            "purchases/purchase_form.html", tenant=slug, form=form,
            products=products, suppliers=suppliers)

    @app.get("/purchases/<int:purchase_id>")
    @login_required
    def purchase_detail(purchase_id):
        slug = session["tenant"]
        conn = _db(slug)
        try:
            data = get_purchase(conn, purchase_id)
            returns = (list_returns_for_origin(conn, "purchase_return",
                                               purchase_id)
                       if data is not None else [])
        finally:
            conn.close()
        if data is None:
            abort(404)
        return render_template(
            "purchases/purchase_detail.html", tenant=slug, **data,
            void_form=VoidForm(),
            can_cancel=current_user.role in ("owner", "admin"),
            returns=returns,
            can_return=current_user.role in ("owner", "admin"),
        )

    @app.post("/purchases/<int:purchase_id>/cancel")
    @require_role("owner", "admin")
    def purchase_cancel(purchase_id):
        slug = session["tenant"]
        form = VoidForm()
        if not form.validate_on_submit():
            for field_errors in form.errors.values():
                for err in field_errors:
                    flash(err, "error")
            return redirect(url_for("purchase_detail",
                                    purchase_id=purchase_id))
        conn = _db(slug)
        try:
            if get_purchase(conn, purchase_id) is None:
                abort(404)
            try:
                cancel_purchase(conn, purchase_id, current_user.row_id,
                                form.reason.data)
            except (ValueError, sqlite3.IntegrityError) as exc:
                flash(str(exc), "error")
            else:
                flash("Pembelian dibatalkan dan stok dikembalikan.",
                      "success")
        finally:
            conn.close()
        return redirect(url_for("purchase_detail",
                                purchase_id=purchase_id))

    # ------------------------------------------------------------------
    # Retur penjualan & pembelian (P1 Tahap 7)
    # ------------------------------------------------------------------
    def _parse_return_items():
        """Baca item retur dari form: product_id/qty berulang.
        Baris dengan qty kosong/0 diabaikan."""
        pids = request.form.getlist("product_id")
        qtys = request.form.getlist("qty")
        if len(pids) != len(qtys):
            raise ValueError("baris item retur tidak konsisten")
        items = []
        for pid, qty in zip(pids, qtys):
            if not pid:
                continue
            try:
                qty_val = float(qty)
            except (TypeError, ValueError):
                raise ValueError("kuantitas retur tidak valid")
            if qty_val <= 0:
                continue
            try:
                product_id = int(pid)
            except (TypeError, ValueError):
                raise ValueError("produk retur tidak valid")
            items.append({"product_id": product_id, "qty": qty_val})
        return items

    def _returnable_items(conn, kind, origin_id, origin_items):
        """Item asal + sisa kuantitas yang masih bisa diretur."""
        out = []
        for item in origin_items:
            returned = _returned_qty(conn, kind, origin_id,
                                     item["product_id"])
            remaining = item["qty"] - returned
            out.append({"item": item, "returned": returned,
                        "remaining": remaining})
        return out

    @app.route("/sales/<int:sale_id>/return", methods=["GET", "POST"])
    @require_role("owner", "admin")
    def sale_return(sale_id):
        slug = session["tenant"]
        conn = _db(slug)
        try:
            data = get_sale(conn, sale_id)
            if data is None:
                abort(404)
            returnable = _returnable_items(conn, "sale_return", sale_id,
                                           data["items"])
        finally:
            conn.close()
        form = ReturnForm()
        if request.method == "GET" and not form.idempotency_key.data:
            form.idempotency_key.data = uuid.uuid4().hex
        if form.validate_on_submit():
            try:
                items = _parse_return_items()
            except ValueError as exc:
                flash(str(exc), "error")
                return render_template(
                    "returns/return_form.html", tenant=slug, form=form,
                    kind="sale_return", origin=data, returnable=returnable)
            payload = json.dumps(
                {"sale_id": sale_id, "items": items,
                 "reason": form.reason.data}, sort_keys=True)
            conn = _db(slug)
            try:
                try:
                    return_id = create_sale_return(
                        conn, sale_id, current_user.row_id, items,
                        form.reason.data, form.notes.data,
                        idempotency_key=form.idempotency_key.data,
                        idempotency_payload=payload,
                    )
                except (ValueError, sqlite3.IntegrityError) as exc:
                    flash(str(exc), "error")
                    return render_template(
                        "returns/return_form.html", tenant=slug, form=form,
                        kind="sale_return", origin=data,
                        returnable=returnable)
            finally:
                conn.close()
            flash("Retur penjualan tersimpan dan stok bertambah.", "success")
            return redirect(url_for("return_detail", return_id=return_id))
        return render_template(
            "returns/return_form.html", tenant=slug, form=form,
            kind="sale_return", origin=data, returnable=returnable)

    @app.route("/purchases/<int:purchase_id>/return",
               methods=["GET", "POST"])
    @require_role("owner", "admin")
    def purchase_return(purchase_id):
        slug = session["tenant"]
        conn = _db(slug)
        try:
            data = get_purchase(conn, purchase_id)
            if data is None:
                abort(404)
            returnable = _returnable_items(conn, "purchase_return",
                                           purchase_id, data["items"])
        finally:
            conn.close()
        form = ReturnForm()
        if request.method == "GET" and not form.idempotency_key.data:
            form.idempotency_key.data = uuid.uuid4().hex
        if form.validate_on_submit():
            try:
                items = _parse_return_items()
            except ValueError as exc:
                flash(str(exc), "error")
                return render_template(
                    "returns/return_form.html", tenant=slug, form=form,
                    kind="purchase_return", origin=data,
                    returnable=returnable)
            payload = json.dumps(
                {"purchase_id": purchase_id, "items": items,
                 "reason": form.reason.data}, sort_keys=True)
            conn = _db(slug)
            try:
                try:
                    return_id = create_purchase_return(
                        conn, purchase_id, current_user.row_id, items,
                        form.reason.data, form.notes.data,
                        idempotency_key=form.idempotency_key.data,
                        idempotency_payload=payload,
                    )
                except (ValueError, sqlite3.IntegrityError) as exc:
                    flash(str(exc), "error")
                    return render_template(
                        "returns/return_form.html", tenant=slug, form=form,
                        kind="purchase_return", origin=data,
                        returnable=returnable)
            finally:
                conn.close()
            flash("Retur pembelian tersimpan dan stok berkurang.", "success")
            return redirect(url_for("return_detail", return_id=return_id))
        return render_template(
            "returns/return_form.html", tenant=slug, form=form,
            kind="purchase_return", origin=data, returnable=returnable)

    @app.get("/returns")
    @login_required
    def returns_list():
        from datetime import datetime

        def _valid_date(value):
            try:
                datetime.strptime(value, "%Y-%m-%d")
                return value
            except (TypeError, ValueError):
                return None

        slug = session["tenant"]
        q = (request.args.get("q") or "").strip()
        kind = request.args.get("jenis") or ""
        status = request.args.get("status") or ""
        date_from = _valid_date(request.args.get("dari") or "")
        date_to = _valid_date(request.args.get("sampai") or "")
        order = request.args.get("urut") or "newest"
        if order not in ("newest", "oldest"):
            order = "newest"
        conn = _db(slug)
        try:
            rows = list_returns(conn, q=q or None, kind=kind or None,
                                status=status or None,
                                date_from=date_from, date_to=date_to,
                                order=order)
        finally:
            conn.close()
        return render_template(
            "returns/returns_list.html", tenant=slug, returns=rows, q=q,
            kind=kind, status=status, date_from=date_from or "",
            date_to=date_to or "", order=order, kinds=RETURN_KINDS,
            statuses=RETURN_STATUSES,
        )

    @app.get("/returns/<int:return_id>")
    @login_required
    def return_detail(return_id):
        slug = session["tenant"]
        conn = _db(slug)
        try:
            data = get_return(conn, return_id)
        finally:
            conn.close()
        if data is None:
            abort(404)
        return render_template(
            "returns/return_detail.html", tenant=slug, **data,
            void_form=VoidForm(),
            can_cancel=current_user.role in ("owner", "admin"),
        )

    @app.post("/returns/<int:return_id>/cancel")
    @require_role("owner", "admin")
    def return_cancel(return_id):
        slug = session["tenant"]
        form = VoidForm()
        if not form.validate_on_submit():
            for field_errors in form.errors.values():
                for err in field_errors:
                    flash(err, "error")
            return redirect(url_for("return_detail", return_id=return_id))
        conn = _db(slug)
        try:
            if get_return(conn, return_id) is None:
                abort(404)
            try:
                cancel_return(conn, return_id, current_user.row_id,
                              form.reason.data)
            except (ValueError, sqlite3.IntegrityError) as exc:
                flash(str(exc), "error")
            else:
                flash("Retur dibatalkan dan stok dikembalikan.", "success")
        finally:
            conn.close()
        return redirect(url_for("return_detail", return_id=return_id))

    @app.post("/sales/<int:sale_id>/confirm-payment")
    @require_role("owner", "admin")
    def sale_confirm_payment(sale_id):
        slug = session["tenant"]
        form = ConfirmForm()
        if not form.validate_on_submit():
            flash("Token tidak valid.", "error")
            return redirect(url_for("sale_detail", sale_id=sale_id))
        conn = _db(slug)
        try:
            try:
                confirm_payment(conn, sale_id, current_user.row_id)
            except ValueError as exc:
                flash(str(exc), "error")
            else:
                flash("Pembayaran dikonfirmasi.", "success")
        finally:
            conn.close()
        return redirect(url_for("sale_detail", sale_id=sale_id))

    def _apply_cart_change(slug, form, change):
        """Validasi perubahan keranjang terhadap database, lalu simpan
        ke session bila valid. Mengembalikan True bila tersimpan."""
        if not form.validate_on_submit():
            for field_errors in form.errors.values():
                for err in field_errors:
                    flash(err, "error")
            return False
        conn = _db(slug)
        try:
            outlet = get_default_outlet(conn)
            items = _get_cart(slug)
            new_items = change(items, form)
            if new_items is None:
                return False
            _, _, _, errors = summarize_cart(conn, new_items, outlet["id"])
            if errors:
                for err in errors:
                    flash(err, "error")
                return False
            _save_cart(slug, new_items)
            return True
        finally:
            conn.close()

    @app.post("/pos/cart/add")
    @login_required
    def pos_cart_add():
        slug = session["tenant"]
        form = CartAddForm()

        def change(items, form):
            qty = form.qty.data
            if not qty or qty <= 0:
                flash("Kuantitas harus lebih dari 0.", "error")
                return None
            items = [dict(i) for i in items]
            for item in items:
                if item["product_id"] == form.product_id.data:
                    item["qty"] = item["qty"] + qty
                    return items
            items.append({"product_id": form.product_id.data, "qty": qty})
            return items

        _apply_cart_change(slug, form, change)
        return redirect(url_for("pos", q=request.args.get("q", "")))

    @app.post("/pos/cart/set")
    @login_required
    def pos_cart_set():
        slug = session["tenant"]
        form = CartSetForm()

        def change(items, form):
            qty = form.qty.data
            if qty is None or qty < 0:
                flash("Kuantitas tidak boleh negatif.", "error")
                return None
            items = [dict(i) for i in items]
            for item in items:
                if item["product_id"] == form.product_id.data:
                    if qty == 0:
                        return [i for i in items
                                if i["product_id"] != form.product_id.data]
                    item["qty"] = qty
                    return items
            flash("Item tidak ada di keranjang.", "error")
            return None

        _apply_cart_change(slug, form, change)
        return redirect(url_for("pos", q=request.args.get("q", "")))

    @app.post("/pos/cart/remove")
    @login_required
    def pos_cart_remove():
        slug = session["tenant"]
        form = CartRemoveForm()
        if form.validate_on_submit():
            items = [i for i in _get_cart(slug)
                     if i["product_id"] != form.product_id.data]
            _save_cart(slug, items)
        return redirect(url_for("pos", q=request.args.get("q", "")))

    @app.post("/pos/cart/clear")
    @login_required
    def pos_cart_clear():
        slug = session["tenant"]
        form = ConfirmForm()
        if form.validate_on_submit():
            _save_cart(slug, [])
        return redirect(url_for("pos"))

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
