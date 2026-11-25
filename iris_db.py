"""Akses database SQLite per tenant (tahap 12: skema v6 + retur).

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
import hashlib
import json
import os
import re
import sqlite3
from datetime import date
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

SCHEMA_VERSION = 6
_SCHEMA_PATH = Path(__file__).with_name("iris_schema.sql")

# Jenis mutasi stok yang sah (skema v6). 'adjustment' dipertahankan
# untuk kompatibilitas data lama; form baru memakai opening_balance /
# adjustment_in / adjustment_out. 'sale_void' = mutasi pembalik
# pembatalan penjualan (P1 Tahap 5); 'purchase_void' = mutasi pembalik
# pembatalan pembelian (P1 Tahap 6); 'return' = retur penjualan (stok
# masuk) dan pembatalan retur penjualan (stok keluar, ref_type
# 'return_void'); 'purchase_return' = retur pembelian (stok keluar)
# dan pembatalan retur pembelian (stok masuk, ref_type 'return_void').
STOCK_MOVEMENT_KINDS = (
    "sale", "purchase", "adjustment", "return", "transfer",
    "opening_balance", "adjustment_in", "adjustment_out",
    "sale_void", "purchase_void", "purchase_return",
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


def _migrate_v1_to_v2(conn):
    """v1 -> v2: CHECK constraint SQLite tidak bisa diubah dengan ALTER,
    jadi tabel stock_movements dibuat ulang (buat tabel baru, salin
    data, hapus lama, ganti nama) dalam satu transaksi — gagal di
    tengah berarti tabel lama tetap utuh. Pemetaan jenis lama:
    'adjustment' + catatan diawali 'Saldo awal' -> 'opening_balance',
    'adjustment' positif -> 'adjustment_in', negatif -> 'adjustment_out',
    jenis lain tidak berubah. Kolom effective_date ditambah (NULL untuk
    data lama)."""
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


def _migrate_v2_to_v3(conn):
    """v2 -> v3 (penjualan kasir).

    - sale_items: tambah kolom snapshot product_name/sku/unit (ALTER,
      tanpa memindahkan data).
    - sales: dibuat ulang (CHECK 'pending' + kolom baru tidak bisa
      ditambah dengan constraint lewat ALTER) dalam satu transaksi;
      data lama disalin utuh. idempotency_key UNIQUE dijamin database.
    - sale_payments: tabel baru + index.
    """
    cols = [r[1] for r in conn.execute("PRAGMA table_info(sale_items)")]
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with conn:
            for col, ddl in (
                ("product_name", "ALTER TABLE sale_items ADD COLUMN product_name TEXT NOT NULL DEFAULT ''"),
                ("sku", "ALTER TABLE sale_items ADD COLUMN sku TEXT"),
                ("unit", "ALTER TABLE sale_items ADD COLUMN unit TEXT"),
            ):
                if col not in cols:
                    conn.execute(ddl)
            conn.execute(
                "CREATE TABLE sales_new ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " outlet_id INTEGER NOT NULL REFERENCES outlets (id),"
                " user_id INTEGER REFERENCES users (id) ON DELETE SET NULL,"
                " customer_id INTEGER REFERENCES customers (id) ON DELETE SET NULL,"
                " invoice_no TEXT NOT NULL UNIQUE,"
                " status TEXT NOT NULL DEFAULT 'completed'"
                "  CHECK (status IN ('completed', 'pending', 'void', 'returned')),"
                " subtotal INTEGER NOT NULL DEFAULT 0 CHECK (subtotal >= 0),"
                " discount INTEGER NOT NULL DEFAULT 0 CHECK (discount >= 0),"
                " tax INTEGER NOT NULL DEFAULT 0 CHECK (tax >= 0),"
                " total INTEGER NOT NULL DEFAULT 0 CHECK (total >= 0),"
                " paid INTEGER NOT NULL DEFAULT 0 CHECK (paid >= 0),"
                " change_amount INTEGER NOT NULL DEFAULT 0 CHECK (change_amount >= 0),"
                " payment_method TEXT NOT NULL DEFAULT 'cash',"
                " payment_ref TEXT,"
                " idempotency_key TEXT UNIQUE,"
                " idempotency_payload TEXT,"
                " void_reason TEXT,"
                " voided_by INTEGER REFERENCES users (id) ON DELETE SET NULL,"
                " voided_at TEXT,"
                " created_at TEXT NOT NULL DEFAULT (datetime('now')))"
            )
            conn.execute(
                "INSERT INTO sales_new"
                " (id, outlet_id, user_id, customer_id, invoice_no, status,"
                "  subtotal, discount, tax, total, paid, change_amount,"
                "  payment_method, payment_ref, idempotency_key,"
                "  idempotency_payload, void_reason, voided_by, voided_at,"
                "  created_at)"
                " SELECT id, outlet_id, user_id, customer_id, invoice_no, status,"
                "  subtotal, discount, tax, total, paid, 0,"
                "  payment_method, NULL, NULL,"
                "  NULL, NULL, NULL, NULL,"
                "  created_at FROM sales"
            )
            conn.execute("DROP TABLE sales")
            conn.execute("ALTER TABLE sales_new RENAME TO sales")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS sale_payments ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " sale_id INTEGER NOT NULL REFERENCES sales (id) ON DELETE CASCADE,"
                " payment_method TEXT NOT NULL,"
                " amount INTEGER NOT NULL CHECK (amount >= 0),"
                " reference_number TEXT,"
                " paid_at TEXT NOT NULL DEFAULT (datetime('now')),"
                " created_by INTEGER REFERENCES users (id) ON DELETE SET NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sales_outlet_created"
                " ON sales (outlet_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sales_created ON sales (created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sales_user ON sales (user_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sale_items_product"
                " ON sale_items (product_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sale_payments_sale"
                " ON sale_payments (sale_id)"
            )
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate_v3_to_v4(conn):
    """v3 -> v4: tambah jenis mutasi 'sale_void' (pembatalan penjualan).

    CHECK SQLite tidak bisa diubah dengan ALTER, jadi tabel
    stock_movements dibuat ulang seperti migrasi v1->v2: data disalin
    apa adanya (tidak ada pemetaan jenis), dalam satu transaksi.
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with conn:
            conn.execute(
                "CREATE TABLE stock_movements_new ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " product_id INTEGER NOT NULL REFERENCES products (id),"
                " outlet_id INTEGER NOT NULL REFERENCES outlets (id),"
                " qty REAL NOT NULL,"
                " kind TEXT NOT NULL CHECK (kind IN ('sale', 'purchase',"
                " 'adjustment', 'return', 'transfer', 'opening_balance',"
                " 'adjustment_in', 'adjustment_out', 'sale_void')),"
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
                " SELECT id, product_id, outlet_id, qty, kind, ref_type,"
                "  ref_id, note, user_id, effective_date, created_at"
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


def migrate_tenant_db(conn, from_version):
    """Migrasikan database tenant ke SCHEMA_VERSION, bertahap per versi.

    v0 (database baru, skema sudah terbaru) tidak perlu apa-apa.
    Versi yang tidak dikenal tidak dimigrasi dan tidak ditandai —
    pemanggil (init_tenant_db) hanya menaikkan versi bila migrasi
    berhasil.
    """
    if from_version == 0:
        return
    if from_version == 1:
        _migrate_v1_to_v2(conn)
        from_version = 2
    if from_version == 2:
        _migrate_v2_to_v3(conn)
        from_version = 3
    if from_version == 3:
        _migrate_v3_to_v4(conn)
        from_version = 4
    if from_version == 4:
        _migrate_v4_to_v5(conn)
        from_version = 5
    if from_version == 5:
        _migrate_v5_to_v6(conn)
        return
    raise ValueError(f"tidak ada jalur migrasi dari versi skema {from_version}")


def _migrate_v5_to_v6(conn):
    """v5 -> v6 (retur penjualan & pembelian).

    - Tabel baru returns + return_items (CREATE TABLE IF NOT EXISTS
      dari skema v6 — di sini dieksekusi langsung agar migrasi eksplisit).
    - stock_movements dibuat ulang untuk menambah jenis 'purchase_return'
      di CHECK (data disalin apa adanya, tanpa pemetaan jenis).
    - Index baru returns/return_items.
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS returns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK (kind IN ('sale_return', 'purchase_return')),
                    sale_id INTEGER REFERENCES sales (id) ON DELETE SET NULL,
                    purchase_id INTEGER REFERENCES purchases (id) ON DELETE SET NULL,
                    outlet_id INTEGER NOT NULL REFERENCES outlets (id),
                    user_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
                    return_no TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'completed'
                        CHECK (status IN ('completed', 'cancelled')),
                    total INTEGER NOT NULL DEFAULT 0 CHECK (total >= 0),
                    reason TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    idempotency_key TEXT UNIQUE,
                    idempotency_payload TEXT,
                    cancel_reason TEXT,
                    cancelled_by INTEGER REFERENCES users (id) ON DELETE SET NULL,
                    cancelled_at TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS return_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    return_id INTEGER NOT NULL REFERENCES returns (id) ON DELETE CASCADE,
                    product_id INTEGER NOT NULL REFERENCES products (id),
                    product_name TEXT NOT NULL DEFAULT '',
                    sku TEXT,
                    unit TEXT,
                    qty REAL NOT NULL CHECK (qty > 0),
                    price INTEGER NOT NULL CHECK (price >= 0)
                );
                """
            )
            conn.execute(
                "CREATE TABLE stock_movements_new ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " product_id INTEGER NOT NULL REFERENCES products (id),"
                " outlet_id INTEGER NOT NULL REFERENCES outlets (id),"
                " qty REAL NOT NULL,"
                " kind TEXT NOT NULL CHECK (kind IN ('sale', 'purchase',"
                " 'adjustment', 'return', 'transfer', 'opening_balance',"
                " 'adjustment_in', 'adjustment_out', 'sale_void',"
                " 'purchase_void', 'purchase_return')),"
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
                " SELECT id, product_id, outlet_id, qty, kind, ref_type,"
                "  ref_id, note, user_id, effective_date, created_at"
                " FROM stock_movements"
            )
            conn.execute("DROP TABLE stock_movements")
            conn.execute("ALTER TABLE stock_movements_new RENAME TO stock_movements")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_stock_movements_product"
                " ON stock_movements (product_id, created_at)"
            )
            for ddl in (
                "CREATE INDEX IF NOT EXISTS idx_returns_created"
                " ON returns (created_at)",
                "CREATE INDEX IF NOT EXISTS idx_returns_sale"
                " ON returns (sale_id)",
                "CREATE INDEX IF NOT EXISTS idx_returns_purchase"
                " ON returns (purchase_id)",
                "CREATE INDEX IF NOT EXISTS idx_return_items_return"
                " ON return_items (return_id)",
            ):
                conn.execute(ddl)
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate_v4_to_v5(conn):
    """v4 -> v5 (modul pembelian).

    - suppliers: tambah notes/is_active/updated_at (ALTER).
    - purchases: tambah notes + kolom pembatalan cancel_reason/
      cancelled_by/cancelled_at (ALTER).
    - purchase_items: tambah snapshot product_name/sku/unit (ALTER).
    - stock_movements: dibuat ulang untuk menambah jenis 'purchase_void'
      di CHECK (data disalin apa adanya, tanpa pemetaan jenis).
    - Index baru purchases/purchase_items.
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with conn:
            for table, col, ddl in (
                ("suppliers", "notes",
                 "ALTER TABLE suppliers ADD COLUMN notes TEXT NOT NULL DEFAULT ''"),
                ("suppliers", "is_active",
                 "ALTER TABLE suppliers ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"),
                ("suppliers", "updated_at",
                 "ALTER TABLE suppliers ADD COLUMN updated_at TEXT NOT NULL DEFAULT (datetime('now'))"),
                ("purchases", "notes",
                 "ALTER TABLE purchases ADD COLUMN notes TEXT NOT NULL DEFAULT ''"),
                ("purchases", "cancel_reason",
                 "ALTER TABLE purchases ADD COLUMN cancel_reason TEXT"),
                ("purchases", "cancelled_by",
                 "ALTER TABLE purchases ADD COLUMN cancelled_by INTEGER REFERENCES users (id) ON DELETE SET NULL"),
                ("purchases", "cancelled_at",
                 "ALTER TABLE purchases ADD COLUMN cancelled_at TEXT"),
                ("purchase_items", "product_name",
                 "ALTER TABLE purchase_items ADD COLUMN product_name TEXT NOT NULL DEFAULT ''"),
                ("purchase_items", "sku",
                 "ALTER TABLE purchase_items ADD COLUMN sku TEXT"),
                ("purchase_items", "unit",
                 "ALTER TABLE purchase_items ADD COLUMN unit TEXT"),
            ):
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
                if col not in cols:
                    conn.execute(ddl)
            conn.execute(
                "CREATE TABLE stock_movements_new ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " product_id INTEGER NOT NULL REFERENCES products (id),"
                " outlet_id INTEGER NOT NULL REFERENCES outlets (id),"
                " qty REAL NOT NULL,"
                " kind TEXT NOT NULL CHECK (kind IN ('sale', 'purchase',"
                " 'adjustment', 'return', 'transfer', 'opening_balance',"
                " 'adjustment_in', 'adjustment_out', 'sale_void',"
                " 'purchase_void')),"
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
                " SELECT id, product_id, outlet_id, qty, kind, ref_type,"
                "  ref_id, note, user_id, effective_date, created_at"
                " FROM stock_movements"
            )
            conn.execute("DROP TABLE stock_movements")
            conn.execute("ALTER TABLE stock_movements_new RENAME TO stock_movements")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_stock_movements_product"
                " ON stock_movements (product_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_purchases_created"
                " ON purchases (created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_purchases_supplier"
                " ON purchases (supplier_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_purchase_items_purchase"
                " ON purchase_items (purchase_id)"
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


def _apply_stock_change(conn, product_id, outlet_id, qty_delta, note="",
                        user_id=None, kind="adjustment", effective_date=None,
                        ref_type="", ref_id=None):
    """Inti perubahan stok: ubah tabel stock + tulis stock_movements.

    TIDAK mengelola transaksi sendiri — pemanggil yang membuka dan
    menutup transaksi (adjust_stock memakai ``with conn:``, checkout
    memakai transaksi penjualan yang sama). Stok hasil tidak boleh
    negatif. Mengembalikan stok akhir.
    """
    if not qty_delta:
        raise ValueError("jumlah penyesuaian tidak boleh nol")
    if kind not in STOCK_MOVEMENT_KINDS:
        raise ValueError(f"jenis mutasi tidak valid: {kind!r}")
    if get_product(conn, product_id) is None:
        raise ValueError("produk tidak ditemukan")
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
        " (product_id, outlet_id, qty, kind, ref_type, ref_id, note,"
        "  user_id, effective_date)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (product_id, outlet_id, qty_delta, kind, ref_type, ref_id,
         note or "", user_id, effective_date),
    )
    return new_qty


def adjust_stock(conn, product_id, outlet_id, qty_delta, note="", user_id=None,
                 kind="adjustment", effective_date=None, ref_type="",
                 ref_id=None):
    """Penyesuaian stok atomik: ubah tabel stock DAN tulis stock_movements
    dalam satu transaksi. Stok hasil tidak boleh negatif. qty_delta != 0.
    Mengembalikan stok akhir. Melempar ValueError bila tidak valid."""
    with conn:  # satu transaksi: gagal di tengah -> semua dibatalkan
        return _apply_stock_change(
            conn, product_id, outlet_id, qty_delta, note=note,
            user_id=user_id, kind=kind, effective_date=effective_date,
            ref_type=ref_type, ref_id=ref_id,
        )


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
        unit_row = None
        if product["unit_id"]:
            unit_row = conn.execute(
                "SELECT name FROM units WHERE id = ?", (product["unit_id"],)
            ).fetchone()
        lines.append({
            "product": product, "qty": qty, "price": price,
            "subtotal": subtotal,
            "unit": unit_row["name"] if unit_row else None,
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


# ----------------------------------------------------------------------
# Penjualan kasir (P1 Tahap 3)
# ----------------------------------------------------------------------
PAYMENT_METHODS = ("cash", "transfer", "qris", "debit")
# Non-tunai dicatat manual oleh kasir — BUKAN terverifikasi gateway.
NON_CASH_METHODS = ("transfer", "qris", "debit")
MAX_CART_ITEMS = 100


def _idempotency_payload_hash(items, payment_method, amount_tendered,
                              payment_ref):
    canonical = json.dumps(
        {
            "items": sorted(
                (int(i["product_id"]), float(i["qty"])) for i in items
            ),
            "payment_method": payment_method,
            "amount_tendered": amount_tendered,
            "payment_ref": payment_ref or "",
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _generate_invoice_no(conn):
    """Nomor invoice INV-YYYYMMDD-NNNN, urutan harian per tenant.

    Dipanggil di dalam transaksi BEGIN IMMEDIATE (satu penulis dalam
    satu waktu), dan keunikan tetap dijamin UNIQUE constraint database.
    """
    today = date.today().strftime("%Y%m%d")
    prefix = f"INV-{today}-"
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM sales WHERE invoice_no LIKE ?",
        (prefix + "%",),
    ).fetchone()
    return f"{prefix}{row['n'] + 1:04d}"


def create_sale(conn, outlet_id, user_id, items, payment_method,
                amount_tendered=None, payment_ref=None, idempotency_key=None):
    """Simpan penjualan secara atomik (BEGIN IMMEDIATE ... COMMIT).

    Langkah dalam satu transaksi: cek idempotensi, validasi keranjang
    dari database (produk aktif, kuantitas BULAT > 0, stok cukup),
    hitung ulang total, validasi pembayaran, buat invoice, simpan
    sales + sale_items (snapshot) + sale_payments, kurangi stok lewat
    ledger (kind='sale', ref_type='sale', ref_id=sale id).
    Gagal di langkah mana pun -> rollback seluruhnya.

    Aturan pembayaran (P1 dasar, tanpa diskon/pajak):
    - tunai: amount_tendered wajib >= total; kembalian = tendered-total.
    - non-tunai: dicatat manual, status 'pending', paid=0 sampai
      owner/admin mengonfirmasi (confirm_payment); tendered == total.
    Mengembalikan (sale_id, replayed): replayed True bila token
    idempotensi sudah pernah dipakai dengan payload yang sama.
    """
    if not idempotency_key:
        raise ValueError("token idempotensi wajib diisi")
    if payment_method not in PAYMENT_METHODS:
        raise ValueError(f"metode pembayaran tidak dikenal: {payment_method!r}")
    if not items:
        raise ValueError("keranjang kosong")
    if len(items) > MAX_CART_ITEMS:
        raise ValueError("keranjang melebihi batas item")
    # Kuantitas harus bulat positif (keputusan spesifikasi Tahap 3).
    for item in items:
        qty = item.get("qty")
        if qty is None or float(qty) <= 0 or float(qty) != int(float(qty)):
            raise ValueError("kuantitas harus bilangan bulat lebih dari 0")

    payload_hash = _idempotency_payload_hash(
        items, payment_method, amount_tendered, payment_ref)
    wasolation = conn.isolation_level
    conn.isolation_level = None  # kelola transaksi manual
    try:
        for attempt in range(3):
            try:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    existing = conn.execute(
                        "SELECT id, idempotency_payload FROM sales"
                        " WHERE idempotency_key = ?",
                        (idempotency_key,),
                    ).fetchone()
                    if existing is not None:
                        if existing["idempotency_payload"] != payload_hash:
                            raise ValueError(
                                "token idempotensi sudah dipakai untuk"
                                " transaksi yang berbeda")
                        conn.execute("COMMIT")
                        return existing["id"], True
                    lines, _, total, errors = summarize_cart(
                        conn, items, outlet_id)
                    if errors:
                        raise ValueError(errors[0])
                    if amount_tendered is None:
                        amount_tendered = total
                    amount_tendered = int(amount_tendered)
                    if amount_tendered < 0:
                        raise ValueError("nominal pembayaran tidak boleh negatif")
                    if payment_method == "cash":
                        if amount_tendered < total:
                            raise ValueError(
                                "uang diterima kurang dari total"
                                f" (total Rp {total}, diterima"
                                f" Rp {amount_tendered})")
                        change = amount_tendered - total
                        status, paid = "completed", total
                    else:
                        if amount_tendered != total:
                            raise ValueError(
                                "pembayaran non-tunai harus sebesar total")
                        change = 0
                        status, paid = "pending", 0
                    invoice_no = _generate_invoice_no(conn)
                    cur = conn.execute(
                        "INSERT INTO sales"
                        " (outlet_id, user_id, invoice_no, status, subtotal,"
                        "  discount, tax, total, paid, change_amount,"
                        "  payment_method, payment_ref, idempotency_key,"
                        "  idempotency_payload)"
                        " VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?, ?)",
                        (outlet_id, user_id, invoice_no, status, total,
                         total, paid, change, payment_method,
                         (payment_ref or "").strip() or None,
                         idempotency_key, payload_hash),
                    )
                    sale_id = cur.lastrowid
                    for line in lines:
                        p = line["product"]
                        conn.execute(
                            "INSERT INTO sale_items"
                            " (sale_id, product_id, product_name, sku, unit,"
                            "  qty, price, discount)"
                            " VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                            (sale_id, p["id"], p["name"], p["sku"],
                             line["unit"],
                             line["qty"], line["price"]),
                        )
                    conn.execute(
                        "INSERT INTO sale_payments"
                        " (sale_id, payment_method, amount, reference_number,"
                        "  created_by)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (sale_id, payment_method, amount_tendered,
                         (payment_ref or "").strip() or None, user_id),
                    )
                    for line in lines:
                        _apply_stock_change(
                            conn, line["product"]["id"], outlet_id,
                            -line["qty"], note=f"Penjualan {invoice_no}",
                            user_id=user_id, kind="sale",
                            ref_type="sale", ref_id=sale_id,
                        )
                    conn.execute("COMMIT")
                    return sale_id, False
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
            except sqlite3.IntegrityError as exc:
                # Benturan nomor invoice (sangat jarang di bawah
                # BEGIN IMMEDIATE): coba lagi dengan nomor berikutnya.
                if "sales.invoice_no" in str(exc) and attempt < 2:
                    continue
                raise
    finally:
        conn.isolation_level = wasolation


def get_sale(conn, sale_id):
    """Header penjualan + items + pembayaran + kasir (atau None)."""
    sale = conn.execute(
        "SELECT s.*, u.full_name AS cashier_name, u.username AS cashier_username,"
        " o.name AS outlet_name, o.address AS outlet_address,"
        " o.phone AS outlet_phone,"
        " v.full_name AS voided_by_name FROM sales s"
        " LEFT JOIN users u ON u.id = s.user_id"
        " LEFT JOIN outlets o ON o.id = s.outlet_id"
        " LEFT JOIN users v ON v.id = s.voided_by"
        " WHERE s.id = ?",
        (sale_id,),
    ).fetchone()
    if sale is None:
        return None
    items = conn.execute(
        "SELECT * FROM sale_items WHERE sale_id = ? ORDER BY id",
        (sale_id,),
    ).fetchall()
    payments = conn.execute(
        "SELECT * FROM sale_payments WHERE sale_id = ? ORDER BY id",
        (sale_id,),
    ).fetchall()
    return {"sale": sale, "items": items, "payments": payments}


SALE_STATUSES = ("completed", "pending", "void", "returned")


def list_sales(conn, q=None, date_from=None, date_to=None, status=None,
               payment_method=None, order="newest", limit=100):
    """Daftar penjualan. Cari nomor invoice; saring tanggal/status/
    metode bila diisi. Nilai filter yang tidak dikenal diabaikan
    (bukan error) agar URL filter yang salah tidak menampilkan
    apa-apa secara diam-diam atau crash. Urutan: newest/oldest."""
    sql = (
        "SELECT s.*, u.full_name AS cashier_name,"
        " (SELECT COUNT(*) FROM sale_items i WHERE i.sale_id = s.id)"
        "  AS item_count FROM sales s"
        " LEFT JOIN users u ON u.id = s.user_id"
    )
    args, where = [], []
    if q:
        where.append("s.invoice_no LIKE ?")
        args.append(f"%{q}%")
    if date_from:
        where.append("date(s.created_at) >= ?")
        args.append(date_from)
    if date_to:
        where.append("date(s.created_at) <= ?")
        args.append(date_to)
    if status in SALE_STATUSES:
        where.append("s.status = ?")
        args.append(status)
    if payment_method in PAYMENT_METHODS:
        where.append("s.payment_method = ?")
        args.append(payment_method)
    if where:
        sql += " WHERE " + " AND ".join(where)
    if order == "oldest":
        sql += " ORDER BY s.created_at ASC, s.id ASC LIMIT ?"
    else:
        sql += " ORDER BY s.created_at DESC, s.id DESC LIMIT ?"
    args.append(limit)
    return conn.execute(sql, args).fetchall()


def confirm_payment(conn, sale_id, user_id):
    """Konfirmasi pembayaran non-tunai yang masih 'pending'.

    Hanya untuk sale pending: paid menjadi total, status 'completed'.
    Bukan pembayaran baru — tidak mengubah stok/ledger. Melempar
    ValueError bila sale tidak pending.
    """
    sale = conn.execute(
        "SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if sale is None:
        raise ValueError("transaksi tidak ditemukan")
    if sale["status"] != "pending":
        raise ValueError("hanya transaksi pending yang dapat dikonfirmasi")
    with conn:
        conn.execute(
            "UPDATE sales SET status = 'completed', paid = total"
            " WHERE id = ? AND status = 'pending'",
            (sale_id,),
        )
    return True


# ----------------------------------------------------------------------
# Pembatalan penjualan (P1 Tahap 5)
# ----------------------------------------------------------------------

def void_sale(conn, sale_id, user_id, reason):
    """Batalkan penjualan secara atomik (BEGIN IMMEDIATE).

    Transaksi, item, pembayaran, dan mutasi `sale` asli TIDAK dihapus
    atau diubah. Yang terjadi: status -> 'void' + jejak pembatalan
    (alasan, pengguna, waktu), dan satu mutasi pembalik kind='sale_void'
    per item yang mengembalikan stok persis kuantitas yang dijual.

    Kebijakan pembayaran: pembatalan BUKAN pengembalian uang. `paid`
    dan `sale_payments` tetap tercatat apa adanya; tidak ada status
    'refunded' yang dipalsukan. Pengembalian uang (jika ada) adalah
    proses terpisah.

    Hanya sale berstatus 'completed'/'pending' yang dapat dibatalkan.
    Pembatalan kedua ditolak (status sudah 'void' + pemeriksaan mutasi
    pembalik yang sudah ada), jadi stok tidak pernah dikembalikan dua
    kali. Gagal di langkah mana pun -> rollback seluruhnya.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("alasan pembatalan wajib diisi")
    if len(reason) > 500:
        raise ValueError("alasan pembatalan maksimal 500 karakter")
    wasolation = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            sale = conn.execute(
                "SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
            if sale is None:
                raise ValueError("transaksi tidak ditemukan")
            if sale["status"] == "void":
                raise ValueError("transaksi sudah dibatalkan")
            if sale["status"] not in ("completed", "pending"):
                raise ValueError(
                    f"transaksi berstatus {sale['status']!r} tidak dapat"
                    " dibatalkan")
            existing = conn.execute(
                "SELECT 1 FROM stock_movements"
                " WHERE ref_type = 'sale_void' AND ref_id = ? LIMIT 1",
                (sale_id,),
            ).fetchone()
            if existing:
                raise ValueError(
                    "mutasi pembalik untuk transaksi ini sudah ada")
            # Penjualan yang sudah diretur (sebagian/penuh) tidak boleh
            # dibatalkan: stok barang yang diretur sudah kembali, jadi
            # void akan mengembalikan stok dua kali. Batalkan retur
            # terlebih dahulu bila memang perlu.
            ret = conn.execute(
                "SELECT 1 FROM returns WHERE kind = 'sale_return'"
                " AND sale_id = ? AND status = 'completed' LIMIT 1",
                (sale_id,),
            ).fetchone()
            if ret:
                raise ValueError(
                    "penjualan yang sudah diretur tidak dapat dibatalkan;"
                    " batalkan retur terlebih dahulu")
            items = conn.execute(
                "SELECT * FROM sale_items WHERE sale_id = ? ORDER BY id",
                (sale_id,),
            ).fetchall()
            for item in items:
                _apply_stock_change(
                    conn, item["product_id"], sale["outlet_id"],
                    item["qty"],
                    note=f"Pembatalan {sale['invoice_no']}: {reason}",
                    user_id=user_id, kind="sale_void",
                    ref_type="sale_void", ref_id=sale_id,
                )
            cur = conn.execute(
                "UPDATE sales SET status = 'void', void_reason = ?,"
                " voided_by = ?, voided_at = datetime('now')"
                " WHERE id = ? AND status IN ('completed', 'pending')",
                (reason, user_id, sale_id),
            )
            if cur.rowcount != 1:
                raise ValueError("transaksi sudah berubah status")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.isolation_level = wasolation
    return True


# ----------------------------------------------------------------------
# Pemasok & pembelian (P1 Tahap 6)
# ----------------------------------------------------------------------
PURCHASE_STATUSES = ("ordered", "received", "returned", "cancelled")


def list_suppliers(conn, q=None, include_inactive=False):
    sql = "SELECT * FROM suppliers"
    args, where = [], []
    if q:
        where.append("(name LIKE ? OR phone LIKE ? OR address LIKE ?)")
        args += [f"%{q}%"] * 3
    if not include_inactive:
        where.append("is_active = 1")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY name ASC"
    return conn.execute(sql, args).fetchall()


def get_supplier(conn, supplier_id):
    return conn.execute(
        "SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()


def create_supplier(conn, name, phone="", address="", notes=""):
    name = (name or "").strip()
    if not name:
        raise ValueError("nama pemasok wajib diisi")
    if len(name) > 200:
        raise ValueError("nama pemasok maksimal 200 karakter")
    with conn:
        cur = conn.execute(
            "INSERT INTO suppliers (name, phone, address, notes)"
            " VALUES (?, ?, ?, ?)",
            (name, (phone or "").strip(), (address or "").strip(),
             (notes or "").strip()),
        )
    return cur.lastrowid


def update_supplier(conn, supplier_id, name, phone="", address="", notes=""):
    name = (name or "").strip()
    if not name:
        raise ValueError("nama pemasok wajib diisi")
    if len(name) > 200:
        raise ValueError("nama pemasok maksimal 200 karakter")
    with conn:
        cur = conn.execute(
            "UPDATE suppliers SET name = ?, phone = ?, address = ?,"
            " notes = ?, updated_at = datetime('now') WHERE id = ?",
            (name, (phone or "").strip(), (address or "").strip(),
             (notes or "").strip(), supplier_id),
        )
        if cur.rowcount != 1:
            raise ValueError("pemasok tidak ditemukan")
    return True


def set_supplier_active(conn, supplier_id, active):
    with conn:
        cur = conn.execute(
            "UPDATE suppliers SET is_active = ?,"
            " updated_at = datetime('now') WHERE id = ?",
            (1 if active else 0, supplier_id),
        )
        if cur.rowcount != 1:
            raise ValueError("pemasok tidak ditemukan")
    return True


def _generate_purchase_no(conn):
    """Nomor pembelian PO-YYYYMMDD-NNNN, urutan harian per tenant.

    Dipanggil di dalam transaksi BEGIN IMMEDIATE; keunikan dijamin
    UNIQUE constraint database."""
    today = date.today().strftime("%Y%m%d")
    prefix = f"PO-{today}-"
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM purchases WHERE invoice_no LIKE ?",
        (prefix + "%",),
    ).fetchone()
    return f"{prefix}{row['n'] + 1:04d}"


def create_purchase(conn, outlet_id, user_id, items, supplier_id=None,
                    notes=""):
    """Simpan pembelian + penerimaan stok secara atomik (BEGIN IMMEDIATE).

    Transaksi dibuat langsung berstatus 'received': header + detail
    (snapshot nama/SKU/satuan/harga beli) + satu mutasi masuk
    kind='purchase' (ref_type='purchase', ref_id=purchase id) per item.
    Total dihitung ulang dari database (harga beli dari form, kuantitas
    boleh pecahan karena pembelian per berat dimungkinkan). Harga jual
    produk TIDAK diubah. Gagal di langkah mana pun -> rollback.
    """
    if not items:
        raise ValueError("pembelian harus memiliki minimal satu item")
    if len(items) > MAX_CART_ITEMS:
        raise ValueError("pembelian melebihi batas item")
    if supplier_id is not None:
        supplier = get_supplier(conn, supplier_id)
        if supplier is None:
            raise ValueError("pemasok tidak ditemukan")
        if not supplier["is_active"]:
            raise ValueError("pemasok tidak aktif")
    wasolation = conn.isolation_level
    conn.isolation_level = None
    try:
        for attempt in range(3):
            try:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    total = 0
                    lines = []
                    for item in items:
                        product = get_product(conn, item.get("product_id"))
                        if product is None:
                            raise ValueError("produk tidak ditemukan")
                        if not product["is_active"]:
                            raise ValueError(
                                f"produk {product['name']!r} nonaktif")
                        qty = float(item.get("qty", 0))
                        if qty <= 0:
                            raise ValueError(
                                "kuantitas harus lebih dari 0")
                        price = int(item.get("price", 0))
                        if price < 0:
                            raise ValueError(
                                "harga beli tidak boleh negatif")
                        unit_row = None
                        if product["unit_id"]:
                            unit_row = conn.execute(
                                "SELECT name FROM units WHERE id = ?",
                                (product["unit_id"],),
                            ).fetchone()
                        subtotal = int(round(price * qty))
                        total += subtotal
                        lines.append({
                            "product": product, "qty": qty, "price": price,
                            "unit": unit_row["name"] if unit_row else None,
                        })
                    invoice_no = _generate_purchase_no(conn)
                    cur = conn.execute(
                        "INSERT INTO purchases"
                        " (outlet_id, supplier_id, user_id, invoice_no,"
                        "  status, total, notes)"
                        " VALUES (?, ?, ?, ?, 'received', ?, ?)",
                        (outlet_id, supplier_id, user_id, invoice_no,
                         total, (notes or "").strip()),
                    )
                    purchase_id = cur.lastrowid
                    for line in lines:
                        p = line["product"]
                        conn.execute(
                            "INSERT INTO purchase_items"
                            " (purchase_id, product_id, product_name, sku,"
                            "  unit, qty, price)"
                            " VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (purchase_id, p["id"], p["name"], p["sku"],
                             line["unit"], line["qty"], line["price"]),
                        )
                        _apply_stock_change(
                            conn, p["id"], outlet_id, line["qty"],
                            note=f"Pembelian {invoice_no}",
                            user_id=user_id, kind="purchase",
                            ref_type="purchase", ref_id=purchase_id,
                        )
                    conn.execute("COMMIT")
                    return purchase_id
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
            except sqlite3.IntegrityError as exc:
                if "purchases.invoice_no" in str(exc) and attempt < 2:
                    continue
                raise
    finally:
        conn.isolation_level = wasolation


def get_purchase(conn, purchase_id):
    """Header pembelian + items + pemasok + pencatat (atau None)."""
    row = conn.execute(
        "SELECT p.*, s.name AS supplier_name,"
        " u.full_name AS created_by_name,"
        " v.full_name AS cancelled_by_name FROM purchases p"
        " LEFT JOIN suppliers s ON s.id = p.supplier_id"
        " LEFT JOIN users u ON u.id = p.user_id"
        " LEFT JOIN users v ON v.id = p.cancelled_by"
        " WHERE p.id = ?",
        (purchase_id,),
    ).fetchone()
    if row is None:
        return None
    items = conn.execute(
        "SELECT * FROM purchase_items WHERE purchase_id = ? ORDER BY id",
        (purchase_id,),
    ).fetchall()
    return {"purchase": row, "items": items}


def list_purchases(conn, q=None, supplier_id=None, status=None,
                   date_from=None, date_to=None, order="newest",
                   limit=100):
    """Daftar pembelian. Nilai filter yang tidak dikenal diabaikan."""
    sql = (
        "SELECT p.*, s.name AS supplier_name,"
        " (SELECT COUNT(*) FROM purchase_items i WHERE i.purchase_id = p.id)"
        "  AS item_count FROM purchases p"
        " LEFT JOIN suppliers s ON s.id = p.supplier_id"
    )
    args, where = [], []
    if q:
        where.append("p.invoice_no LIKE ?")
        args.append(f"%{q}%")
    if supplier_id:
        where.append("p.supplier_id = ?")
        args.append(supplier_id)
    if status in PURCHASE_STATUSES:
        where.append("p.status = ?")
        args.append(status)
    if date_from:
        where.append("date(p.created_at) >= ?")
        args.append(date_from)
    if date_to:
        where.append("date(p.created_at) <= ?")
        args.append(date_to)
    if where:
        sql += " WHERE " + " AND ".join(where)
    if order == "oldest":
        sql += " ORDER BY p.created_at ASC, p.id ASC LIMIT ?"
    else:
        sql += " ORDER BY p.created_at DESC, p.id DESC LIMIT ?"
    args.append(limit)
    return conn.execute(sql, args).fetchall()


def cancel_purchase(conn, purchase_id, user_id, reason):
    """Batalkan pembelian yang sudah diterima, secara atomik.

    Hanya pembelian berstatus 'received'. Stok dikembalikan lewat satu
    mutasi kind='purchase_void' per item — tetapi DITOLAK bila stok
    saat ini tidak mencukupi (mis. sebagian barang sudah terjual),
    karena pembatalan tidak boleh membuat stok negatif. Pembatalan
    ganda dicegah (cek status + mutasi pembalik yang sudah ada).
    Transaksi, item, dan mutasi 'purchase' asli tidak dihapus/diubah.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("alasan pembatalan wajib diisi")
    if len(reason) > 500:
        raise ValueError("alasan pembatalan maksimal 500 karakter")
    wasolation = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT * FROM purchases WHERE id = ?", (purchase_id,)
            ).fetchone()
            if row is None:
                raise ValueError("pembelian tidak ditemukan")
            if row["status"] == "cancelled":
                raise ValueError("pembelian sudah dibatalkan")
            if row["status"] != "received":
                raise ValueError(
                    f"pembelian berstatus {row['status']!r} tidak dapat"
                    " dibatalkan")
            existing = conn.execute(
                "SELECT 1 FROM stock_movements"
                " WHERE ref_type = 'purchase_void' AND ref_id = ? LIMIT 1",
                (purchase_id,),
            ).fetchone()
            if existing:
                raise ValueError(
                    "mutasi pembalik untuk pembelian ini sudah ada")
            # Pembelian yang sudah diretur tidak boleh dibatalkan
            # (alasan sama seperti void_sale: stok bisa kembali dua kali).
            ret = conn.execute(
                "SELECT 1 FROM returns WHERE kind = 'purchase_return'"
                " AND purchase_id = ? AND status = 'completed' LIMIT 1",
                (purchase_id,),
            ).fetchone()
            if ret:
                raise ValueError(
                    "pembelian yang sudah diretur tidak dapat dibatalkan;"
                    " batalkan retur terlebih dahulu")
            items = conn.execute(
                "SELECT * FROM purchase_items WHERE purchase_id = ?"
                " ORDER BY id",
                (purchase_id,),
            ).fetchall()
            for item in items:
                current = get_stock_qty(conn, item["product_id"],
                                        row["outlet_id"])
                if current < item["qty"]:
                    raise ValueError(
                        f"stok tidak mencukupi untuk membatalkan"
                        f" (produk {item['product_name']!r}: stok"
                        f" {current:g}, perlu {item['qty']:g})")
            for item in items:
                _apply_stock_change(
                    conn, item["product_id"], row["outlet_id"],
                    -item["qty"],
                    note=f"Pembatalan {row['invoice_no']}: {reason}",
                    user_id=user_id, kind="purchase_void",
                    ref_type="purchase_void", ref_id=purchase_id,
                )
            cur = conn.execute(
                "UPDATE purchases SET status = 'cancelled',"
                " cancel_reason = ?, cancelled_by = ?,"
                " cancelled_at = datetime('now')"
                " WHERE id = ? AND status = 'received'",
                (reason, user_id, purchase_id),
            )
            if cur.rowcount != 1:
                raise ValueError("pembelian sudah berubah status")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.isolation_level = wasolation
    return True


# ----------------------------------------------------------------------
# Retur penjualan & pembelian (P1 Tahap 7)
# ----------------------------------------------------------------------
RETURN_KINDS = ("sale_return", "purchase_return")
RETURN_STATUSES = ("completed", "cancelled")


def _generate_return_no(conn, kind):
    prefix = "RS-" if kind == "sale_return" else "RP-"
    today = date.today().strftime("%Y%m%d")
    prefix = f"{prefix}{today}-"
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM returns WHERE return_no LIKE ?",
        (prefix + "%",),
    ).fetchone()
    return f"{prefix}{row['n'] + 1:04d}"


def _returned_qty(conn, kind, origin_id, product_id):
    """Total kuantitas yang sudah diretur (retur 'completed' saja)
    untuk satu produk pada satu transaksi asal."""
    col = "sale_id" if kind == "sale_return" else "purchase_id"
    row = conn.execute(
        "SELECT COALESCE(SUM(i.qty), 0) AS n FROM return_items i"
        " JOIN returns r ON r.id = i.return_id"
        f" WHERE r.kind = ? AND r.{col} = ? AND r.status = 'completed'"
        " AND i.product_id = ?",
        (kind, origin_id, product_id),
    ).fetchone()
    return row["n"]


def _create_return(conn, kind, origin, user_id, items, reason, notes,
                   idempotency_key=None, idempotency_payload=None):
    """Inti pembuatan retur (dipanggil dari create_sale_return /
    create_purchase_return). Atomik di bawah BEGIN IMMEDIATE.

    - origin: dict transaksi asal + items-nya (dari get_sale/get_purchase).
    - items: [{"product_id", "qty"}] — harga diambil dari detail asal.
    - Retur penjualan: stok masuk kind='return'.
      Retur pembelian: stok keluar kind='purchase_return' (stok dicek).
    - Transaksi asal yang diretur PENUH menjadi status 'returned'.
    - Idempotensi: token + hash payload; replay mengembalikan retur
      yang sama; token sama + payload beda ditolak.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("alasan retur wajib diisi")
    if len(reason) > 500:
        raise ValueError("alasan retur maksimal 500 karakter")
    if not items:
        raise ValueError("retur harus memiliki minimal satu item")
    if len(items) > MAX_CART_ITEMS:
        raise ValueError("retur melebihi batas item")
    wasolation = conn.isolation_level
    conn.isolation_level = None
    try:
        for attempt in range(3):
            try:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    if idempotency_key:
                        existing = conn.execute(
                            "SELECT id, idempotency_payload FROM returns"
                            " WHERE idempotency_key = ?",
                            (idempotency_key,),
                        ).fetchone()
                        if existing is not None:
                            payload_hash = hashlib.sha256(
                                (idempotency_payload or "").encode()
                            ).hexdigest()
                            if existing["idempotency_payload"] != payload_hash:
                                raise ValueError(
                                    "token idempotensi sudah dipakai"
                                    " untuk data berbeda")
                            conn.execute("COMMIT")
                            return existing["id"]
                    origin_row = origin["sale" if kind == "sale_return" else "purchase"]
                    origin_items = {i["product_id"]: i for i in origin["items"]}
                    total = 0
                    lines = []
                    for item in items:
                        pid = item.get("product_id")
                        src = origin_items.get(pid)
                        if src is None:
                            raise ValueError(
                                "produk tidak ada pada transaksi asal")
                        qty = float(item.get("qty", 0))
                        if qty <= 0:
                            raise ValueError(
                                "kuantitas retur harus lebih dari 0")
                        already = _returned_qty(
                            conn, kind, origin_row["id"], pid)
                        if already + qty > src["qty"]:
                            raise ValueError(
                                f"kuantitas retur melebihi sisa"
                                f" ({src['product_name']!r}: terjual/diterima"
                                f" {src['qty']:g}, sudah diretur"
                                f" {already:g})")
                        price = src["price"]
                        if kind == "sale_return":
                            price = src["price"] - (src["discount"] or 0)
                        subtotal = int(round(price * qty))
                        total += subtotal
                        lines.append({
                            "src": src, "qty": qty, "price": price,
                        })
                    if kind == "purchase_return":
                        for line in lines:
                            current = get_stock_qty(
                                conn, line["src"]["product_id"],
                                origin_row["outlet_id"])
                            if current < line["qty"]:
                                raise ValueError(
                                    f"stok tidak mencukupi untuk retur"
                                    f" (produk"
                                    f" {line['src']['product_name']!r}: stok"
                                    f" {current:g}, perlu {line['qty']:g})")
                    return_no = _generate_return_no(conn, kind)
                    payload_hash = None
                    if idempotency_key:
                        payload_hash = hashlib.sha256(
                            (idempotency_payload or "").encode()
                        ).hexdigest()
                    col = "sale_id" if kind == "sale_return" else "purchase_id"
                    cur = conn.execute(
                        "INSERT INTO returns"
                        f" (kind, {col}, outlet_id, user_id, return_no,"
                        "  status, total, reason, notes, idempotency_key,"
                        "  idempotency_payload)"
                        " VALUES (?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?)",
                        (kind, origin_row["id"], origin_row["outlet_id"],
                         user_id, return_no, total, reason,
                         (notes or "").strip(), idempotency_key, payload_hash),
                    )
                    return_id = cur.lastrowid
                    stock_kind = "return" if kind == "sale_return" else "purchase_return"
                    stock_delta = 1 if kind == "sale_return" else -1
                    for line in lines:
                        src = line["src"]
                        conn.execute(
                            "INSERT INTO return_items"
                            " (return_id, product_id, product_name, sku,"
                            "  unit, qty, price)"
                            " VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (return_id, src["product_id"],
                             src["product_name"], src["sku"], src["unit"],
                             line["qty"], line["price"]),
                        )
                        _apply_stock_change(
                            conn, src["product_id"],
                            origin_row["outlet_id"],
                            stock_delta * line["qty"],
                            note=f"Retur {return_no} dari"
                                 f" {origin_row['invoice_no']}",
                            user_id=user_id, kind=stock_kind,
                            ref_type="return", ref_id=return_id,
                        )
                    # Transaksi asal menjadi 'returned' bila semua item
                    # sudah diretur penuh.
                    fully = all(
                        _returned_qty(conn, kind, origin_row["id"], i["product_id"])
                        >= i["qty"] for i in origin["items"]
                    )
                    if fully:
                        table = "sales" if kind == "sale_return" else "purchases"
                        conn.execute(
                            f"UPDATE {table} SET status = 'returned'"
                            " WHERE id = ?",
                            (origin_row["id"],),
                        )
                    conn.execute("COMMIT")
                    return return_id
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
            except sqlite3.IntegrityError as exc:
                if "returns.return_no" in str(exc) and attempt < 2:
                    continue
                raise
    finally:
        conn.isolation_level = wasolation


def create_sale_return(conn, sale_id, user_id, items, reason, notes="",
                       idempotency_key=None, idempotency_payload=None):
    """Retur penjualan: barang kembali, stok bertambah.

    Hanya penjualan berstatus 'completed'/'pending'. Penjualan yang
    sudah dibatalkan ('void') ditolak. Harga dari snapshot sale_items.
    """
    data = get_sale(conn, sale_id)
    if data is None:
        raise ValueError("penjualan tidak ditemukan")
    if data["sale"]["status"] == "void":
        raise ValueError("penjualan yang sudah dibatalkan tidak dapat diretur")
    if data["sale"]["status"] not in ("completed", "pending"):
        raise ValueError(
            f"penjualan berstatus {data['sale']['status']!r} tidak dapat diretur")
    return _create_return(conn, "sale_return", data, user_id, items,
                          reason, notes, idempotency_key,
                          idempotency_payload)


def create_purchase_return(conn, purchase_id, user_id, items, reason,
                           notes="", idempotency_key=None,
                           idempotency_payload=None):
    """Retur pembelian: barang kembali ke pemasok, stok berkurang.

    Hanya pembelian berstatus 'received'. Harga beli dari snapshot
    purchase_items. Stok harus mencukupi.
    """
    data = get_purchase(conn, purchase_id)
    if data is None:
        raise ValueError("pembelian tidak ditemukan")
    if data["purchase"]["status"] != "received":
        raise ValueError(
            f"pembelian berstatus {data['purchase']['status']!r} tidak dapat diretur")
    return _create_return(conn, "purchase_return", data, user_id, items,
                          reason, notes, idempotency_key,
                          idempotency_payload)


def get_return(conn, return_id):
    row = conn.execute(
        "SELECT r.*, u.full_name AS created_by_name,"
        " v.full_name AS cancelled_by_name,"
        " s.invoice_no AS sale_invoice, p.invoice_no AS purchase_invoice,"
        " p.supplier_id FROM returns r"
        " LEFT JOIN users u ON u.id = r.user_id"
        " LEFT JOIN users v ON v.id = r.cancelled_by"
        " LEFT JOIN sales s ON s.id = r.sale_id"
        " LEFT JOIN purchases p ON p.id = r.purchase_id"
        " WHERE r.id = ?",
        (return_id,),
    ).fetchone()
    if row is None:
        return None
    items = conn.execute(
        "SELECT * FROM return_items WHERE return_id = ? ORDER BY id",
        (return_id,),
    ).fetchall()
    supplier_name = None
    if row["supplier_id"]:
        sup = get_supplier(conn, row["supplier_id"])
        supplier_name = sup["name"] if sup else None
    return {"return": row, "items": items, "supplier_name": supplier_name}


def list_returns(conn, q=None, kind=None, status=None, date_from=None,
                 date_to=None, order="newest", limit=100):
    sql = (
        "SELECT r.*, s.invoice_no AS sale_invoice,"
        " p.invoice_no AS purchase_invoice FROM returns r"
        " LEFT JOIN sales s ON s.id = r.sale_id"
        " LEFT JOIN purchases p ON p.id = r.purchase_id"
    )
    args, where = [], []
    if q:
        where.append("r.return_no LIKE ?")
        args.append(f"%{q}%")
    if kind in RETURN_KINDS:
        where.append("r.kind = ?")
        args.append(kind)
    if status in RETURN_STATUSES:
        where.append("r.status = ?")
        args.append(status)
    if date_from:
        where.append("date(r.created_at) >= ?")
        args.append(date_from)
    if date_to:
        where.append("date(r.created_at) <= ?")
        args.append(date_to)
    if where:
        sql += " WHERE " + " AND ".join(where)
    if order == "oldest":
        sql += " ORDER BY r.created_at ASC, r.id ASC LIMIT ?"
    else:
        sql += " ORDER BY r.created_at DESC, r.id DESC LIMIT ?"
    args.append(limit)
    return conn.execute(sql, args).fetchall()


def list_returns_for_origin(conn, kind, origin_id):
    col = "sale_id" if kind == "sale_return" else "purchase_id"
    return conn.execute(
        f"SELECT * FROM returns WHERE kind = ? AND {col} = ?"
        " ORDER BY created_at DESC, id DESC",
        (kind, origin_id),
    ).fetchall()


def cancel_return(conn, return_id, user_id, reason):
    """Batalkan retur yang sudah diproses, secara atomik.

    Mutasi kompensasi dengan ref_type='return_void': retur penjualan
    (dulu menambah stok) dibalik dengan mutasi keluar; retur pembelian
    (dulu mengurangi stok) dibalik dengan mutasi masuk. Pembatalan
    retur penjualan ditolak bila stok tidak mencukupi. Transaksi asal
    yang tadinya 'returned' kembali ke status sebelumnya ('completed'
    untuk penjualan, 'received' untuk pembelian) bila retur ini
    dibatalkan. Retur, item, dan mutasi retur asli tidak dihapus.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("alasan pembatalan wajib diisi")
    if len(reason) > 500:
        raise ValueError("alasan pembatalan maksimal 500 karakter")
    wasolation = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT * FROM returns WHERE id = ?", (return_id,)
            ).fetchone()
            if row is None:
                raise ValueError("retur tidak ditemukan")
            if row["status"] == "cancelled":
                raise ValueError("retur sudah dibatalkan")
            if row["status"] != "completed":
                raise ValueError(
                    f"retur berstatus {row['status']!r} tidak dapat dibatalkan")
            existing = conn.execute(
                "SELECT 1 FROM stock_movements"
                " WHERE ref_type = 'return_void' AND ref_id = ? LIMIT 1",
                (return_id,),
            ).fetchone()
            if existing:
                raise ValueError(
                    "mutasi pembalik untuk retur ini sudah ada")
            items = conn.execute(
                "SELECT * FROM return_items WHERE return_id = ? ORDER BY id",
                (return_id,),
            ).fetchall()
            if row["kind"] == "sale_return":
                stock_kind, delta = "return", -1
                for item in items:
                    current = get_stock_qty(conn, item["product_id"],
                                            row["outlet_id"])
                    if current < item["qty"]:
                        raise ValueError(
                            f"stok tidak mencukupi untuk membatalkan retur"
                            f" (produk {item['product_name']!r}: stok"
                            f" {current:g}, perlu {item['qty']:g})")
            else:
                stock_kind, delta = "purchase_return", 1
            for item in items:
                _apply_stock_change(
                    conn, item["product_id"], row["outlet_id"],
                    delta * item["qty"],
                    note=f"Pembatalan retur {row['return_no']}: {reason}",
                    user_id=user_id, kind=stock_kind,
                    ref_type="return_void", ref_id=return_id,
                )
            cur = conn.execute(
                "UPDATE returns SET status = 'cancelled',"
                " cancel_reason = ?, cancelled_by = ?,"
                " cancelled_at = datetime('now')"
                " WHERE id = ? AND status = 'completed'",
                (reason, user_id, return_id),
            )
            if cur.rowcount != 1:
                raise ValueError("retur sudah berubah status")
            # Kembalikan status transaksi asal bila tadinya 'returned'.
            if row["kind"] == "sale_return" and row["sale_id"]:
                conn.execute(
                    "UPDATE sales SET status = 'completed'"
                    " WHERE id = ? AND status = 'returned'",
                    (row["sale_id"],),
                )
            elif row["kind"] == "purchase_return" and row["purchase_id"]:
                conn.execute(
                    "UPDATE purchases SET status = 'received'"
                    " WHERE id = ? AND status = 'returned'",
                    (row["purchase_id"],),
                )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.isolation_level = wasolation
    return True
