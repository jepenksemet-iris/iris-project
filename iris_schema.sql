-- POS IRIS — skema database tenant, versi 1
-- Berlaku per tenant: satu file iris.db di tenants/<slug>/iris.db
-- Dibuat/idempotent oleh iris_db.init_tenant_db() (CREATE TABLE IF NOT EXISTS).
-- Versi skema dicatat di PRAGMA user_version = 1.
-- Semua uang disimpan sebagai INTEGER (satuan rupiah terkecil) agar
-- tidak ada kesalahan pembulatan float. Jumlah/stok memakai REAL
-- hanya untuk barang yang dijual per berat/volume; stok dihitung
-- utuh lewat tabel stock (bukan kolom yang bisa diubah sembarangan).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'cashier'
        CHECK (role IN ('owner', 'admin', 'cashier')),
    outlet_id INTEGER REFERENCES outlets (id) ON DELETE SET NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS outlets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    address TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE, -- contoh: pcs, kg, liter, dus
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    barcode TEXT UNIQUE,
    name TEXT NOT NULL,
    category_id INTEGER REFERENCES categories (id) ON DELETE SET NULL,
    unit_id INTEGER REFERENCES units (id) ON DELETE SET NULL,
    buy_price INTEGER NOT NULL DEFAULT 0 CHECK (buy_price >= 0),
    sell_price INTEGER NOT NULL DEFAULT 0 CHECK (sell_price >= 0),
    min_stock REAL NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Stok per outlet (satu baris per produk x outlet).
CREATE TABLE IF NOT EXISTS stock (
    product_id INTEGER NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    outlet_id INTEGER NOT NULL REFERENCES outlets (id) ON DELETE CASCADE,
    qty REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (product_id, outlet_id)
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Penjualan: total dihitung dari sale_items (sumber kebenaran),
-- kolom total di sini hanya ringkasan yang sama nilainya.
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    outlet_id INTEGER NOT NULL REFERENCES outlets (id),
    user_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    customer_id INTEGER REFERENCES customers (id) ON DELETE SET NULL,
    invoice_no TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'completed'
        CHECK (status IN ('completed', 'void', 'returned')),
    subtotal INTEGER NOT NULL DEFAULT 0 CHECK (subtotal >= 0),
    discount INTEGER NOT NULL DEFAULT 0 CHECK (discount >= 0),
    tax INTEGER NOT NULL DEFAULT 0 CHECK (tax >= 0),
    total INTEGER NOT NULL DEFAULT 0 CHECK (total >= 0),
    paid INTEGER NOT NULL DEFAULT 0 CHECK (paid >= 0),
    payment_method TEXT NOT NULL DEFAULT 'cash',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sales (id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products (id),
    qty REAL NOT NULL CHECK (qty > 0),
    price INTEGER NOT NULL CHECK (price >= 0), -- harga satuan saat transaksi
    discount INTEGER NOT NULL DEFAULT 0 CHECK (discount >= 0)
);

CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    outlet_id INTEGER NOT NULL REFERENCES outlets (id),
    supplier_id INTEGER REFERENCES suppliers (id) ON DELETE SET NULL,
    user_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    invoice_no TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'received'
        CHECK (status IN ('ordered', 'received', 'returned', 'cancelled')),
    total INTEGER NOT NULL DEFAULT 0 CHECK (total >= 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS purchase_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES purchases (id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products (id),
    qty REAL NOT NULL CHECK (qty > 0),
    price INTEGER NOT NULL CHECK (price >= 0) -- harga beli satuan saat transaksi
);

-- Riwayat perubahan stok (sumber audit): sale, purchase, adjustment,
-- return, transfer. qty bisa negatif untuk pengurangan.
CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products (id),
    outlet_id INTEGER NOT NULL REFERENCES outlets (id),
    qty REAL NOT NULL,
    kind TEXT NOT NULL
        CHECK (kind IN ('sale', 'purchase', 'adjustment', 'return', 'transfer')),
    ref_type TEXT NOT NULL DEFAULT '',
    ref_id INTEGER,
    note TEXT NOT NULL DEFAULT '',
    user_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Pemasukan/pengeluaran kas di luar penjualan & pembelian.
CREATE TABLE IF NOT EXISTS cash_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    outlet_id INTEGER REFERENCES outlets (id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    amount INTEGER NOT NULL CHECK (amount > 0),
    description TEXT NOT NULL DEFAULT '',
    user_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products (category_id);
CREATE INDEX IF NOT EXISTS idx_stock_outlet ON stock (outlet_id);
CREATE INDEX IF NOT EXISTS idx_sales_outlet_created ON sales (outlet_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items (sale_id);
CREATE INDEX IF NOT EXISTS idx_stock_movements_product ON stock_movements (product_id, created_at);
