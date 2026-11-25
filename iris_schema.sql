-- POS IRIS — skema database tenant, versi 3
-- Berlaku per tenant: satu file iris.db di tenants/<slug>/iris.db
-- Dibuat/idempotent oleh iris_db.init_tenant_db() (CREATE TABLE IF NOT EXISTS).
-- Versi skema dicatat di PRAGMA user_version = 3.
-- v2 (2026-11-25): stock_movements.kind ditambah 'opening_balance',
-- 'adjustment_in', 'adjustment_out'; kolom effective_date (tanggal
-- efektif mutasi, mis. saldo awal) ditambah.
-- v3 (2026-11-25): penjualan kasir — snapshot nama/SKU/satuan di
-- sale_items; tabel sale_payments; sales ditambah change_amount,
-- payment_ref, idempotency_key UNIQUE, idempotency_payload,
-- void_reason/voided_by/voided_at, dan status 'pending' (pembayaran
-- non-tunai yang belum terverifikasi). Database lama dimigrasi oleh
-- iris_db.migrate_tenant_db() (lihat iris_db.py).
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
-- status 'pending' = pembayaran non-tunai dicatat kasir tapi belum
-- terverifikasi owner/admin; 'paid' = jumlah yang diterapkan ke
-- penjualan (untuk tunai = total; untuk non-tunai pending = 0 sampai
-- dikonfirmasi). change_amount = uang diterima - total (tunai saja).
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    outlet_id INTEGER NOT NULL REFERENCES outlets (id),
    user_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    customer_id INTEGER REFERENCES customers (id) ON DELETE SET NULL,
    invoice_no TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'completed'
        CHECK (status IN ('completed', 'pending', 'void', 'returned')),
    subtotal INTEGER NOT NULL DEFAULT 0 CHECK (subtotal >= 0),
    discount INTEGER NOT NULL DEFAULT 0 CHECK (discount >= 0),
    tax INTEGER NOT NULL DEFAULT 0 CHECK (tax >= 0),
    total INTEGER NOT NULL DEFAULT 0 CHECK (total >= 0),
    paid INTEGER NOT NULL DEFAULT 0 CHECK (paid >= 0),
    change_amount INTEGER NOT NULL DEFAULT 0 CHECK (change_amount >= 0),
    payment_method TEXT NOT NULL DEFAULT 'cash',
    payment_ref TEXT,
    idempotency_key TEXT UNIQUE,
    idempotency_payload TEXT,
    void_reason TEXT,
    voided_by INTEGER REFERENCES users (id) ON DELETE SET NULL,
    voided_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Snapshot nama/SKU/satuan saat transaksi agar struk lama tetap benar
-- walau master produk diedit. qty REAL mengikuti skema stok (barang
-- per berat/volume); checkout Tahap 3 hanya menerima kuantitas bulat.
CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sales (id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products (id),
    product_name TEXT NOT NULL DEFAULT '',
    sku TEXT,
    unit TEXT,
    qty REAL NOT NULL CHECK (qty > 0),
    price INTEGER NOT NULL CHECK (price >= 0), -- harga satuan saat transaksi
    discount INTEGER NOT NULL DEFAULT 0 CHECK (discount >= 0)
);

-- Satu baris per pembayaran yang dicatat kasir. Non-tunai di sini
-- berarti "dicatat manual oleh kasir", BUKAN terverifikasi gateway.
-- amount = nominal yang diterima/dibayar (untuk tunai bisa lebih dari
-- total; kembaliannya ada di sales.change_amount).
CREATE TABLE IF NOT EXISTS sale_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sales (id) ON DELETE CASCADE,
    payment_method TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK (amount >= 0),
    reference_number TEXT,
    paid_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by INTEGER REFERENCES users (id) ON DELETE SET NULL
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
-- return, transfer, opening_balance, adjustment_in, adjustment_out.
-- qty positif = masuk, negatif = keluar. effective_date = tanggal
-- efektif mutasi (mis. saldo awal); bila kosong, berlaku created_at.
CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products (id),
    outlet_id INTEGER NOT NULL REFERENCES outlets (id),
    qty REAL NOT NULL,
    kind TEXT NOT NULL
        CHECK (kind IN ('sale', 'purchase', 'adjustment', 'return', 'transfer',
                        'opening_balance', 'adjustment_in', 'adjustment_out')),
    ref_type TEXT NOT NULL DEFAULT '',
    ref_id INTEGER,
    note TEXT NOT NULL DEFAULT '',
    user_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    effective_date TEXT,
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
CREATE INDEX IF NOT EXISTS idx_sales_created ON sales (created_at);
CREATE INDEX IF NOT EXISTS idx_sales_user ON sales (user_id);
CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items (sale_id);
CREATE INDEX IF NOT EXISTS idx_sale_items_product ON sale_items (product_id);
CREATE INDEX IF NOT EXISTS idx_sale_payments_sale ON sale_payments (sale_id);
CREATE INDEX IF NOT EXISTS idx_stock_movements_product ON stock_movements (product_id, created_at);
