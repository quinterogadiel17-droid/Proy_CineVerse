import json


class ReservationError(Exception):
    pass


class ReservationConflictError(ReservationError):
    pass


class ReservationValidationError(ReservationError):
    pass


def normalize_positive_ids(values):
    normalized = []
    seen = set()

    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue

        if number <= 0 or number in seen:
            continue

        seen.add(number)
        normalized.append(number)

    return normalized


def log_admin_action(cursor, admin_id, action_type, details):
    cursor.execute(
        """
        INSERT INTO admin_action_logs (admin_id, action_type, details_json)
        VALUES (%s, %s, %s)
        """,
        (admin_id, action_type, json.dumps(details, ensure_ascii=True, default=str)),
    )


def _fetch_ticket_for_update(cursor, ticket_id):
    cursor.execute(
        """
        SELECT id, codigo, usuario_id, funcion_id, estado,
               COALESCE(subtotal_boletas, 0) AS subtotal_boletas,
               COALESCE(subtotal_comida, 0) AS subtotal_comida
        FROM tiquetes
        WHERE id = %s
        FOR UPDATE
        """,
        (ticket_id,),
    )
    return cursor.fetchone()


def _fetch_ticket_seats_for_update(cursor, ticket_id, seat_ids=None):
    filters = ""
    params = [ticket_id]

    if seat_ids:
        placeholders = ",".join(["%s"] * len(seat_ids))
        filters = f" AND dt.asiento_id IN ({placeholders})"
        params.extend(seat_ids)

    cursor.execute(
        f"""
        SELECT dt.asiento_id, dt.precio_unitario, a.fila, a.columna
        FROM detalle_tiquete dt
        JOIN asientos a ON a.id = dt.asiento_id
        WHERE dt.tiquete_id = %s {filters}
        ORDER BY a.fila, a.columna
        FOR UPDATE
        """,
        params,
    )
    return cursor.fetchall()


def _fetch_ticket_remaining_totals(cursor, ticket_id):
    cursor.execute(
        """
        SELECT COUNT(*) AS total_asientos,
               COALESCE(SUM(precio_unitario), 0) AS subtotal_boletas
        FROM detalle_tiquete
        WHERE tiquete_id = %s
        """,
        (ticket_id,),
    )
    return cursor.fetchone()


def release_ticket_seats(cursor, ticket_id, seat_ids=None):
    ticket = _fetch_ticket_for_update(cursor, ticket_id)
    if not ticket:
        raise ReservationValidationError("La reserva indicada no existe.")

    if ticket["estado"] == "cancelado":
        raise ReservationConflictError("La reserva ya fue cancelada.")

    if ticket["estado"] == "usado":
        raise ReservationConflictError("No se pueden liberar asientos de un tiquete usado.")

    requested_seat_ids = normalize_positive_ids(seat_ids) if seat_ids is not None else None
    if seat_ids is not None and not requested_seat_ids:
        raise ReservationValidationError("Debes indicar al menos un asiento valido.")

    seat_rows = _fetch_ticket_seats_for_update(cursor, ticket_id, requested_seat_ids)
    if not seat_rows:
        raise ReservationConflictError("Los asientos seleccionados ya no estan reservados.")

    if requested_seat_ids and len(seat_rows) != len(requested_seat_ids):
        raise ReservationConflictError(
            "Uno o mas asientos ya fueron liberados o no pertenecen a esta reserva."
        )

    release_ids = [row["asiento_id"] for row in seat_rows]
    placeholders = ",".join(["%s"] * len(release_ids))
    delete_params = [ticket_id] + release_ids

    cursor.execute(
        f"""
        DELETE FROM asientos_funcion
        WHERE tiquete_id = %s AND asiento_id IN ({placeholders})
        """,
        delete_params,
    )
    cursor.execute(
        f"""
        DELETE FROM detalle_tiquete
        WHERE tiquete_id = %s AND asiento_id IN ({placeholders})
        """,
        delete_params,
    )

    remaining = _fetch_ticket_remaining_totals(cursor, ticket_id)
    remaining_seat_count = int(remaining["total_asientos"])
    remaining_boletas = float(remaining["subtotal_boletas"])
    subtotal_comida = float(ticket["subtotal_comida"] or 0)
    released_labels = [f"{row['fila']}{row['columna']}" for row in seat_rows]

    if remaining_seat_count == 0:
        cursor.execute(
            """
            UPDATE tiquetes
            SET subtotal_boletas = 0.00,
                subtotal_comida = 0.00,
                extras_json = %s,
                total = 0.00,
                estado = 'cancelado'
            WHERE id = %s
            """,
            ("[]", ticket_id),
        )
        current_total = 0.0
        cancelled = True
    else:
        current_total = remaining_boletas + subtotal_comida
        cursor.execute(
            """
            UPDATE tiquetes
            SET subtotal_boletas = %s,
                total = %s,
                estado = 'activo'
            WHERE id = %s
            """,
            (remaining_boletas, current_total, ticket_id),
        )
        cancelled = False

    return {
        "ticket_id": ticket["id"],
        "ticket_code": ticket["codigo"],
        "function_id": ticket["funcion_id"],
        "user_id": ticket["usuario_id"],
        "released_seat_ids": release_ids,
        "released_seat_labels": released_labels,
        "released_count": len(release_ids),
        "remaining_seat_count": remaining_seat_count,
        "cancelled": cancelled,
        "current_total": current_total,
    }


def delete_user_account(cursor, user_id, admin_id=None):
    cursor.execute(
        """
        SELECT id, nombre, email, rol
        FROM usuarios
        WHERE id = %s
        FOR UPDATE
        """,
        (user_id,),
    )
    user = cursor.fetchone()
    if not user:
        raise ReservationValidationError("El usuario no existe.")

    if user["rol"] == "admin":
        raise ReservationConflictError("No se pueden eliminar administradores desde esta vista.")

    cursor.execute(
        """
        SELECT id
        FROM tiquetes
        WHERE usuario_id = %s AND estado = 'activo'
        ORDER BY fecha_compra DESC
        FOR UPDATE
        """,
        (user_id,),
    )
    active_tickets = cursor.fetchall()

    cancelled_tickets = []
    released_total = 0
    for ticket in active_tickets:
        result = release_ticket_seats(cursor, ticket["id"])
        cancelled_tickets.append(result["ticket_code"])
        released_total += result["released_count"]

    cursor.execute("UPDATE tiquetes SET usuario_id = NULL WHERE usuario_id = %s", (user_id,))
    cursor.execute("DELETE FROM resenas WHERE usuario_id = %s", (user_id,))
    cursor.execute("DELETE FROM usuarios WHERE id = %s", (user_id,))

    if admin_id:
        log_admin_action(
            cursor,
            admin_id,
            "delete_user",
            {
                "user_id": user["id"],
                "user_name": user["nombre"],
                "user_email": user["email"],
                "cancelled_tickets": cancelled_tickets,
                "released_seats": released_total,
            },
        )

    return {
        "user_id": user["id"],
        "user_name": user["nombre"],
        "user_email": user["email"],
        "cancelled_tickets": cancelled_tickets,
        "released_seats": released_total,
    }
