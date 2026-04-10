from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from catalog import PAYMENT_METHODS, SNACK_COMBOS
from extensions import mysql

funciones_bp = Blueprint("funciones", __name__)


@funciones_bp.route("/funcion/<int:id>")
def seleccionar_asientos(id):
    cur = mysql.connection.cursor(dictionary=True)
    cur.execute(
        """
        SELECT f.*, p.titulo, p.duracion, p.clasificacion, p.imagen_url,
               s.nombre AS sede_nombre, c.nombre AS ciudad_nombre
        FROM funciones f
        JOIN peliculas p ON p.id = f.pelicula_id
        JOIN sedes s ON s.id = f.sede_id
        JOIN ciudades c ON c.id = s.ciudad_id
        WHERE f.id = %s
        """,
        (id,),
    )
    funcion = cur.fetchone()
    cur.close()

    if not funcion:
        return redirect(url_for("peliculas.cartelera"))

    return render_template(
        "funcion.html",
        funcion=funcion,
        combos_catalogo=SNACK_COMBOS,
        payment_methods=PAYMENT_METHODS,
    )


@funciones_bp.route("/api/funciones/<int:id>/asientos")
def api_asientos_funcion(id):
    cur = mysql.connection.cursor(dictionary=True)
    cur.execute(
        """
        SELECT a.id, a.numero, a.fila, a.columna, a.estado,
               CASE WHEN af.id IS NOT NULL THEN 'ocupado' ELSE 'disponible' END AS estado_funcion
        FROM asientos a
        LEFT JOIN asientos_funcion af ON af.asiento_id = a.id AND af.funcion_id = %s
        WHERE a.estado = 'activo'
        ORDER BY a.fila, a.columna
        """,
        (id,),
    )
    asientos = cur.fetchall()
    cur.close()
    return jsonify(asientos)


@funciones_bp.route("/api/funciones")
def api_funciones():
    selected_city_id = session.get("selected_city_id")
    selected_sede_id = session.get("selected_sede_id")

    filters = [
        "f.estado = 'disponible'",
        "f.fecha >= CURDATE()",
    ]
    params = []

    if selected_city_id:
        filters.append("c.id = %s")
        params.append(selected_city_id)

    if selected_sede_id:
        filters.append("s.id = %s")
        params.append(selected_sede_id)

    cur = mysql.connection.cursor(dictionary=True)
    cur.execute(
        f"""
        SELECT f.*, p.titulo, s.nombre AS sede_nombre, c.nombre AS ciudad_nombre,
               COUNT(af.id) AS asientos_ocupados,
               (150 - COUNT(af.id)) AS asientos_disponibles
        FROM funciones f
        JOIN peliculas p ON p.id = f.pelicula_id
        JOIN sedes s ON s.id = f.sede_id
        JOIN ciudades c ON c.id = s.ciudad_id
        LEFT JOIN asientos_funcion af ON af.funcion_id = f.id
        WHERE {' AND '.join(filters)}
        GROUP BY f.id
        ORDER BY f.fecha, f.hora
        """,
        params,
    )
    funciones = cur.fetchall()
    cur.close()

    for funcion in funciones:
        if funcion.get("fecha"):
            funcion["fecha"] = str(funcion["fecha"])
        if funcion.get("hora"):
            funcion["hora"] = str(funcion["hora"])[:5]

    return jsonify(funciones)


@funciones_bp.route("/api/funciones", methods=["POST"])
def api_crear_funcion():
    if session.get("user_rol") != "admin":
        return jsonify({"error": "No autorizado"}), 403

    data = request.get_json()
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            """
            INSERT INTO funciones (pelicula_id, sede_id, fecha, hora, sala, formato, precio, estado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'disponible')
            """,
            (
                data["pelicula_id"],
                data["sede_id"],
                data["fecha"],
                data["hora"],
                data["sala"],
                data["formato"],
                data["precio"],
            ),
        )
        mysql.connection.commit()
        new_id = cur.lastrowid
        cur.close()
        return jsonify({"id": new_id, "mensaje": "Funcion creada"}), 201
    except Exception as exc:
        mysql.connection.rollback()
        return jsonify({"error": "Traslape de horario en sala", "detalle": str(exc)}), 400


@funciones_bp.route("/api/funciones/<int:id>", methods=["DELETE"])
def api_cancelar_funcion(id):
    if session.get("user_rol") != "admin":
        return jsonify({"error": "No autorizado"}), 403

    cur = mysql.connection.cursor(dictionary=True)
    cur.execute("UPDATE funciones SET estado = 'cancelada' WHERE id = %s", (id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({"mensaje": "Funcion cancelada"})
