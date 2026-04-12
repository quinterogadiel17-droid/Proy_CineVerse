from collections import defaultdict
from functools import wraps
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from catalog import PROJECTION_FORMATS
from extensions import mysql
from services.asset_service import (
    append_asset_manifest,
    build_data_url,
    read_uploaded_poster_bytes,
    resolve_poster_url,
)
from services.email_service import generate_email_token, send_confirmation_email_async
from services.reservation_service import (
    ReservationConflictError,
    ReservationValidationError,
    delete_user_account,
    log_admin_action,
    normalize_positive_ids,
    release_ticket_seats,
)

admin_bp = Blueprint("admin", __name__)


def admin_required(view):
    @wraps(view)
    def decorated(*args, **kwargs):
        if session.get("user_rol") != "admin":
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return decorated


def queue_confirmation_email_for_user(user_name, email):
    try:
        token = generate_email_token(email)
        confirm_url = url_for("auth.confirm_account", token=token, _external=True)
        status, error = send_confirmation_email_async(user_name, email, confirm_url)
        return status, error, confirm_url
    except Exception as exc:
        current_app.logger.exception("No se pudo preparar o encolar verificacion para %s", email)
        return "failed", str(exc), None


@admin_bp.route("/")
@admin_required
def dashboard():
    cur = mysql.connection.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS total FROM tiquetes WHERE estado != 'cancelado'")
    total_tickets = cur.fetchone()["total"]

    cur.execute("SELECT COALESCE(SUM(total), 0) AS ingresos FROM tiquetes WHERE estado != 'cancelado'")
    ingresos = cur.fetchone()["ingresos"]

    cur.execute("SELECT COUNT(*) AS total FROM peliculas WHERE estado = 'activa'")
    total_movies = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) AS total FROM funciones WHERE fecha >= CURDATE() AND estado = 'disponible'")
    total_shows = cur.fetchone()["total"]

    cur.execute(
        """
        SELECT DATE(fecha_compra) AS dia, SUM(total) AS total_dia, COUNT(*) AS num_ventas
        FROM tiquetes
        WHERE estado != 'cancelado' AND fecha_compra >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        GROUP BY DATE(fecha_compra)
        ORDER BY dia
        """
    )
    sales = cur.fetchall()
    for sale in sales:
        sale["dia"] = str(sale["dia"])

    cur.execute(
        """
        SELECT f.sala, f.hora, f.formato, s.nombre AS sede_nombre, c.nombre AS ciudad_nombre, p.titulo,
               COUNT(af.id) AS ocupados,
               (150 - COUNT(af.id)) AS disponibles
        FROM funciones f
        JOIN peliculas p ON p.id = f.pelicula_id
        JOIN sedes s ON s.id = f.sede_id
        JOIN ciudades c ON c.id = s.ciudad_id
        LEFT JOIN asientos_funcion af ON af.funcion_id = f.id
        WHERE f.fecha = CURDATE()
        GROUP BY f.id
        ORDER BY c.nombre, s.nombre, f.hora
        """
    )
    occupancy = cur.fetchall()
    for row in occupancy:
        if row.get("hora"):
            row["hora"] = str(row["hora"])[:5]

    cur.execute(
        """
        SELECT p.titulo, COUNT(dt.id) AS total_asientos
        FROM peliculas p
        JOIN funciones f ON f.pelicula_id = p.id
        JOIN tiquetes t ON t.funcion_id = f.id
        JOIN detalle_tiquete dt ON dt.tiquete_id = t.id
        WHERE t.estado != 'cancelado'
        GROUP BY p.id
        ORDER BY total_asientos DESC
        LIMIT 5
        """
    )
    top_movies = cur.fetchall()
    cur.close()

    return render_template(
        "admin/dashboard.html",
        total_tiquetes=total_tickets,
        ingresos=ingresos,
        total_peliculas=total_movies,
        total_funciones=total_shows,
        ventas_dia=sales,
        ocupacion=occupancy,
        top_peliculas=top_movies,
    )


@admin_bp.route("/peliculas")
@admin_required
def peliculas():
    cur = mysql.connection.cursor(dictionary=True)
    cur.execute(
        """
        SELECT
            id, titulo, descripcion, duracion, genero, categoria, clasificacion,
            imagen_url, trailer_url, estado, fecha_creacion,
            CASE WHEN poster_blob IS NULL THEN 0 ELSE 1 END AS has_poster_blob
        FROM peliculas
        ORDER BY fecha_creacion DESC
        """
    )
    movies = cur.fetchall()
    cur.close()
    for movie in movies:
        if movie.get("has_poster_blob"):
            movie["imagen_url"] = url_for("peliculas.poster_image", id=movie["id"])
        else:
            movie["imagen_url"] = resolve_poster_url(movie.get("imagen_url"))
    return render_template("admin/peliculas.html", peliculas=movies)


@admin_bp.route("/funciones")
@admin_required
def funciones():
    cur = mysql.connection.cursor(dictionary=True)
    cur.execute(
        """
        SELECT f.*, p.titulo, s.nombre AS sede_nombre, c.nombre AS ciudad_nombre,
               COUNT(af.id) AS asientos_ocupados
        FROM funciones f
        JOIN peliculas p ON p.id = f.pelicula_id
        JOIN sedes s ON s.id = f.sede_id
        JOIN ciudades c ON c.id = s.ciudad_id
        LEFT JOIN asientos_funcion af ON af.funcion_id = f.id
        GROUP BY f.id
        ORDER BY f.fecha DESC, c.nombre, s.nombre, f.hora
        """
    )
    functions = cur.fetchall()
    for function in functions:
        if function.get("fecha"):
            function["fecha"] = str(function["fecha"])
        if function.get("hora"):
            function["hora"] = str(function["hora"])[:5]

    cur.execute("SELECT id, titulo FROM peliculas WHERE estado = 'activa' ORDER BY titulo")
    movies = cur.fetchall()

    cur.execute(
        """
        SELECT s.id, s.nombre, c.id AS ciudad_id, c.nombre AS ciudad_nombre
        FROM sedes s
        JOIN ciudades c ON c.id = s.ciudad_id
        ORDER BY c.nombre, s.nombre
        """
    )
    venues = cur.fetchall()
    cur.close()

    return render_template(
        "admin/funciones.html",
        funciones=functions,
        peliculas=movies,
        sedes=venues,
        formatos=PROJECTION_FORMATS,
    )


@admin_bp.route("/usuarios")
@admin_required
def usuarios():
    nombre = request.args.get("nombre", "").strip()
    email = request.args.get("email", "").strip().lower()
    filters = []
    params = []

    if nombre:
        filters.append("u.nombre LIKE %s")
        params.append(f"%{nombre}%")

    if email:
        filters.append("u.email LIKE %s")
        params.append(f"%{email}%")

    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

    cur = mysql.connection.cursor(dictionary=True)
    cur.execute(
        f"""
        SELECT u.id, u.nombre, u.email, u.rol, u.verificado, u.activo,
               u.fecha_creacion, u.ultimo_login,
               COUNT(CASE WHEN t.estado = 'activo' THEN 1 END) AS reservas_activas
        FROM usuarios u
        LEFT JOIN tiquetes t ON t.usuario_id = u.id
        {where_sql}
        GROUP BY u.id
        ORDER BY u.fecha_creacion DESC
        """,
        params,
    )
    users = cur.fetchall()

    cur.execute(
        """
        SELECT
            COUNT(*) AS total_usuarios,
            SUM(CASE WHEN rol = 'cliente' THEN 1 ELSE 0 END) AS total_clientes,
            SUM(CASE WHEN activo = 0 THEN 1 ELSE 0 END) AS total_bloqueados,
            SUM(CASE WHEN verificado = 0 THEN 1 ELSE 0 END) AS total_no_verificados
        FROM usuarios
        """
    )
    stats = cur.fetchone()
    cur.close()

    return render_template(
        "admin/usuarios.html",
        usuarios=users,
        filtros={"nombre": nombre, "email": email},
        stats=stats,
    )


@admin_bp.route("/api/usuarios/<int:user_id>/estado", methods=["POST"])
@admin_required
def toggle_user_status(user_id):
    cur = mysql.connection.cursor(dictionary=True)
    try:
        cur.execute("SELECT id, nombre, email, rol, activo FROM usuarios WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            cur.close()
            return jsonify({"error": "Usuario no encontrado"}), 404

        if user["rol"] == "admin":
            cur.close()
            return jsonify({"error": "No puedes bloquear administradores desde esta vista"}), 400

        new_status = 0 if user["activo"] else 1
        cur.execute("UPDATE usuarios SET activo = %s WHERE id = %s", (new_status, user_id))
        log_admin_action(
            cur,
            session["user_id"],
            "toggle_user_status",
            {
                "target_user_id": user["id"],
                "target_user_email": user["email"],
                "target_user_name": user["nombre"],
                "active": bool(new_status),
            },
        )
        mysql.connection.commit()
        cur.close()
        return jsonify(
            {
                "activo": bool(new_status),
                "mensaje": "Usuario reactivado." if new_status else "Usuario bloqueado.",
            }
        )
    except Exception as exc:
        mysql.connection.rollback()
        cur.close()
        return jsonify({"error": "No se pudo actualizar el usuario.", "detalle": str(exc)}), 500


@admin_bp.route("/api/usuarios/<int:user_id>/verificar", methods=["POST"])
@admin_required
def verify_user(user_id):
    cur = mysql.connection.cursor(dictionary=True)
    try:
        cur.execute("SELECT id, nombre, email, rol, verificado FROM usuarios WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            cur.close()
            return jsonify({"error": "Usuario no encontrado"}), 404

        if user["rol"] == "admin":
            cur.close()
            return jsonify({"error": "Los administradores ya estan verificados."}), 400

        if user["verificado"]:
            cur.close()
            return jsonify({"verificado": True, "mensaje": "El usuario ya estaba verificado."})

        cur.execute(
            """
            UPDATE usuarios
            SET verificado = 1, fecha_confirmacion = NOW(), activo = 1
            WHERE id = %s
            """,
            (user_id,),
        )
        log_admin_action(
            cur,
            session["user_id"],
            "verify_user",
            {
                "target_user_id": user["id"],
                "target_user_email": user["email"],
                "target_user_name": user["nombre"],
            },
        )
        mysql.connection.commit()
        cur.close()
        return jsonify({"verificado": True, "mensaje": "Usuario verificado manualmente."})
    except Exception as exc:
        mysql.connection.rollback()
        cur.close()
        return jsonify({"error": "No se pudo verificar el usuario.", "detalle": str(exc)}), 500


@admin_bp.route("/api/usuarios/<int:user_id>/reenviar-verificacion", methods=["POST"])
@admin_required
def resend_user_verification(user_id):
    cur = mysql.connection.cursor(dictionary=True)
    try:
        cur.execute("SELECT id, nombre, email, rol, verificado, activo FROM usuarios WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            cur.close()
            return jsonify({"error": "Usuario no encontrado"}), 404

        if user["rol"] == "admin":
            cur.close()
            return jsonify({"error": "No aplica para administradores."}), 400

        cur.close()
        status, error, _ = queue_confirmation_email_for_user(user["nombre"], user["email"])
        if status == "failed":
            return jsonify({"error": error or "No se pudo reenviar el correo."}), 502

        cur = mysql.connection.cursor(dictionary=True)
        log_admin_action(
            cur,
            session["user_id"],
            "resend_user_verification",
            {
                "target_user_id": user["id"],
                "target_user_email": user["email"],
                "target_user_name": user["nombre"],
                "mail_status": status,
            },
        )
        mysql.connection.commit()
        cur.close()
        return jsonify(
            {
                "mensaje": (
                    "Correo de verificacion reenviado."
                    if status == "sent"
                    else "Correo de verificacion encolado para envio."
                )
            }
        )
    except Exception as exc:
        mysql.connection.rollback()
        try:
            cur.close()
        except Exception:
            pass
        current_app.logger.warning("No se pudo reenviar verificacion para user_id=%s: %s", user_id, exc)
        return jsonify({"error": "No se pudo reenviar la verificacion.", "detalle": str(exc)}), 500


@admin_bp.route("/api/usuarios/<int:user_id>", methods=["PUT"])
@admin_required
def update_user(user_id):
    data = request.get_json(silent=True) or {}
    nombre = str(data.get("nombre", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    activo = data.get("activo")
    verificado = data.get("verificado")

    if not nombre or not email:
        return jsonify({"error": "Nombre y correo son obligatorios."}), 400

    cur = mysql.connection.cursor(dictionary=True)
    try:
        cur.execute("SELECT id, nombre, email, rol, activo, verificado FROM usuarios WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            cur.close()
            return jsonify({"error": "Usuario no encontrado"}), 404

        if user["rol"] == "admin" and email != user["email"]:
            cur.close()
            return jsonify({"error": "No puedes cambiar el correo de un administrador desde esta vista."}), 400

        cur.execute("SELECT id FROM usuarios WHERE email = %s AND id != %s LIMIT 1", (email, user_id))
        if cur.fetchone():
            cur.close()
            return jsonify({"error": "Ese correo ya esta en uso."}), 409

        active_value = user["activo"] if activo is None else int(bool(activo))
        verified_value = user["verificado"] if verificado is None else int(bool(verificado))
        fecha_confirmacion_sql = "NOW()" if verified_value else "NULL"

        cur.execute(
            f"""
            UPDATE usuarios
            SET nombre = %s,
                email = %s,
                activo = %s,
                verificado = %s,
                fecha_confirmacion = {fecha_confirmacion_sql}
            WHERE id = %s
            """,
            (nombre, email, active_value, verified_value, user_id),
        )
        log_admin_action(
            cur,
            session["user_id"],
            "update_user",
            {
                "target_user_id": user["id"],
                "before": {
                    "nombre": user["nombre"],
                    "email": user["email"],
                    "activo": bool(user["activo"]),
                    "verificado": bool(user["verificado"]),
                },
                "after": {
                    "nombre": nombre,
                    "email": email,
                    "activo": bool(active_value),
                    "verificado": bool(verified_value),
                },
            },
        )
        mysql.connection.commit()
        cur.close()
        return jsonify(
            {
                "mensaje": "Usuario actualizado correctamente.",
                "usuario": {
                    "id": user_id,
                    "nombre": nombre,
                    "email": email,
                    "activo": bool(active_value),
                    "verificado": bool(verified_value),
                },
            }
        )
    except Exception as exc:
        mysql.connection.rollback()
        cur.close()
        return jsonify({"error": "No se pudo actualizar el usuario.", "detalle": str(exc)}), 500


@admin_bp.route("/api/usuarios/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):
    cur = mysql.connection.cursor(dictionary=True)
    try:
        result = delete_user_account(cur, user_id, admin_id=session["user_id"])
        mysql.connection.commit()
        cur.close()
        return jsonify(
            {
                "mensaje": "Usuario eliminado correctamente.",
                "usuario": result["user_name"],
                "tiquetes_cancelados": result["cancelled_tickets"],
                "asientos_liberados": result["released_seats"],
            }
        )
    except (ReservationConflictError, ReservationValidationError) as exc:
        mysql.connection.rollback()
        cur.close()
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        mysql.connection.rollback()
        cur.close()
        return jsonify({"error": "No se pudo eliminar el usuario.", "detalle": str(exc)}), 500


@admin_bp.route("/api/usuarios/acciones-masivas", methods=["POST"])
@admin_required
def bulk_user_actions():
    data = request.get_json(silent=True) or {}
    action = str(data.get("action", "")).strip().lower()
    user_ids = normalize_positive_ids(data.get("user_ids", []))

    if not user_ids:
        return jsonify({"error": "Selecciona al menos un usuario."}), 400

    placeholders = ",".join(["%s"] * len(user_ids))
    cur = mysql.connection.cursor(dictionary=True)

    try:
        cur.execute(
            f"""
            SELECT id, nombre, email, rol, activo
            FROM usuarios
            WHERE id IN ({placeholders})
            FOR UPDATE
            """,
            user_ids,
        )
        users = cur.fetchall()
        if not users:
            mysql.connection.rollback()
            cur.close()
            return jsonify({"error": "No se encontraron usuarios para procesar."}), 404

        protected_users = [user for user in users if user["rol"] == "admin"]
        target_users = [user for user in users if user["rol"] != "admin"]

        if not target_users:
            mysql.connection.rollback()
            cur.close()
            return jsonify({"error": "La seleccion solo contiene administradores protegidos."}), 400

        if action == "block":
            target_ids = [user["id"] for user in target_users]
            target_placeholders = ",".join(["%s"] * len(target_ids))
            cur.execute(
                f"UPDATE usuarios SET activo = 0 WHERE id IN ({target_placeholders})",
                target_ids,
            )
            log_admin_action(
                cur,
                session["user_id"],
                "bulk_block_users",
                {
                    "target_user_ids": target_ids,
                    "target_emails": [user["email"] for user in target_users],
                    "protected_user_ids": [user["id"] for user in protected_users],
                },
            )
            mysql.connection.commit()
            cur.close()
            return jsonify(
                {
                    "mensaje": "Usuarios bloqueados correctamente.",
                    "procesados": len(target_users),
                    "omitidos": len(protected_users),
                }
            )

        if action == "delete":
            deleted = []
            released_seats = 0
            for user in target_users:
                result = delete_user_account(cur, user["id"], admin_id=session["user_id"])
                deleted.append(result["user_email"])
                released_seats += result["released_seats"]

            mysql.connection.commit()
            cur.close()
            return jsonify(
                {
                    "mensaje": "Usuarios eliminados correctamente.",
                    "procesados": len(target_users),
                    "omitidos": len(protected_users),
                    "eliminados": deleted,
                    "asientos_liberados": released_seats,
                }
            )

        mysql.connection.rollback()
        cur.close()
        return jsonify({"error": "Accion masiva no soportada."}), 400
    except (ReservationConflictError, ReservationValidationError) as exc:
        mysql.connection.rollback()
        cur.close()
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        mysql.connection.rollback()
        cur.close()
        return jsonify({"error": "No se pudo completar la accion masiva.", "detalle": str(exc)}), 500


@admin_bp.route("/api/funciones/<int:function_id>/asientos-ocupados")
@admin_required
def occupied_seats(function_id):
    cur = mysql.connection.cursor(dictionary=True)
    cur.execute(
        """
        SELECT f.id, f.fecha, f.hora, f.estado, p.titulo, s.nombre AS sede_nombre, c.nombre AS ciudad_nombre
        FROM funciones f
        JOIN peliculas p ON p.id = f.pelicula_id
        JOIN sedes s ON s.id = f.sede_id
        JOIN ciudades c ON c.id = s.ciudad_id
        WHERE f.id = %s
        """,
        (function_id,),
    )
    function = cur.fetchone()
    if not function:
        cur.close()
        return jsonify({"error": "Funcion no encontrada."}), 404

    cur.execute(
        """
        SELECT af.asiento_id, af.tiquete_id, t.codigo AS ticket_code,
               a.fila, a.columna,
               COALESCE(u.nombre, 'Usuario eliminado') AS usuario_nombre,
               COALESCE(u.email, 'Sin correo') AS usuario_email
        FROM asientos_funcion af
        JOIN asientos a ON a.id = af.asiento_id
        JOIN tiquetes t ON t.id = af.tiquete_id
        LEFT JOIN usuarios u ON u.id = t.usuario_id
        WHERE af.funcion_id = %s AND t.estado = 'activo'
        ORDER BY a.fila, a.columna
        """,
        (function_id,),
    )
    seats = cur.fetchall()
    cur.close()

    if function.get("fecha"):
        function["fecha"] = str(function["fecha"])
    if function.get("hora"):
        function["hora"] = str(function["hora"])[:5]

    for seat in seats:
        seat["label"] = f"{seat['fila']}{seat['columna']}"

    return jsonify({"funcion": function, "asientos": seats})


@admin_bp.route("/api/funciones/<int:function_id>/liberar-asientos", methods=["POST"])
@admin_required
def release_function_seats(function_id):
    data = request.get_json(silent=True) or {}
    seat_ids = normalize_positive_ids(data.get("seat_ids", []))
    if not seat_ids:
        return jsonify({"error": "Selecciona al menos un asiento ocupado."}), 400

    cur = mysql.connection.cursor(dictionary=True)

    try:
        cur.execute(
            """
            SELECT f.id, f.fecha, f.hora, p.titulo, s.nombre AS sede_nombre, c.nombre AS ciudad_nombre
            FROM funciones f
            JOIN peliculas p ON p.id = f.pelicula_id
            JOIN sedes s ON s.id = f.sede_id
            JOIN ciudades c ON c.id = s.ciudad_id
            WHERE f.id = %s
            """,
            (function_id,),
        )
        function = cur.fetchone()
        if not function:
            cur.close()
            return jsonify({"error": "Funcion no encontrada."}), 404

        placeholders = ",".join(["%s"] * len(seat_ids))
        cur.execute(
            f"""
            SELECT af.asiento_id, af.tiquete_id, t.codigo AS ticket_code, t.usuario_id,
                   a.fila, a.columna,
                   COALESCE(u.nombre, 'Usuario eliminado') AS usuario_nombre,
                   COALESCE(u.email, 'Sin correo') AS usuario_email
            FROM asientos_funcion af
            JOIN asientos a ON a.id = af.asiento_id
            JOIN tiquetes t ON t.id = af.tiquete_id
            LEFT JOIN usuarios u ON u.id = t.usuario_id
            WHERE af.funcion_id = %s
              AND af.asiento_id IN ({placeholders})
              AND t.estado = 'activo'
            ORDER BY a.fila, a.columna
            FOR UPDATE
            """,
            [function_id] + seat_ids,
        )
        occupied_rows = cur.fetchall()

        if len(occupied_rows) != len(seat_ids):
            mysql.connection.rollback()
            cur.close()
            return jsonify(
                {
                    "error": "Uno o mas asientos ya no estan ocupados. Actualiza la lista antes de continuar."
                }
            ), 409

        grouped_seats = defaultdict(list)
        released_labels = []
        impacted_tickets = []
        for row in occupied_rows:
            grouped_seats[row["tiquete_id"]].append(row["asiento_id"])
            released_labels.append(f"{row['fila']}{row['columna']}")

        for ticket_id, ticket_seat_ids in grouped_seats.items():
            result = release_ticket_seats(cur, ticket_id, ticket_seat_ids)
            impacted_tickets.append(
                {
                    "ticket_id": result["ticket_id"],
                    "ticket_code": result["ticket_code"],
                    "released_seats": result["released_seat_labels"],
                    "cancelled": result["cancelled"],
                }
            )

        log_admin_action(
            cur,
            session["user_id"],
            "release_reserved_seats",
            {
                "function_id": function_id,
                "movie_title": function["titulo"],
                "venue": f"{function['ciudad_nombre']} - {function['sede_nombre']}",
                "seat_ids": seat_ids,
                "seat_labels": released_labels,
                "impacted_tickets": impacted_tickets,
            },
        )

        mysql.connection.commit()
        cur.close()
        return jsonify(
            {
                "mensaje": "Asientos liberados correctamente.",
                "asientos_liberados": released_labels,
                "tiquetes_afectados": impacted_tickets,
            }
        )
    except (ReservationConflictError, ReservationValidationError) as exc:
        mysql.connection.rollback()
        cur.close()
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        mysql.connection.rollback()
        cur.close()
        return jsonify({"error": "No se pudieron liberar los asientos.", "detalle": str(exc)}), 500


@admin_bp.route("/api/upload-poster", methods=["POST"])
@admin_required
def upload_poster():
    file_storage = request.files.get("image")
    if not file_storage:
        return jsonify({"error": "No se recibio ningun archivo"}), 400

    try:
        poster_bytes, mime_type = read_uploaded_poster_bytes(file_storage)
        poster_data_url = build_data_url(poster_bytes, mime_type)
        resource_name = f"db-preview-{uuid4().hex}"
        append_asset_manifest(
            name=resource_name,
            path="DB_BLOB_PREVIEW",
            description="Poster procesado para persistencia en DB (BLOB)",
            ui_location="Modulo admin de peliculas (previsualizacion)",
        )
        return jsonify(
            {
                "path": poster_data_url,
                "filename": resource_name,
                "mime_type": mime_type,
                "size_bytes": len(poster_bytes),
            }
        ), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Error subiendo poster: %s", exc)
        return jsonify({"error": "No se pudo subir la imagen en este momento."}), 502
