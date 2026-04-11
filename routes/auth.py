from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from catalog import ALLOWED_USER_EMAIL_DOMAINS, INSTITUTIONAL_DOMAIN
from extensions import mysql
from services.email_service import (
    confirm_email_token,
    confirm_password_reset_token,
    generate_email_token,
    generate_password_reset_token,
    send_confirmation_email_async,
    send_password_reset_email_async,
)

auth_bp = Blueprint("auth", __name__)


def is_allowed_client_email(email):
    domain = email.split("@")[-1].lower()
    return domain in ALLOWED_USER_EMAIL_DOMAINS


def is_local_environment():
    app_base_url = current_app.config.get("APP_BASE_URL", "")
    return app_base_url.startswith("http://localhost") or app_base_url.startswith("http://127.0.0.1")


def build_auth_notice(title, message, email=None, action_url=None, error_detail=None, confirmation_url=None):
    return render_template(
        "auth_notice.html",
        title=title,
        message=message,
        email=email,
        action_url=action_url,
        error_detail=error_detail,
        confirmation_url=confirmation_url,
    )


def queue_confirmation_email(user_name, email):
    token = generate_email_token(email)
    confirm_url = url_for("auth.confirm_account", token=token, _external=True)
    status, error = send_confirmation_email_async(user_name, email, confirm_url)
    return status, error, confirm_url


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
            flash(
                "Debes confirmar tu correo antes de iniciar sesion. Si no lo ves, reenvia el mensaje y revisa spam.",
                "error",
            )
            return redirect(url_for("auth.reenviar_confirmacion", email=email))

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
                SELECT id, nombre, email, rol, verificado
                FROM usuarios
                WHERE email = %s
                LIMIT 1
                """,
                (email,),
            )
            existing_user = cur.fetchone()

            if existing_user and (existing_user["rol"] == "admin" or existing_user["verificado"]):
                cur.close()
                flash("El email ya esta registrado.", "error")
                return render_template("registro.html")

            if existing_user:
                cur.execute(
                    """
                    UPDATE usuarios
                    SET nombre = %s,
                        contrasena = %s,
                        activo = 1,
                        verificado = 0,
                        fecha_confirmacion = NULL
                    WHERE id = %s
                    """,
                    (nombre, generate_password_hash(password), existing_user["id"]),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO usuarios (nombre, email, contrasena, rol, verificado, activo)
                    VALUES (%s, %s, %s, 'cliente', 0, 1)
                    """,
                    (nombre, email, generate_password_hash(password)),
                )

            mysql.connection.commit()
        except Exception as exc:
            mysql.connection.rollback()
            cur.close()
            current_app.logger.warning("No se pudo registrar/preparar el usuario %s: %s", email, exc)
            flash("No fue posible procesar el registro. Intenta nuevamente.", "error")
            return render_template("registro.html")

        cur.close()

        mail_status, error, confirm_url = queue_confirmation_email(nombre, email)
        if mail_status == "sent":
            message = "Te enviamos un correo de confirmacion. Revisa tu bandeja principal, spam o promociones para activar tu cuenta."
        elif mail_status == "queued":
            message = "Estamos procesando el envio del correo de confirmacion. Si no lo ves en unos minutos, revisa spam o usa la opcion de reenvio."
        else:
            message = "La cuenta quedo creada en estado pendiente, pero el correo no pudo salir ahora mismo. Puedes reintentarlo desde la opcion de reenvio."

        return build_auth_notice(
            title="Confirma tu cuenta",
            message=message,
            email=email,
            action_url=url_for("auth.reenviar_confirmacion", email=email),
            error_detail=error,
            confirmation_url=confirm_url if mail_status == "failed" and is_local_environment() else None,
        )

    return render_template("registro.html")


@auth_bp.route("/reenviar-confirmacion", methods=["GET", "POST"])
def reenviar_confirmacion():
    prefilled_email = request.args.get("email", "").strip().lower()

    if request.method == "POST":
        email = request.form["email"].strip().lower()
        new_email = request.form.get("new_email", "").strip().lower()

        cur = mysql.connection.cursor(dictionary=True)
        try:
            cur.execute(
                """
                SELECT id, nombre, email, rol, verificado
                FROM usuarios
                WHERE email = %s
                LIMIT 1
                """,
                (email,),
            )
            user = cur.fetchone()

            if not user or user["rol"] == "admin":
                cur.close()
                return build_auth_notice(
                    title="Revisa tu correo",
                    message="Si existe una cuenta pendiente con ese correo, volveremos a enviar el mensaje de confirmacion. Revisa spam o promociones.",
                    email=email,
                )

            if user.get("verificado", 0):
                cur.close()
                flash("Esa cuenta ya esta confirmada. Puedes iniciar sesion.", "success")
                return redirect(url_for("auth.login"))

            target_email = user["email"]
            if new_email and new_email != email:
                if not is_allowed_client_email(new_email):
                    cur.close()
                    flash("El nuevo correo debe ser una cuenta Gmail valida.", "error")
                    return render_template("auth_resend.html", prefilled_email=email, prefilled_new_email=new_email)
                if new_email.endswith("@" + INSTITUTIONAL_DOMAIN):
                    cur.close()
                    flash("No puedes cambiar a un dominio administrativo.", "error")
                    return render_template("auth_resend.html", prefilled_email=email, prefilled_new_email=new_email)

                cur.execute("SELECT id FROM usuarios WHERE email = %s LIMIT 1", (new_email,))
                existing_target = cur.fetchone()
                if existing_target:
                    cur.close()
                    flash("El nuevo correo ya esta en uso.", "error")
                    return render_template("auth_resend.html", prefilled_email=email, prefilled_new_email=new_email)

                cur.execute(
                    """
                    UPDATE usuarios
                    SET email = %s, verificado = 0, fecha_confirmacion = NULL
                    WHERE id = %s
                    """,
                    (new_email, user["id"]),
                )
                mysql.connection.commit()
                target_email = new_email

            cur.close()
        except Exception as exc:
            mysql.connection.rollback()
            cur.close()
            current_app.logger.warning("No se pudo preparar el reenvio de confirmacion para %s: %s", email, exc)
            flash("No fue posible reenviar el correo en este momento.", "error")
            return render_template("auth_resend.html", prefilled_email=email, prefilled_new_email=new_email)

        mail_status, error, confirm_url = queue_confirmation_email(user["nombre"], target_email)
        if mail_status == "sent":
            message = "Reenviamos el correo de confirmacion. Revisa tu bandeja principal, spam o promociones."
        elif mail_status == "queued":
            message = "Estamos procesando el reenvio del correo. Si no lo ves en unos minutos, revisa spam o vuelve a intentarlo."
        else:
            message = "No pudimos enviar el correo en este momento, pero puedes intentarlo de nuevo mas tarde."
        return build_auth_notice(
            title="Reenvio de confirmacion",
            message=message,
            email=target_email,
            action_url=url_for("auth.reenviar_confirmacion", email=target_email),
            error_detail=error,
            confirmation_url=confirm_url if mail_status == "failed" and is_local_environment() else None,
        )

    return render_template("auth_resend.html", prefilled_email=prefilled_email, prefilled_new_email="")


@auth_bp.route("/confirmar-cuenta/<token>")
def confirm_account(token):
    email = confirm_email_token(token)
    if not email:
        flash("El enlace de confirmacion es invalido o expiro.", "error")
        return redirect(url_for("auth.reenviar_confirmacion"))

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


@auth_bp.route("/olvide-contrasena", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"].strip().lower()

        cur = mysql.connection.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, nombre, email, activo
            FROM usuarios
            WHERE email = %s
            LIMIT 1
            """,
            (email,),
        )
        user = cur.fetchone()
        cur.close()

        if user and user.get("activo", 1):
            token = generate_password_reset_token(user["email"])
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            send_password_reset_email_async(user["nombre"], user["email"], reset_url)

        return build_auth_notice(
            title="Revisa tu correo",
            message="Si encontramos una cuenta asociada, te enviaremos un enlace para restablecer la contrasena. Revisa tambien spam o promociones.",
            email=email,
        )

    return render_template("forgot_password.html")


@auth_bp.route("/restablecer-contrasena/<token>", methods=["GET", "POST"])
def reset_password(token):
    email = confirm_password_reset_token(token)
    if not email:
        flash("El enlace para cambiar la contrasena es invalido o expiro.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if len(password) < 6:
            flash("La contrasena debe tener al menos 6 caracteres.", "error")
            return render_template("reset_password.html", token=token)

        if password != confirm_password:
            flash("Las contrasenas no coinciden.", "error")
            return render_template("reset_password.html", token=token)

        cur = mysql.connection.cursor(dictionary=True)
        cur.execute("SELECT id FROM usuarios WHERE email = %s LIMIT 1", (email,))
        user = cur.fetchone()

        if not user:
            cur.close()
            flash("No encontramos una cuenta asociada a este enlace.", "error")
            return redirect(url_for("auth.forgot_password"))

        cur.execute(
            "UPDATE usuarios SET contrasena = %s WHERE id = %s",
            (generate_password_hash(password), user["id"]),
        )
        mysql.connection.commit()
        cur.close()

        flash("Contrasena actualizada. Ya puedes iniciar sesion.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html", token=token)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("peliculas.cartelera"))
