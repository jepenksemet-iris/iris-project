"""Form Flask-WTF (tahap 3 login tenant; tahap 6–7 produk & stok).
CSRF aktif via Flask-WTF."""
from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    FloatField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional


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


class ConfirmForm(FlaskForm):
    """Form kosong — hanya untuk CSRF pada aksi POST (arsipkan produk)."""
    submit = SubmitField("Ya, lanjutkan")
