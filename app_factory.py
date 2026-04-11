import logging
import time
from datetime import timedelta

from flask import Flask, jsonify, redirect, render_template, request, session, url_for, g
from werkzeug.exceptions import HTTPException

from catalog import (
    ALLOWED_USER_EMAIL_DOMAINS,
    APP_NAME,
    APP_TAGLINE,
    INSTITUTIONAL_DOMAIN,
    PAYMENT_METHODS,
    PROJECTION_FORMATS,
)
from config import Config
from extensions import mysql
from services.email_service import get_mail_configuration_status, log_mail_configuration

logger = logging.getLogger(__name__)
_location_cache = {
    "expires_at": 0.0,
    "cities": [],
}

MESES_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def format_time(value):
    if value is None:
        return ""
    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    text = str(value)
    return text[:5] if len(text) >= 5 else text


def format_date(value):
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        month_name = MESES_ES.get(value.month, value.strftime("%B").lower())
        return f"{value.day:02d} de {month_name}"
    return str(value)


def format_short_date(value):
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    return str(value)


def format_currency(value):
    if value is None:
        return "$0"
    return "$" + "{:,.0f}".format(float(value))


def load_location_context():
    conn = mysql.connection
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT id, nombre FROM ciudades ORDER BY nombre")
    cities = cur.fetchall()

    selected_city_id = session.get("selected_city_id")
    selected_sede_id = session.get("selected_sede_id")

    current_sedes = []
    selected_city = None
    selected_sede = None

    if selected_city_id:
        cur.execute("SELECT id, nombre FROM ciudades WHERE id = %s", (selected_city_id,))
        selected_city = cur.fetchone()

        cur.execute(
            "SELECT id, nombre FROM sedes WHERE ciudad_id = %s ORDER BY nombre",
            (selected_city_id,),
        )
        current_sedes = cur.fetchall()

    if selected_sede_id:
        cur.execute("SELECT id, nombre, ciudad_id FROM sedes WHERE id = %s", (selected_sede_id,))
        selected_sede = cur.fetchone()

    cur.close()
    return cities, current_sedes, selected_city, selected_sede


def _load_cached_cities():
    now = time.time()
    if _location_cache["cities"] and _location_cache["expires_at"] > now:
        return _location_cache["cities"]

    cur = mysql.connection.cursor(dictionary=True)
    try:
        cur.execute("SELECT id, nombre FROM ciudades ORDER BY nombre")
        cities = cur.fetchall()
    finally:
        cur.close()

    _location_cache["cities"] = cities
    _location_cache["expires_at"] = now + max(int(Config.MYSQL_LOCATION_CACHE_SECONDS), 15)
    return cities


def get_safe_location_context():
    try:
        cities = _load_cached_cities()
        if not session.get("selected_city_id") and not session.get("selected_sede_id"):
            return cities, [], None, None

        conn = mysql.connection
        cur = conn.cursor(dictionary=True)
        try:
            selected_city_id = session.get("selected_city_id")
            selected_sede_id = session.get("selected_sede_id")
            current_sedes = []
            selected_city = None
            selected_sede = None

            if selected_city_id:
                cur.execute("SELECT id, nombre FROM ciudades WHERE id = %s", (selected_city_id,))
                selected_city = cur.fetchone()

                cur.execute(
                    "SELECT id, nombre FROM sedes WHERE ciudad_id = %s ORDER BY nombre",
                    (selected_city_id,),
                )
                current_sedes = cur.fetchall()

            if selected_sede_id:
                cur.execute("SELECT id, nombre, ciudad_id FROM sedes WHERE id = %s", (selected_sede_id,))
                selected_sede = cur.fetchone()
        finally:
            cur.close()

        return cities, current_sedes, selected_city, selected_sede
    except Exception as exc:
        logger.warning("No se pudo cargar el contexto de ubicacion desde la DB: %s", exc)
        return [], [], None, None


def _register_filters(app):
    app.jinja_env.filters["format_time"] = format_time
    app.jinja_env.filters["format_date"] = format_date
    app.jinja_env.filters["format_short_date"] = format_short_date
    app.jinja_env.filters["format_currency"] = format_currency


def _register_hooks(app):
    @app.teardown_appcontext
    def close_db_connection(exception=None):
        db = g.pop("db_conn", None)
        if db is not None and db.is_connected():
            db.close()

    @app.before_request
    def enforce_active_session_user():
        user_id = session.get("user_id")
        if not user_id or request.endpoint == "static":
            return

        try:
            cur = mysql.connection.cursor(dictionary=True)
            cur.execute("SELECT id, nombre, rol, activo FROM usuarios WHERE id = %s", (user_id,))
            user = cur.fetchone()
            cur.close()
        except Exception as exc:
            logger.warning("No se pudo validar la sesion contra la DB: %s", exc)
            if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
                return jsonify({"error": "Servicio temporalmente no disponible."}), 503
            return

        if not user or not user.get("activo", 1):
            session.clear()
            message = (
                "Tu cuenta fue bloqueada o eliminada. Inicia sesion nuevamente."
                if user
                else "Tu sesion ya no es valida. Inicia sesion nuevamente."
            )

            if request.path.startswith("/api/") or request.path.startswith("/admin/api/") or (
                request.endpoint
                and (
                    request.endpoint.startswith("peliculas.api_")
                    or request.endpoint.startswith("funciones.api_")
                    or request.endpoint.startswith("tiquetes.api_")
                )
            ):
                return jsonify({"error": message}), 403

            if request.endpoint and request.endpoint.startswith("auth."):
                return

            return redirect(url_for("auth.login"))

        session["user_nombre"] = user["nombre"]
        session["user_rol"] = user["rol"]

    @app.before_request
    def enforce_location_selection():
        session.setdefault("allowed_user_domains", list(ALLOWED_USER_EMAIL_DOMAINS))
        excluded_endpoints = {
            "static",
            "choose_location",
            "update_location",
            "api_city_sedes",
            "healthz",
            "healthz_mail",
            "index",
            "auth.login",
            "auth.registro",
            "auth.confirm_account",
            "auth.logout",
            "auth.reenviar_confirmacion",
            "auth.forgot_password",
            "auth.reset_password",
            "tiquetes.validar_page",
            "tiquetes.api_validar",
        }

        if request.endpoint is None or request.endpoint in excluded_endpoints:
            return
        if request.endpoint.startswith("admin."):
            return
        if request.endpoint.startswith("auth."):
            return
        if request.endpoint.startswith("peliculas.api_"):
            return
        if request.endpoint.startswith("funciones.api_"):
            return
        if request.endpoint.startswith("tiquetes.api_"):
            return

        if not session.get("selected_city_id"):
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("choose_location", next=next_url))

    @app.context_processor
    def inject_brand_context():
        cities, current_sedes, selected_city, selected_sede = get_safe_location_context()
        return {
            "app_name": APP_NAME,
            "app_tagline": APP_TAGLINE,
            "institutional_domain": INSTITUTIONAL_DOMAIN,
            "city_options": cities,
            "header_sedes": current_sedes,
            "selected_city": selected_city,
            "selected_sede": selected_sede,
            "projection_formats": PROJECTION_FORMATS,
            "payment_methods": PAYMENT_METHODS,
        }

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc):
        if isinstance(exc, HTTPException):
            return exc

        logger.exception("Error no controlado atendiendo %s %s", request.method, request.path)
        if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
            return jsonify({"error": "Error interno del servidor."}), 500
        return render_template("error.html"), 500


def _register_routes(app):
    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"}), 200

    @app.get("/healthz/mail")
    def healthz_mail():
        status = get_mail_configuration_status()
        payload = {
            "provider": status["provider"],
            "configured": status["configured"],
            "api_key": status["api_key_masked"],
            "from_email": status["from_email"],
            "from_name": status["from_name"],
            "timeout_seconds": status["timeout_seconds"],
            "missing": status["missing"],
        }
        http_status = 200 if status["configured"] else 503
        return jsonify(payload), http_status

    @app.route("/seleccionar-ubicacion", methods=["GET"])
    def choose_location():
        next_url = request.args.get("next", url_for("peliculas.cartelera"))
        cities = []
        sedes = []
        current_city_id = session.get("selected_city_id")

        try:
            cities = _load_cached_cities()
            first_city_id = cities[0]["id"] if cities else None
            current_city_id = current_city_id or first_city_id

            if current_city_id:
                cur = mysql.connection.cursor(dictionary=True)
                try:
                    cur.execute(
                        "SELECT id, nombre FROM sedes WHERE ciudad_id = %s ORDER BY nombre",
                        (current_city_id,),
                    )
                    sedes = cur.fetchall()
                finally:
                    cur.close()
        except Exception as exc:
            logger.warning("No se pudo cargar la pantalla de ubicacion desde la DB: %s", exc)

        return render_template(
            "select_location.html",
            cities=cities,
            sedes=sedes,
            next_url=next_url,
            current_city_id=current_city_id,
            selected_sede_id=session.get("selected_sede_id"),
        )

    @app.post("/preferencias/ubicacion")
    def update_location():
        city_id = request.form.get("city_id", "").strip()
        sede_id = request.form.get("sede_id", "").strip()
        next_url = request.form.get("next", url_for("peliculas.cartelera")).strip()

        if city_id.isdigit():
            session["selected_city_id"] = int(city_id)
        else:
            session.pop("selected_city_id", None)

        if sede_id.isdigit():
            session["selected_sede_id"] = int(sede_id)
        else:
            session.pop("selected_sede_id", None)

        if not next_url.startswith("/"):
            next_url = url_for("peliculas.cartelera")
        return redirect(next_url)

    @app.get("/api/ciudades/<int:city_id>/sedes")
    def api_city_sedes(city_id):
        try:
            cur = mysql.connection.cursor(dictionary=True)
            cur.execute("SELECT id, nombre FROM sedes WHERE ciudad_id = %s ORDER BY nombre", (city_id,))
            sedes = cur.fetchall()
            cur.close()
            return jsonify(sedes)
        except Exception as exc:
            logger.warning("No se pudieron consultar sedes para la ciudad %s: %s", city_id, exc)
            return jsonify({"error": "Servicio temporalmente no disponible."}), 503

    @app.route("/")
    def index():
        if not session.get("selected_city_id"):
            return redirect(url_for("choose_location"))
        return redirect(url_for("peliculas.cartelera"))


def create_app():
    app = Flask(
        __name__,
        static_folder=str(Config.PROJECT_ROOT / "static"),
        template_folder=str(Config.PROJECT_ROOT / "templates"),
        static_url_path="/static",
    )
    app.config.from_object(Config)
    app.config.setdefault("SEND_FILE_MAX_AGE_DEFAULT", 300)

    with app.app_context():
        log_mail_configuration("startup")
        logger.info("APP_BASE_URL=%s ENVIRONMENT=%s", app.config.get("APP_BASE_URL"), app.config.get("ENVIRONMENT"))

    mysql.init_app(app)
    _register_filters(app)
    _register_hooks(app)
    _register_routes(app)

    from routes.admin import admin_bp
    from routes.auth import auth_bp
    from routes.funciones import funciones_bp
    from routes.peliculas import peliculas_bp
    from routes.tiquetes import tiquetes_bp

    app.register_blueprint(peliculas_bp)
    app.register_blueprint(funciones_bp)
    app.register_blueprint(tiquetes_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(auth_bp)

    return app
