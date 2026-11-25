"""Form Flask-WTF tahap 3 (login tenant). CSRF aktif via Flask-WTF."""
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=64)])
    tenant = StringField("Tenant (slug)", validators=[DataRequired(), Length(max=63)])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Masuk")
