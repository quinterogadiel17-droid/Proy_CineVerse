from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from catalog import ALLOWED_USER_EMAIL_DOMAINS, INSTITUTIONAL_DOMAIN
from extensions import mysql
from services.email_service import (
    confirm_email_token,
    generate_email_token,
    send_confirmation_email,
)

auth_bp = Blueprint("auth", __name__)


def is_allowed_client_email(email):
    domain = email.split("@")[-1].lower()
    return domain in ALLOWED_USER_EMAIL_DOMAINS


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        cur = mysql.connection.cursor(dictionary=True)
        cur.execute("SELECT * FROM usuarios WHERE email = %s", (email,))
        user = cur.fetchone()

        if not user or not check_password_hash(user["contrasena"], password):
            cur.close()
            flash("Credenciales incorrectas.", "error")
            return render_template("login.html")

        if not user.get("activo", 1):
            cur.close()
            flash("Tu cuenta fue bloqueada. Contacta al administrador.", "error")
            return render_template("login.html")

        if user["rol"] != "admin" and not user.get("verificado", 0):
            cur.close()
            flash("Debes confirmar tu correo antes de iniciar sesion.", "error")
            return render_template("login.html")

        cur.execute("UPDATE usuarios SET ultimo_login = NOW() WHERE id = %s", (user["id"],))
        mysql.connection.commit()
        cur.close()

        session["user_id"] = user["id"]
        session["user_nombre"] = user["nombre"]
        session["user_rol"] = user["rol"]

        flash("Bienvenido, " + user["nombre"] + ".", "success")
        if user["rol"] == "admin":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("peliculas.cartelera"))

    return render_template("login.html")


@auth_bp.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not is_allowed_client_email(email):
            flash("Solo se permite registro de clientes con cuentas Gmail.", "error")
            return render_template("registro.html")

        if email.endswith("@" + INSTITUTIONAL_DOMAIN):
            flash("Las cuentas administrativas se crean solo desde base de datos.", "error")
            return render_template("registro.html")

        cur = mysql.connection.cursor(dictionary=True)
        try:
            cur.execute(
                """
                INSERT INTO usuarios (nombre, email, contrasena, rol, verificado, activo)
                VALUES (%s, %s, %s, 'cliente', 0, 1)
                """,
                (nombre, email, generate_password_hash(password)),
            )
            mysql.connection.commit()
        except Exception:
            mysql.connection.rollback()
            cur.close()
            flash("El email ya esta registrado.", "error")
            return render_template("registro.html")

        cur.close()

        token = generate_email_token(email)
        confirm_url = url_for("auth.confirm_account", token=token, _external=True)
        sent, error = send_confirmation_email(nombre, email, confirm_url)

        if sent:
            return render_template(
                "auth_notice.html",
                title="Confirma tu cuenta",
                message="Te enviamos un correo de confirmacion. Revisa tu bandeja y activa tu cuenta para iniciar sesion.",
                confirmation_url=None,
            )

        return render_template(
            "auth_notice.html",
            title="Confirma tu cuenta",
            message="No fue posible enviar el correo porque SMTP no esta configurado en este entorno.",
            confirmation_url=confirm_url,
            error_detail=error,
        )

    return render_template("registro.html")


@auth_bp.route("/confirmar-cuenta/<token>")
def confirm_account(token):
    email = confirm_email_token(token)
    if not email:
        flash("El enlace de confirmacion es invalido o expiro.", "error")
        return redirect(url_for("auth.login"))

    cur = mysql.connection.cursor(dictionary=True)
    cur.execute(
        """
        UPDATE usuarios
        SET verificado = 1, fecha_confirmacion = NOW()
        WHERE email = %s AND rol = 'cliente'
        """,
        (email,),
    )
    mysql.connection.commit()
    cur.close()

    flash("Cuenta confirmada. Ya puedes iniciar sesion.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("peliculas.cartelera"))
