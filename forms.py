"""Form Flask-WTF (tahap 3 login tenant; tahap 6–7 produk & stok).
CSRF aktif via Flask-WTF."""
from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    FloatField,
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    InputRequired,
    Length,
    NumberRange,
    Optional,
)


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=64)])
    tenant = StringField("Tenant (slug)", validators=[DataRequired(), Length(max=63)])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Masuk")


class ProductForm(FlaskForm):
    sku = StringField("SKU", validators=[DataRequired(), Length(max=64)])
    name = StringField("Nama produk", validators=[DataRequired(), Length(max=200)])
    barcode = StringField("Barcode", validators=[Optional(), Length(max=64)])
    category = StringField("Kategori", validators=[Optional(), Length(max=100)])
    unit = StringField(
        "Satuan dasar (mis. pcs, kg)",
        validators=[DataRequired(), Length(max=32)],
    )
    buy_price = IntegerField(
        "Harga beli (Rp)", validators=[DataRequired(), NumberRange(min=0)]
    )
    sell_price = IntegerField(
        "Harga jual (Rp)", validators=[DataRequired(), NumberRange(min=0)]
    )
    min_stock = FloatField(
        "Stok minimum (opsional, kosong = 0)",
        validators=[Optional(), NumberRange(min=0)],
    )
    submit = SubmitField("Simpan")


class StockAdjustForm(FlaskForm):
    outlet_id = SelectField("Outlet", coerce=int, validators=[DataRequired()])
    kind = SelectField(
        "Jenis mutasi",
        choices=[
            ("opening_balance", "Saldo awal"),
            ("adjustment_in", "Penyesuaian masuk"),
            ("adjustment_out", "Penyesuaian keluar"),
        ],
        validators=[DataRequired()],
    )
    qty_delta = FloatField(
        "Jumlah (harus lebih dari 0)",
        validators=[DataRequired(), NumberRange(min=0)],
    )
    effective_date = DateField(
        "Tanggal efektif (opsional, kosong = hari ini)",
        validators=[Optional()],
    )
    note = StringField("Keterangan", validators=[Optional(), Length(max=200)])
    submit = SubmitField("Simpan penyesuaian")


class CartAddForm(FlaskForm):
    product_id = IntegerField("Produk", validators=[DataRequired()])
    # InputRequired (bukan DataRequired): angka 0 harus lolos validasi
    # form supaya ditolak dengan pesan yang jelas di route.
    qty = FloatField(
        "Kuantitas",
        validators=[InputRequired(),
                    NumberRange(min=0, message="Kuantitas harus lebih dari 0.")],
        default=1,
    )
    submit = SubmitField("Tambah")


class CartSetForm(FlaskForm):
    product_id = IntegerField("Produk", validators=[DataRequired()])
    qty = FloatField(
        "Kuantitas",
        validators=[InputRequired(),
                    NumberRange(min=0, message="Kuantitas harus lebih dari 0.")],
    )
    submit = SubmitField("Ubah")


class CartRemoveForm(FlaskForm):
    product_id = IntegerField("Produk", validators=[DataRequired()])
    submit = SubmitField("Hapus")


class CheckoutForm(FlaskForm):
    payment_method = SelectField(
        "Metode pembayaran",
        choices=[
            ("cash", "Tunai"),
            ("transfer", "Transfer bank (dicatat manual)"),
            ("qris", "QRIS (dicatat manual)"),
            ("debit", "Debit (dicatat manual)"),
        ],
        validators=[DataRequired()],
    )
    amount_tendered = IntegerField(
        "Uang diterima (Rp, tunai)",
        validators=[Optional(), NumberRange(min=0)],
    )
    payment_ref = StringField(
        "Referensi pembayaran (opsional, non-tunai)",
        validators=[Optional(), Length(max=100)],
    )
    idempotency_key = HiddenField("Token checkout", validators=[DataRequired()])
    submit = SubmitField("Proses pembayaran")


class ConfirmForm(FlaskForm):
    """Form kosong — hanya untuk CSRF pada aksi POST (arsipkan produk)."""
    submit = SubmitField("Ya, lanjutkan")
