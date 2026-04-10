from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from catalog import PROJECTION_FORMATS
from extensions import mysql

peliculas_bp = Blueprint("peliculas", __name__)


def get_selected_location():
    return session.get("selected_city_id"), session.get("selected_sede_id")


@peliculas_bp.route("/cartelera")
def cartelera():
    selected_city_id, selected_sede_id = get_selected_location()
    selected_category = request.args.get("categoria", "Todas").strip() or "Todas"
    selected_genero = request.args.get("genero", "Todos").strip() or "Todos"
    selected_format = request.args.get("formato", "Todos").strip() or "Todos"
    selected_order = request.args.get("orden", "popularidad").strip() or "popularidad"

    function_join_filters = [
        "f.pelicula_id = p.id",
        "f.estado = 'disponible'",
        "f.fecha >= CURDATE()",
    ]
    function_join_params = []
    sede_join_filters = ["s.id = f.sede_id"]
    sede_join_params = []
    city_join_filters = ["c.id = s.ciudad_id"]
    city_join_params = []

    if selected_city_id:
        function_join_filters.append("f.sede_id IN (SELECT id FROM sedes WHERE ciudad_id = %s)")
        function_join_params.append(selected_city_id)

    if selected_sede_id:
        function_join_filters.append("f.sede_id = %s")
        function_join_params.append(selected_sede_id)

    if selected_format != "Todos":
        function_join_filters.append("f.formato = %s")
        function_join_params.append(selected_format)

    where_filters = ["p.estado = 'activa'"]
    where_params = []
    if selected_category != "Todas":
        where_filters.append("p.categoria = %s")
        where_params.append(selected_category)
    if selected_genero != "Todos":
        where_filters.append("p.genero = %s")
        where_params.append(selected_genero)

    order_map = {
        "popularidad": "popularidad DESC, rating_promedio DESC, p.titulo ASC",
        "alfabetico": "p.titulo ASC",
        "precio": "precio_desde ASC, p.titulo ASC",
        "reciente": "p.fecha_creacion DESC, p.titulo ASC",
    }
    order_by = order_map.get(selected_order, order_map["popularidad"])

    cur = mysql.connection.cursor(dictionary=True)
    cur.execute(
        f"""
        SELECT p.*,
               GROUP_CONCAT(DISTINCT DATE_FORMAT(f.fecha, '%%d/%%m') ORDER BY f.fecha SEPARATOR ' · ') AS fechas,
               GROUP_CONCAT(DISTINCT f.formato ORDER BY FIELD(f.formato, '2D', '3D', 'IMAX', 'VIP') SEPARATOR ', ') AS formatos,
               GROUP_CONCAT(DISTINCT s.nombre ORDER BY s.nombre SEPARATOR ' · ') AS sedes,
               MIN(f.precio) AS precio_desde,
               COUNT(DISTINCT f.id) AS num_funciones,
               COALESCE((SELECT ROUND(AVG(r.puntuacion), 1) FROM resenas r WHERE r.pelicula_id = p.id), 0) AS rating_promedio,
               (SELECT COUNT(*) FROM resenas r2 WHERE r2.pelicula_id = p.id) AS total_resenas,
               (
                   SELECT COUNT(*)
                   FROM tiquetes t
                   JOIN funciones fx ON fx.id = t.funcion_id
                   WHERE fx.pelicula_id = p.id AND t.estado != 'cancelado'
               ) AS popularidad
        FROM peliculas p
        LEFT JOIN funciones f ON {' AND '.join(function_join_filters)}
        LEFT JOIN sedes s ON {' AND '.join(sede_join_filters)}
        LEFT JOIN ciudades c ON {' AND '.join(city_join_filters)}
        WHERE {' AND '.join(where_filters)}
        GROUP BY p.id
        ORDER BY {order_by}
        """,
        function_join_params + sede_join_params + city_join_params + where_params,
    )
    peliculas = cur.fetchall()

    cur.execute(
        """
        SELECT categoria, COUNT(*) AS total
        FROM peliculas
        WHERE estado = 'activa'
        GROUP BY categoria
        ORDER BY categoria
        """
    )
    categories = cur.fetchall()

    cur.execute(
        """
        SELECT genero, COUNT(*) AS total
        FROM peliculas
        WHERE estado = 'activa' AND genero IS NOT NULL AND genero != ''
        GROUP BY genero
        ORDER BY genero
        """
    )
    genres = cur.fetchall()

    sedes = []
    if selected_city_id:
        cur.execute(
            """
            SELECT s.id, s.nombre,
                   COUNT(DISTINCT f.id) AS total_funciones
            FROM sedes s
            LEFT JOIN funciones f ON f.sede_id = s.id AND f.fecha >= CURDATE() AND f.estado = 'disponible'
            WHERE s.ciudad_id = %s
            GROUP BY s.id
            ORDER BY s.nombre
            """,
            (selected_city_id,),
        )
        sedes = cur.fetchall()

    cur.close()

    featured_movie = next((movie for movie in peliculas if movie.get("num_funciones")), peliculas[0] if peliculas else None)
    total_funciones = sum(movie.get("num_funciones", 0) or 0 for movie in peliculas)

    return render_template(
        "index.html",
        peliculas=peliculas,
        categories=categories,
        genres=genres,
        sedes=sedes,
        featured_movie=featured_movie,
        selected_category=selected_category,
        selected_genero=selected_genero,
        selected_format=selected_format,
        selected_order=selected_order,
        format_options=PROJECTION_FORMATS,
        total_funciones=total_funciones,
        selected_sede_id=selected_sede_id,
    )


@peliculas_bp.route("/pelicula/<int:id>")
def detalle(id):
    selected_city_id, selected_sede_id = get_selected_location()
    selected_format = request.args.get("formato", "Todos").strip() or "Todos"

    cur = mysql.connection.cursor(dictionary=True)
    cur.execute("SELECT * FROM peliculas WHERE id = %s", (id,))
    pelicula = cur.fetchone()
    if not pelicula:
        cur.close()
        return redirect(url_for("peliculas.cartelera"))

    cur.execute(
        """
        SELECT ROUND(AVG(puntuacion), 1) AS promedio, COUNT(*) AS total
        FROM resenas
        WHERE pelicula_id = %s
        """,
        (id,),
    )
    rating = cur.fetchone()

    cur.execute(
        """
        SELECT r.*, u.nombre AS usuario_nombre
        FROM resenas r
        JOIN usuarios u ON u.id = r.usuario_id
        WHERE r.pelicula_id = %s
        ORDER BY r.fecha DESC
        LIMIT 8
        """,
        (id,),
    )
    reviews = cur.fetchall()

    user_review = None
    if session.get("user_id"):
        cur.execute(
            "SELECT comentario, puntuacion FROM resenas WHERE pelicula_id = %s AND usuario_id = %s",
            (id, session["user_id"]),
        )
        user_review = cur.fetchone()

    cur.execute(
        """
        SELECT DISTINCT f.formato
        FROM funciones f
        JOIN sedes s ON s.id = f.sede_id
        JOIN ciudades c ON c.id = s.ciudad_id
        WHERE f.pelicula_id = %s
          AND f.estado = 'disponible'
          AND f.fecha >= CURDATE()
          AND c.id = %s
        ORDER BY FIELD(f.formato, '2D', '3D', 'IMAX', 'VIP')
        """,
        (id, selected_city_id),
    )
    available_formats = [row["formato"] for row in cur.fetchall()]

    cur.execute(
        """
        SELECT s.id, s.nombre, COUNT(*) AS total_funciones
        FROM funciones f
        JOIN sedes s ON s.id = f.sede_id
        JOIN ciudades c ON c.id = s.ciudad_id
        WHERE f.pelicula_id = %s
          AND f.estado = 'disponible'
          AND f.fecha >= CURDATE()
          AND c.id = %s
        GROUP BY s.id
        ORDER BY s.nombre
        """,
        (id, selected_city_id),
    )
    available_sedes = cur.fetchall()

    filters = [
        "f.pelicula_id = %s",
        "f.estado = 'disponible'",
        "f.fecha >= CURDATE()",
        "c.id = %s",
    ]
    params = [id, selected_city_id]

    if selected_sede_id:
        filters.append("s.id = %s")
        params.append(selected_sede_id)
    if selected_format != "Todos":
        filters.append("f.formato = %s")
        params.append(selected_format)

    cur.execute(
        f"""
        SELECT f.*, s.nombre AS sede_nombre, c.nombre AS ciudad_nombre,
               COUNT(af.id) AS asientos_ocupados,
               (150 - COUNT(af.id)) AS asientos_disponibles
        FROM funciones f
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

    return render_template(
        "pelicula.html",
        pelicula=pelicula,
        funciones=funciones,
        available_formats=available_formats,
        available_sedes=available_sedes,
        selected_format=selected_format,
        selected_sede_id=selected_sede_id,
        rating=rating,
        reviews=reviews,
        user_review=user_review,
    )


@peliculas_bp.route("/pelicula/<int:id>/resenas", methods=["POST"])
def guardar_resena(id):
    if not session.get("user_id"):
        flash("Debes iniciar sesion para publicar una resena.", "error")
        return redirect(url_for("auth.login"))
    if session.get("user_rol") != "cliente":
        flash("Solo los clientes pueden publicar resenas.", "error")
        return redirect(url_for("peliculas.detalle", id=id))

    try:
        puntuacion = round(float(request.form.get("puntuacion", "0")), 1)
    except ValueError:
        flash("La puntuacion debe ser numerica.", "error")
        return redirect(url_for("peliculas.detalle", id=id))

    if puntuacion < 1 or puntuacion > 10:
        flash("La puntuacion debe estar entre 1.0 y 10.0.", "error")
        return redirect(url_for("peliculas.detalle", id=id))

    comentario = request.form.get("comentario", "").strip()

    cur = mysql.connection.cursor(dictionary=True)
    cur.execute(
        """
        INSERT INTO resenas (usuario_id, pelicula_id, comentario, puntuacion)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE comentario = VALUES(comentario), puntuacion = VALUES(puntuacion), fecha = NOW()
        """,
        (session["user_id"], id, comentario, puntuacion),
    )
    mysql.connection.commit()
    cur.close()
    flash("Tu resena fue guardada.", "success")
    return redirect(url_for("peliculas.detalle", id=id))


@peliculas_bp.route("/api/peliculas")
def api_peliculas():
    cur = mysql.connection.cursor(dictionary=True)
    cur.execute("SELECT * FROM peliculas WHERE estado = 'activa' ORDER BY titulo")
    peliculas = cur.fetchall()
    cur.close()
    return jsonify(peliculas)


@peliculas_bp.route("/api/peliculas", methods=["POST"])
def api_crear_pelicula():
    if session.get("user_rol") != "admin":
        return jsonify({"error": "No autorizado"}), 403

    data = request.get_json()
    cur = mysql.connection.cursor(dictionary=True)
    cur.execute(
        """
        INSERT INTO peliculas (
            titulo, descripcion, duracion, genero, categoria,
            clasificacion, imagen_url, trailer_url
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            data["titulo"],
            data.get("descripcion"),
            data["duracion"],
            data.get("genero"),
            data.get("categoria", "Cartelera"),
            data.get("clasificacion"),
            data.get("imagen_url"),
            data.get("trailer_url"),
        ),
    )
    mysql.connection.commit()
    new_id = cur.lastrowid
    cur.close()
    return jsonify({"id": new_id, "mensaje": "Pelicula creada"}), 201


@peliculas_bp.route("/api/peliculas/<int:id>", methods=["PUT"])
def api_editar_pelicula(id):
    if session.get("user_rol") != "admin":
        return jsonify({"error": "No autorizado"}), 403

    data = request.get_json()
    cur = mysql.connection.cursor(dictionary=True)

    # Si el cliente no manda imagen_url (o manda None/vacío), conservamos
    # la que ya está guardada en la BD para no borrar imágenes subidas.
    nueva_imagen = data.get("imagen_url")
    if not nueva_imagen:
        cur.execute("SELECT imagen_url FROM peliculas WHERE id = %s", (id,))
        row = cur.fetchone()
        nueva_imagen = row["imagen_url"] if row else None

    cur.execute(
        """
        UPDATE peliculas
        SET titulo = %s,
            descripcion = %s,
            duracion = %s,
            genero = %s,
            categoria = %s,
            clasificacion = %s,
            imagen_url = %s,
            trailer_url = %s,
            estado = %s
        WHERE id = %s
        """,
        (
            data["titulo"],
            data.get("descripcion"),
            data["duracion"],
            data.get("genero"),
            data.get("categoria", "Cartelera"),
            data.get("clasificacion"),
            nueva_imagen,
            data.get("trailer_url"),
            data.get("estado", "activa"),
            id,
        ),
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({"mensaje": "Pelicula actualizada"})


@peliculas_bp.route("/api/peliculas/<int:id>", methods=["DELETE"])
def api_eliminar_pelicula(id):
    if session.get("user_rol") != "admin":
        return jsonify({"error": "No autorizado"}), 403

    cur = mysql.connection.cursor(dictionary=True)
    cur.execute("UPDATE peliculas SET estado = 'inactiva' WHERE id = %s", (id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({"mensaje": "Pelicula eliminada"})