import base64
import io
import json
import logging
import uuid

import qrcode
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from catalog import SNACK_COMBOS
from extensions import mysql
from services.email_service import send_ticket_email_async
from services.payment_service import validate_payment
from services.reservation_service import (
    ReservationConflictError,
    ReservationValidationError,
    release_ticket_seats,
)

tiquetes_bp = Blueprint("tiquetes", __name__)
COMBOS_BY_ID = {combo["id"]: combo for combo in SNACK_COMBOS}
logger = logging.getLogger(__name__)


def generate_qr_png(ticket_code):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(ticket_code)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#ff6b2c", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def qr_png_to_base64(png_bytes):
    return base64.b64encode(png_bytes).decode("utf-8")


@tiquetes_bp.route("/comprar")
def comprar():
    return redirect(url_for("peliculas.cartelera"))


@tiquetes_bp.route("/mis-tiquetes")
def mis_tiquetes():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    cur = mysql.connection.cursor(dictionary=True)
    cur.execute(
        """
        SELECT t.id, t.codigo, t.fecha_compra, t.estado, t.estado_pago, t.total,
               t.subtotal_boletas, t.subtotal_comida, t.metodo_pago,
               f.fecha, f.hora, f.sala, f.formato,
               p.titulo, p.imagen_url,
               s.nombre AS sede_nombre, c.nombre AS ciudad_nombre
        FROM tiquetes t
        JOIN funciones f ON f.id = t.funcion_id
        JOIN peliculas p ON p.id = f.pelicula_id
        JOIN sedes s ON s.id = f.sede_id
        JOIN ciudades c ON c.id = s.ciudad_id
        WHERE t.usuario_id = %s
        ORDER BY t.fecha_compra DESC
        """,
        (user_id,),
    )
    tickets = cur.fetchall()

    ticket_ids = [ticket["id"] for ticket in tickets]
    seats_by_ticket = {}
    if ticket_ids:
        placeholders = ",".join(["%s"] * len(ticket_ids))
        cur.execute(
            f"""
            SELECT dt.tiquete_id, a.fila, a.columna
            FROM detalle_tiquete dt
            JOIN asientos a ON a.id = dt.asiento_id
            WHERE dt.tiquete_id IN ({placeholders})
            ORDER BY a.fila, a.columna
            """,
            ticket_ids,
        )
        for row in cur.fetchall():
            seats_by_ticket.setdefault(row["tiquete_id"], []).append(f"{row['fila']}{row['columna']}")

    cur.close()

    for ticket in tickets:
        if ticket.get("fecha_compra"):
            ticket["fecha_compra_text"] = ticket["fecha_compra"].strftime("%d/%m/%Y %H:%M")
        else:
            ticket["fecha_compra_text"] = ""
        ticket["fecha_funcion_text"] = str(ticket["fecha"]) if ticket.get("fecha") else ""
        ticket["hora_funcion_text"] = str(ticket["hora"])[:5] if ticket.get("hora") else ""
        ticket["asientos"] = seats_by_ticket.get(ticket["id"], [])
        ticket["confirmacion_estado"] = "Confirmado" if ticket.get("estado_pago") == "aprobado" else "No confirmado"
        ticket["can_cancel"] = ticket.get("estado") not in {"cancelado", "usado"}

    return render_template("ticket_history.html", tickets=tickets)


@tiquetes_bp.route("/api/tiquetes", methods=["POST"])
def api_crear_tiquete():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Debes iniciar sesion para completar la compra."}), 401

    data = request.get_json(silent=True) or {}
    funcion_id = data.get("funcion_id")
    asientos_ids = data.get("asientos_ids", [])
    combos = data.get("combos", [])
    payment = data.get("payment", {})

    if not funcion_id or not asientos_ids:
        return jsonify({"error": "Datos incompletos"}), 400

    valid_payment, payment_error, payment_info = validate_payment(
        payment.get("method"),
        payment,
    )
    if not valid_payment:
        return jsonify({"error": payment_error}), 400

    extras_normalizados = []
    subtotal_comida = 0
    for combo in combos:
        combo_id = combo.get("id")
        qty = int(combo.get("qty", 0) or 0)
        catalog_item = COMBOS_BY_ID.get(combo_id)
        if not catalog_item or qty <= 0:
            continue
        total_linea = catalog_item["price"] * qty
        subtotal_comida += total_linea
        extras_normalizados.append(
            {
                "id": combo_id,
                "name": catalog_item["name"],
                "qty": qty,
                "price": catalog_item["price"],
                "total": total_linea,
            }
        )

    cur = mysql.connection.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT f.precio, p.titulo
            FROM funciones f
            JOIN peliculas p ON p.id = f.pelicula_id
            WHERE f.id = %s AND f.estado = 'disponible'
            """,
            (funcion_id,),
        )
        function_info = cur.fetchone()
        if not function_info:
            cur.close()
            return jsonify({"error": "Funcion no disponible"}), 400

        cur.execute(
            "SELECT email, nombre FROM usuarios WHERE id = %s",
            (user_id,),
        )
        user_info = cur.fetchone()
        if not user_info:
            cur.close()
            return jsonify({"error": "Usuario no encontrado"}), 400

        placeholders = ",".join(["%s"] * len(asientos_ids))
        cur.execute(
            f"""
            SELECT COUNT(*) AS ocupados
            FROM asientos_funcion
            WHERE funcion_id = %s AND asiento_id IN ({placeholders})
            """,
            [funcion_id] + asientos_ids,
        )
        if cur.fetchone()["ocupados"] > 0:
            cur.close()
            return jsonify({"error": "Uno o mas asientos ya estan ocupados"}), 409

        subtotal_boletas = float(function_info["precio"]) * len(asientos_ids)
        total = subtotal_boletas + subtotal_comida
        ticket_code = "TK-" + str(uuid.uuid4()).upper()[:12]
        payment_snapshot = json.dumps(payment_info)
        extras_snapshot = json.dumps(extras_normalizados)

        cur.execute(
            """
            INSERT INTO tiquetes (
                codigo, usuario_id, funcion_id, subtotal_boletas, subtotal_comida,
                metodo_pago, referencia_pago, payment_snapshot_json, extras_json, total,
                estado_pago, pago_simulado, estado
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'aprobado', %s, 'activo')
            """,
            (
                str(ticket_code),
                int(user_id),
                int(funcion_id),
                float(subtotal_boletas),
                float(subtotal_comida),
                str(payment_info.get("method", "Tarjeta")),
                str(payment_info.get("reference", "REF-SIM")),
                str(payment_snapshot),
                str(extras_snapshot),
                float(total),
                int(bool(payment_info.get("simulation", True))),
            ),
        )
        ticket_id = cur.lastrowid

        for seat_id in asientos_ids:
            cur.execute(
                """
                INSERT INTO detalle_tiquete (tiquete_id, asiento_id, precio_unitario)
                VALUES (%s, %s, %s)
                """,
                (ticket_id, seat_id, function_info["precio"]),
            )
            cur.execute(
                """
                INSERT INTO asientos_funcion (funcion_id, asiento_id, tiquete_id)
                VALUES (%s, %s, %s)
                """,
                (funcion_id, seat_id, ticket_id),
            )

        qr_png = generate_qr_png(ticket_code)
        qr_base64 = qr_png_to_base64(qr_png)
        cur.execute(
            """
            INSERT INTO qr_tickets (tiquete_id, codigo_qr)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                codigo_qr = VALUES(codigo_qr),
                fecha_generacion = CURRENT_TIMESTAMP
            """,
            (ticket_id, qr_base64),
        )

        # 1. Primero aseguramos la compra en la base de datos
        mysql.connection.commit()

        # 2. Intentamos encolar el correo sin bloquear la respuesta
        email_sent = False
        email_error = None
        email_message = "La compra fue exitosa."

        try:
            ticket_url = url_for("tiquetes.ver_tiquete", codigo=ticket_code, _external=True)
            mail_status, email_error = send_ticket_email_async(
                user_info["nombre"],
                user_info["email"],
                ticket_url,
                ticket_code,
                qr_png,
            )
            email_sent = mail_status in {"sent", "queued"}
            if mail_status == "sent":
                email_message = "Te enviamos el tiquete por correo. Si no lo ves, revisa la carpeta de spam."
            elif mail_status == "queued":
                email_message = "Te enviaremos el tiquete por correo. Si no lo ves, revisa la carpeta de spam."
            else:
                email_message = "La compra fue exitosa, pero el correo no se pudo enviar en este momento."
        except Exception as e:
            email_sent = False
            email_error = f"Error SMTP: {str(e)}"
            email_message = "La compra fue exitosa, pero el correo no se pudo enviar en este momento."
            logger.warning("No se pudo encolar el email del tiquete %s: %s", ticket_code, e)

        cur.close()

        return jsonify(
            {
                "tiquete_id": ticket_id,
                "codigo": ticket_code,
                "total": total,
                "metodo_pago": payment_info["method"],
                "estado_pago": "aprobado",
                "pago_simulado": bool(payment_info.get("simulation", True)),
                "qr": qr_base64,
                "email_sent": email_sent,
                "email_error": email_error,
                "email_message": email_message,
            }
        ), 201

    except Exception as exc:
        if mysql.connection:
            mysql.connection.rollback()
        logger.exception("Error critico creando tiquete")
        return jsonify({
            "error": "Error tecnico detectado",
            "detalle": str(exc),
            "tipo": type(exc).__name__
        }), 500


@tiquetes_bp.route("/tiquete/<codigo>")
def ver_tiquete(codigo):
    cur = mysql.connection.cursor(dictionary=True)
    cur.execute(
        """
        SELECT t.*, f.fecha, f.hora, f.sala, f.formato,
               s.nombre AS sede_nombre, c.nombre AS ciudad_nombre,
               p.titulo, p.imagen_url, u.nombre AS nombre_cliente
        FROM tiquetes t
        JOIN funciones f ON f.id = t.funcion_id
        JOIN sedes s ON s.id = f.sede_id
        JOIN ciudades c ON c.id = s.ciudad_id
        JOIN peliculas p ON p.id = f.pelicula_id
        LEFT JOIN usuarios u ON u.id = t.usuario_id
        WHERE t.codigo = %s
        """,
        (codigo,),
    )
    ticket = cur.fetchone()
    if not ticket:
        cur.close()
        return "Tiquete no encontrado", 404

    cur.execute(
        """
        SELECT a.fila, a.columna, a.numero
        FROM detalle_tiquete dt
        JOIN asientos a ON a.id = dt.asiento_id
        WHERE dt.tiquete_id = %s
        ORDER BY a.fila, a.columna
        """,
        (ticket["id"],),
    )
    seats = cur.fetchall()

    cur.execute("SELECT codigo_qr FROM qr_tickets WHERE tiquete_id = %s ORDER BY id DESC LIMIT 1", (ticket["id"],))
    qr_row = cur.fetchone()
    cur.close()

    extras = []
    if ticket.get("extras_json"):
        try:
            extras = json.loads(ticket["extras_json"])
        except json.JSONDecodeError:
            extras = []

    if ticket.get("fecha"):
        ticket["fecha"] = str(ticket["fecha"])
    if ticket.get("hora"):
        ticket["hora"] = str(ticket["hora"])[:5]

    qr_base64 = qr_row["codigo_qr"] if qr_row else qr_png_to_base64(generate_qr_png(codigo))
    can_cancel = (
        session.get("user_rol") == "cliente"
        and session.get("user_id") == ticket.get("usuario_id")
        and ticket.get("estado") == "activo"
    )
    return render_template(
        "tiquete.html",
        tiquete=ticket,
        asientos=seats,
        extras=extras,
        qr=qr_base64,
        can_cancel=can_cancel,
    )


@tiquetes_bp.route("/api/tiquetes/<codigo>/cancelar", methods=["POST"])
def api_cancelar_tiquete(codigo):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Debes iniciar sesion para cancelar la reserva."}), 401

    if session.get("user_rol") != "cliente":
        return jsonify({"error": "Solo los clientes pueden cancelar sus reservas."}), 403

    cur = mysql.connection.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT id, codigo, usuario_id
            FROM tiquetes
            WHERE codigo = %s
            """,
            (codigo,),
        )
        ticket = cur.fetchone()
        if not ticket:
            cur.close()
            return jsonify({"error": "Tiquete no encontrado."}), 404

        if ticket.get("usuario_id") != user_id:
            cur.close()
            return jsonify({"error": "No puedes cancelar una reserva de otro usuario."}), 403

        result = release_ticket_seats(cur, ticket["id"])
        mysql.connection.commit()
        cur.close()

        return jsonify(
            {
                "mensaje": "Reserva cancelada. Los asientos ya quedaron disponibles nuevamente.",
                "codigo": codigo,
                "asientos_liberados": result["released_seat_labels"],
                "reserva_cancelada": result["cancelled"],
            }
        ), 200
    except (ReservationConflictError, ReservationValidationError) as exc:
        mysql.connection.rollback()
        cur.close()
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        mysql.connection.rollback()
        cur.close()
        return jsonify({"error": "No se pudo cancelar la reserva.", "detalle": str(exc)}), 500


@tiquetes_bp.route("/validar")
def validar_page():
    return render_template("validar.html")


@tiquetes_bp.route("/api/tiquetes/validar", methods=["POST"])
def api_validar():
    data = request.get_json()
    codigo = data.get("codigo", "").strip()
    cur = mysql.connection.cursor(dictionary=True)
    cur.execute(
        """
        SELECT t.*, p.titulo, f.fecha, f.hora, f.sala, s.nombre AS sede_nombre, c.nombre AS ciudad_nombre
        FROM tiquetes t
        JOIN funciones f ON f.id = t.funcion_id
        JOIN peliculas p ON p.id = f.pelicula_id
        JOIN sedes s ON s.id = f.sede_id
        JOIN ciudades c ON c.id = s.ciudad_id
        WHERE t.codigo = %s
        """,
        (codigo,),
    )
    ticket = cur.fetchone()

    if not ticket:
        cur.close()
        return jsonify({"valido": False, "mensaje": "Tiquete invalido - no existe"}), 200

    if ticket["estado"] == "usado":
        cur.close()
        return jsonify({"valido": False, "mensaje": "Tiquete ya fue usado"}), 200

    if ticket["estado"] == "cancelado":
        cur.close()
        return jsonify({"valido": False, "mensaje": "Tiquete cancelado"}), 200

    cur.execute("UPDATE tiquetes SET estado = 'usado' WHERE id = %s", (ticket["id"],))
    mysql.connection.commit()
    cur.close()

    return jsonify(
        {
            "valido": True,
            "mensaje": "Tiquete valido. Acceso permitido",
            "pelicula": ticket["titulo"],
            "sala": ticket["sala"],
            "sede": ticket["sede_nombre"],
            "ciudad": ticket["ciudad_nombre"],
        }
    ), 200
