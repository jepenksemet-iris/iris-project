"""Akses database SQLite per tenant (tahap 7: skema v2 + produk & stok).

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

SCHEMA_VERSION = 2
_SCHEMA_PATH = Path(__file__).with_name("iris_schema.sql")

# Jenis mutasi stok yang sah (skema v2). 'adjustment' dipertahankan
# untuk kompatibilitas data lama; form baru memakai opening_balance /
# adjustment_in / adjustment_out.
STOCK_MOVEMENT_KINDS = (
    "sale", "purchase", "adjustment", "return", "transfer",
    "opening_balance", "adjustment_in", "adjustment_out",
)

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


def migrate_tenant_db(conn, from_version):
    """Migrasikan database tenant ke SCHEMA_VERSION.

    v1 -> v2: CHECK constraint SQLite tidak bisa diubah dengan ALTER,
    jadi tabel stock_movements dibuat ulang (buat tabel baru, salin
    data, hapus lama, ganti nama) dalam satu transaksi — gagal di
    tengah berarti tabel lama tetap utuh. Pemetaan jenis lama:
    'adjustment' + catatan diawali 'Saldo awal' -> 'opening_balance',
    'adjustment' positif -> 'adjustment_in', negatif -> 'adjustment_out',
    jenis lain tidak berubah. Kolom effective_date ditambah (NULL untuk
    data lama). v0 (database baru, skema sudah v2) tidak perlu apa-apa.
    """
    if from_version == 0:
        return
    if from_version != 1:
        raise ValueError(f"tidak ada jalur migrasi dari versi skema {from_version}")
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with conn:
            conn.execute(
                "CREATE TABLE stock_movements_new ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " product_id INTEGER NOT NULL REFERENCES products (id),"
                " outlet_id INTEGER NOT NULL REFERENCES outlets (id),"
                " qty REAL NOT NULL,"
                " kind TEXT NOT NULL CHECK (kind IN ('sale', 'purchase', 'adjustment',"
                " 'return', 'transfer', 'opening_balance', 'adjustment_in',"
                " 'adjustment_out')),"
                " ref_type TEXT NOT NULL DEFAULT '',"
                " ref_id INTEGER,"
                " note TEXT NOT NULL DEFAULT '',"
                " user_id INTEGER REFERENCES users (id) ON DELETE SET NULL,"
                " effective_date TEXT,"
                " created_at TEXT NOT NULL DEFAULT (datetime('now')))"
            )
            conn.execute(
                "INSERT INTO stock_movements_new"
                " (id, product_id, outlet_id, qty, kind, ref_type, ref_id,"
                "  note, user_id, effective_date, created_at)"
                " SELECT id, product_id, outlet_id, qty,"
                "  CASE"
                "   WHEN kind = 'adjustment' AND note LIKE 'Saldo awal%'"
                "     THEN 'opening_balance'"
                "   WHEN kind = 'adjustment' AND qty > 0 THEN 'adjustment_in'"
                "   WHEN kind = 'adjustment' AND qty < 0 THEN 'adjustment_out'"
                "   ELSE kind END,"
                "  ref_type, ref_id, note, user_id, NULL, created_at"
                " FROM stock_movements"
            )
            conn.execute("DROP TABLE stock_movements")
            conn.execute("ALTER TABLE stock_movements_new RENAME TO stock_movements")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_stock_movements_product"
                " ON stock_movements (product_id, created_at)"
            )
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def init_tenant_db(slug, data_dir=None):
    """Buat database tenant bila belum ada dan terapkan skema terbaru.

    Idempotent: aman dijalankan berulang kali (CREATE TABLE IF NOT
    EXISTS + PRAGMA user_version). Database lama dimigrasi otomatis
    ke versi skema saat ini (lihat migrate_tenant_db). Mengembalikan
    koneksi yang sudah terbuka; pemanggil menutupnya.
    """
    conn = get_tenant_db(slug, data_dir=data_dir)
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    version = get_schema_version(conn)
    if version < SCHEMA_VERSION:
        migrate_tenant_db(conn, version)
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


def get_or_create_category(conn, name):
    """Kembalikan id kategori; buat baru bila nama belum ada. Nama kosong -> None."""
    name = (name or "").strip()
    if not name:
        return None
    row = conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


def get_or_create_unit(conn, name):
    """Kembalikan id satuan; buat baru bila nama belum ada. Nama kosong -> None."""
    name = (name or "").strip()
    if not name:
        return None
    row = conn.execute("SELECT id FROM units WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO units (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


def create_product(conn, sku, name, category_id=None, unit_id=None, barcode=None,
                   buy_price=0, sell_price=0, min_stock=0):
    """Buat produk baru. SKU unik; harga dan stok minimum tidak boleh negatif."""
    sku = (sku or "").strip()
    name = (name or "").strip()
    if not sku:
        raise ValueError("SKU wajib diisi")
    if not name:
        raise ValueError("nama produk wajib diisi")
    if buy_price < 0 or sell_price < 0:
        raise ValueError("harga tidak boleh negatif")
    if min_stock < 0:
        raise ValueError("stok minimum tidak boleh negatif")
    barcode = (barcode or "").strip() or None
    cur = conn.execute(
        "INSERT INTO products (sku, barcode, name, category_id, unit_id,"
        " buy_price, sell_price, min_stock)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (sku, barcode, name, category_id, unit_id, buy_price, sell_price, min_stock),
    )
    conn.commit()
    return cur.lastrowid


def get_product(conn, product_id):
    return conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()


def update_product(conn, product_id, sku, name, category_id=None, unit_id=None,
                   barcode=None, buy_price=0, sell_price=0, min_stock=0):
    """Ubah produk. Validasi sama seperti create_product.

    Satuan dasar tidak boleh diubah bila produk sudah memiliki stok
    atau riwayat mutasi — tidak ada aturan konversi yang teruji,
    dan mengubah satuan diam-diam akan merusak arti saldo lama.
    """
    sku = (sku or "").strip()
    name = (name or "").strip()
    if not sku:
        raise ValueError("SKU wajib diisi")
    if not name:
        raise ValueError("nama produk wajib diisi")
    if buy_price < 0 or sell_price < 0:
        raise ValueError("harga tidak boleh negatif")
    if min_stock < 0:
        raise ValueError("stok minimum tidak boleh negatif")
    current = get_product(conn, product_id)
    if current is not None and unit_id != current["unit_id"]:
        has_stock = conn.execute(
            "SELECT COALESCE(SUM(qty), 0) AS n FROM stock WHERE product_id = ?",
            (product_id,),
        ).fetchone()["n"]
        has_movements = conn.execute(
            "SELECT 1 FROM stock_movements WHERE product_id = ? LIMIT 1",
            (product_id,),
        ).fetchone()
        if has_stock or has_movements:
            raise ValueError(
                "Satuan dasar tidak dapat diubah karena produk sudah"
                " memiliki stok atau riwayat mutasi."
            )
    barcode = (barcode or "").strip() or None
    cur = conn.execute(
        "UPDATE products SET sku = ?, barcode = ?, name = ?, category_id = ?,"
        " unit_id = ?, buy_price = ?, sell_price = ?, min_stock = ?,"
        " updated_at = datetime('now') WHERE id = ?",
        (sku, barcode, name, category_id, unit_id, buy_price, sell_price,
         min_stock, product_id),
    )
    conn.commit()
    return cur.rowcount


def set_product_active(conn, product_id, is_active):
    """Arsipkan (is_active=0) atau aktifkan kembali produk. Bukan hapus:
    produk yang sudah dipakai transaksi harus tetap ada untuk histori."""
    cur = conn.execute(
        "UPDATE products SET is_active = ?, updated_at = datetime('now')"
        " WHERE id = ?",
        (1 if is_active else 0, product_id),
    )
    conn.commit()
    return cur.rowcount


def list_categories(conn):
    return conn.execute("SELECT * FROM categories ORDER BY name").fetchall()


def list_products(conn, q=None, category_id=None, include_inactive=False, limit=500):
    """Daftar produk + total stok semua outlet. Cari berdasarkan SKU/nama,
    saring berdasarkan kategori bila diisi."""
    sql = (
        "SELECT p.*, c.name AS category, u.name AS unit,"
        " COALESCE(SUM(s.qty), 0) AS stock_qty"
        " FROM products p"
        " LEFT JOIN categories c ON c.id = p.category_id"
        " LEFT JOIN units u ON u.id = p.unit_id"
        " LEFT JOIN stock s ON s.product_id = p.id"
    )
    args = []
    where = []
    if not include_inactive:
        where.append("p.is_active = 1")
    if q:
        where.append("(p.sku LIKE ? OR p.name LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    if category_id:
        where.append("p.category_id = ?")
        args.append(category_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY p.id ORDER BY p.name LIMIT ?"
    args.append(limit)
    return conn.execute(sql, args).fetchall()


def list_outlets(conn):
    return conn.execute(
        "SELECT * FROM outlets WHERE is_active = 1 ORDER BY name"
    ).fetchall()


def get_default_outlet(conn):
    """Outlet pertama yang aktif; bila belum ada outlet sama sekali, buat
    outlet default 'Outlet Utama'. Dipakai penyesuaian stok agar tenant
    baru tidak terhalang urusan outlet sebelum ada manajemen outlet."""
    row = conn.execute(
        "SELECT * FROM outlets WHERE is_active = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    if row:
        return row
    cur = conn.execute(
        "INSERT INTO outlets (name, slug) VALUES ('Outlet Utama', 'outlet-utama')"
    )
    conn.commit()
    return conn.execute("SELECT * FROM outlets WHERE id = ?", (cur.lastrowid,)).fetchone()


def get_stock_qty(conn, product_id, outlet_id):
    row = conn.execute(
        "SELECT qty FROM stock WHERE product_id = ? AND outlet_id = ?",
        (product_id, outlet_id),
    ).fetchone()
    return row["qty"] if row else 0


def adjust_stock(conn, product_id, outlet_id, qty_delta, note="", user_id=None,
                 kind="adjustment", effective_date=None):
    """Penyesuaian stok atomik: ubah tabel stock DAN tulis stock_movements
    dalam satu transaksi. Stok hasil tidak boleh negatif. qty_delta != 0.
    Mengembalikan stok akhir. Melempar ValueError bila tidak valid."""
    if not qty_delta:
        raise ValueError("jumlah penyesuaian tidak boleh nol")
    if kind not in STOCK_MOVEMENT_KINDS:
        raise ValueError(f"jenis mutasi tidak valid: {kind!r}")
    if get_product(conn, product_id) is None:
        raise ValueError("produk tidak ditemukan")
    with conn:  # satu transaksi: gagal di tengah -> semua dibatalkan
        current = get_stock_qty(conn, product_id, outlet_id)
        new_qty = current + qty_delta
        if new_qty < 0:
            raise ValueError(
                f"stok tidak boleh negatif (saat ini {current:g}, perubahan {qty_delta:g})"
            )
        conn.execute(
            "INSERT INTO stock (product_id, outlet_id, qty) VALUES (?, ?, ?)"
            " ON CONFLICT (product_id, outlet_id) DO UPDATE"
            " SET qty = excluded.qty, updated_at = datetime('now')",
            (product_id, outlet_id, new_qty),
        )
        conn.execute(
            "INSERT INTO stock_movements"
            " (product_id, outlet_id, qty, kind, ref_type, note, user_id,"
            "  effective_date)"
            " VALUES (?, ?, ?, ?, '', ?, ?, ?)",
            (product_id, outlet_id, qty_delta, kind, note or "", user_id,
             effective_date),
        )
    return new_qty


def record_opening_balance(conn, product_id, outlet_id, qty, note="",
                           user_id=None, effective_date=None):
    """Catat saldo awal sebagai mutasi 'opening_balance'.

    Aturan: qty harus > 0 (saldo awal nol tidak perlu dicatat — produk
    baru memang tidak otomatis memiliki stok; kembalikan stok saat ini
    tanpa menulis mutasi). Saldo awal hanya boleh dicatat sekali per
    produk×outlet; koreksi berikutnya memakai penyesuaian biasa.
    """
    if qty is None:
        raise ValueError("kuantitas saldo awal wajib diisi")
    if qty < 0:
        raise ValueError("saldo awal tidak boleh negatif")
    if qty == 0:
        return get_stock_qty(conn, product_id, outlet_id)
    existing = conn.execute(
        "SELECT 1 FROM stock_movements"
        " WHERE product_id = ? AND outlet_id = ? AND kind = 'opening_balance'"
        " LIMIT 1",
        (product_id, outlet_id),
    ).fetchone()
    if existing:
        raise ValueError(
            "Saldo awal untuk produk dan outlet ini sudah dicatat;"
            " gunakan penyesuaian stok untuk koreksi."
        )
    return adjust_stock(
        conn, product_id, outlet_id, qty,
        note=note or "Saldo awal", user_id=user_id,
        kind="opening_balance", effective_date=effective_date,
    )


def search_products(conn, q, outlet_id=None, limit=20):
    """Cari produk AKTIF berdasarkan nama, SKU, atau barcode.

    Mengembalikan stok di outlet yang diminta (bila diisi) — itulah
    stok yang bisa dijual kasir. Tanpa outlet_id, kembalikan total
    stok semua outlet. Hanya produk aktif yang dapat dijual.
    """
    q = (q or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    if outlet_id is not None:
        sql = (
            "SELECT p.*, c.name AS category, u.name AS unit,"
            " COALESCE(s.qty, 0) AS stock_qty"
            " FROM products p"
            " LEFT JOIN categories c ON c.id = p.category_id"
            " LEFT JOIN units u ON u.id = p.unit_id"
            " LEFT JOIN stock s ON s.product_id = p.id AND s.outlet_id = ?"
            " WHERE p.is_active = 1"
            " AND (p.name LIKE ? OR p.sku LIKE ? OR p.barcode LIKE ?)"
            " ORDER BY p.name LIMIT ?"
        )
        return conn.execute(sql, (outlet_id, like, like, like, limit)).fetchall()
    sql = (
        "SELECT p.*, c.name AS category, u.name AS unit,"
        " COALESCE(SUM(s.qty), 0) AS stock_qty"
        " FROM products p"
        " LEFT JOIN categories c ON c.id = p.category_id"
        " LEFT JOIN units u ON u.id = p.unit_id"
        " LEFT JOIN stock s ON s.product_id = p.id"
        " WHERE p.is_active = 1"
        " AND (p.name LIKE ? OR p.sku LIKE ? OR p.barcode LIKE ?)"
        " GROUP BY p.id ORDER BY p.name LIMIT ?"
    )
    return conn.execute(sql, (like, like, like, limit)).fetchall()


def summarize_cart(conn, items, outlet_id):
    """Hitung ulang keranjang dari database (sumber kebenaran server).

    ``items`` adalah daftar dict {"product_id": int, "qty": float}.
    Harga selalu diambil dari products.sell_price; stok divalidasi
    terhadap outlet yang dipakai kasir. Mengembalikan
    (lines, total_qty, total_rp, errors) dengan lines berisi
    product, qty, price, subtotal per baris. Baris bermasalah
    (produk hilang/nonaktif, qty tidak valid, stok kurang) masuk ke
    errors dan tidak dihitung ke total.
    """
    lines = []
    errors = []
    total_qty = 0
    total = 0
    for item in items:
        try:
            product_id = int(item.get("product_id"))
            qty = float(item.get("qty"))
        except (TypeError, ValueError):
            errors.append("Item keranjang tidak valid.")
            continue
        product = get_product(conn, product_id)
        if product is None:
            errors.append(f"Produk #{product_id} tidak ditemukan.")
            continue
        if not product["is_active"]:
            errors.append(f"{product['name']} sudah nonaktif.")
            continue
        if qty <= 0:
            errors.append(f"Kuantitas {product['name']} harus lebih dari 0.")
            continue
        available = get_stock_qty(conn, product_id, outlet_id)
        if qty > available:
            errors.append(
                f"Stok {product['name']} tidak cukup"
                f" (tersedia {available:g}, diminta {qty:g})."
            )
            continue
        price = int(product["sell_price"])
        subtotal = int(round(price * qty))
        lines.append({
            "product": product, "qty": qty, "price": price,
            "subtotal": subtotal,
        })
        total_qty += qty
        total += subtotal
    return lines, total_qty, total, errors


def reconcile_stock(conn, product_id, outlet_id):
    """Bandingkan saldo tabel stock dengan jumlah seluruh mutasi ledger
    untuk produk×outlet. Mengembalikan (saldo_stock, jumlah_mutasi,
    konsisten). Dalam sistem ini semua perubahan stok berasal dari
    mutasi, jadi keduanya harus sama."""
    stock_qty = get_stock_qty(conn, product_id, outlet_id)
    total = conn.execute(
        "SELECT COALESCE(SUM(qty), 0) AS n FROM stock_movements"
        " WHERE product_id = ? AND outlet_id = ?",
        (product_id, outlet_id),
    ).fetchone()["n"]
    return stock_qty, total, stock_qty == total


def list_stock_movements(conn, product_id=None, kind=None, date_from=None,
                         date_to=None, limit=100):
    """Riwayat mutasi, terbaru dulu. Saring berdasarkan jenis dan
    rentang tanggal efektif/pencatatan (format YYYY-MM-DD)."""
    sql = (
        "SELECT m.*, o.name AS outlet_name FROM stock_movements m"
        " LEFT JOIN outlets o ON o.id = m.outlet_id"
    )
    args = []
    where = []
    if product_id is not None:
        where.append("m.product_id = ?")
        args.append(product_id)
    if kind:
        where.append("m.kind = ?")
        args.append(kind)
    if date_from:
        where.append("date(m.created_at) >= ?")
        args.append(date_from)
    if date_to:
        where.append("date(m.created_at) <= ?")
        args.append(date_to)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY m.created_at DESC, m.id DESC LIMIT ?"
    args.append(limit)
    return conn.execute(sql, args).fetchall()


def list_tenants(data_dir=None):
    """Daftar slug tenant yang punya direktori di DATA_DIR (nama saja)."""
    base = Path(data_dir or os.environ.get("IRIS_DATA_DIR", "tenants"))
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())
