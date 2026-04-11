import logging

import mysql.connector as mysql_connector
from werkzeug.security import generate_password_hash

from catalog import CITY_SEED, DEFAULT_CITY_NAME, DEFAULT_SEDE_NAME, MOVIE_SEED
from config import Config
from services.asset_service import ensure_asset_directories, sync_asset_manifest

logger = logging.getLogger(__name__)


def ensure_column(cursor, db_name, table_name, column_name, definition):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (db_name, table_name, column_name),
    )
    if cursor.fetchone()[0] == 0:
        cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {definition}")


def ensure_index(cursor, table_name, index_name, columns, unique=False):
    cursor.execute(f"SHOW INDEX FROM `{table_name}` WHERE Key_name = %s", (index_name,))
    rows = cursor.fetchall()
    existing_columns = [row[4] for row in sorted(rows, key=lambda item: item[3])]

    if existing_columns and existing_columns != columns:
        cursor.execute(f"ALTER TABLE `{table_name}` DROP INDEX `{index_name}`")
        rows = []

    if not rows:
        unique_sql = "UNIQUE " if unique else ""
        column_sql = ", ".join(f"`{column}`" for column in columns)
        cursor.execute(
            f"ALTER TABLE `{table_name}` ADD {unique_sql}INDEX `{index_name}` ({column_sql})"
        )


def ensure_foreign_key(cursor, table_name, fk_name, column_name, target_table, target_column):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = %s AND TABLE_NAME = %s
          AND CONSTRAINT_NAME = %s AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        """,
        (Config.MYSQL_DB, table_name, fk_name),
    )
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            f"""
            ALTER TABLE `{table_name}`
            ADD CONSTRAINT `{fk_name}`
            FOREIGN KEY (`{column_name}`) REFERENCES `{target_table}`(`{target_column}`)
            """
        )


def build_asset_manifest_entries(movie_rows=None):
    entries = []
    seen = set()
    rows = movie_rows if movie_rows is not None else MOVIE_SEED

    for movie in rows:
        if isinstance(movie, dict):
            title = movie.get("titulo")
            image_path = movie.get("imagen_url")
        else:
            title = movie[0] if len(movie) > 0 else None
            image_path = movie[1] if len(movie) > 1 else None

        if not title or not image_path:
            continue

        signature = (title, image_path)
        if signature in seen:
            continue
        seen.add(signature)

        entries.append(
            {
                "name": image_path.split("/")[-1],
                "path": image_path,
                "description": f"Poster principal de {title}",
                "ui_location": "Cartelera, detalle de pelicula, panel admin y ticket",
            }
        )

    return entries


def seed_locations(cursor):
    city_ids = {}
    sede_ids = {}

    for city in CITY_SEED:
        cursor.execute("SELECT id FROM ciudades WHERE nombre = %s LIMIT 1", (city["nombre"],))
        row = cursor.fetchone()
        if row:
            city_id = row[0]
        else:
            cursor.execute("INSERT INTO ciudades (nombre) VALUES (%s)", (city["nombre"],))
            city_id = cursor.lastrowid
        city_ids[city["nombre"]] = city_id

        for sede in city["sedes"]:
            cursor.execute(
                "SELECT id FROM sedes WHERE nombre = %s AND ciudad_id = %s LIMIT 1",
                (sede, city_id),
            )
            sede_row = cursor.fetchone()
            if sede_row:
                sede_id = sede_row[0]
            else:
                cursor.execute(
                    "INSERT INTO sedes (nombre, ciudad_id) VALUES (%s, %s)",
                    (sede, city_id),
                )
                sede_id = cursor.lastrowid
            sede_ids[(city["nombre"], sede)] = sede_id

    return city_ids, sede_ids


def seed_admin_user(cursor):
    cursor.execute(
        "SELECT id, email, contrasena FROM usuarios WHERE rol = 'admin' AND email IN (%s, %s) LIMIT 1",
        ("admin@cinecol.com", "admin@cineverse.com"),
    )
    row = cursor.fetchone()

    if row:
        cursor.execute(
            """
            UPDATE usuarios
            SET nombre = %s,
                email = %s,
                verificado = 1,
                activo = 1
            WHERE id = %s
            """,
            ("Administrador CineVerse", "admin@cinecol.com", row[0]),
        )
        if row[2] in {"", "pbkdf2:sha256:600000$admin123"}:
            cursor.execute(
                "UPDATE usuarios SET contrasena = %s WHERE id = %s",
                (generate_password_hash("admin123"), row[0]),
            )
        return

    cursor.execute(
        """
        INSERT INTO usuarios (nombre, email, contrasena, rol, verificado, activo)
        VALUES (%s, %s, %s, 'admin', 1, 1)
        """,
        ("Administrador CineVerse", "admin@cinecol.com", generate_password_hash("admin123")),
    )


def seed_movies(cursor, sede_ids):
    for movie in MOVIE_SEED:
        cursor.execute("SELECT id FROM peliculas WHERE titulo = %s LIMIT 1", (movie["titulo"],))
        row = cursor.fetchone()

        if row:
            movie_id = row[0]
            cursor.execute("SELECT imagen_url FROM peliculas WHERE id = %s", (movie_id,))
            current_image = (cursor.fetchone() or [None])[0] or ""
            has_custom_image = current_image.startswith("/static/uploads/")
            new_image_url = current_image if has_custom_image else movie["imagen_url"]

            cursor.execute(
                """
                UPDATE peliculas
                SET descripcion = %s,
                    duracion = %s,
                    genero = %s,
                    categoria = %s,
                    clasificacion = %s,
                    imagen_url = %s,
                    trailer_url = %s,
                    estado = 'activa'
                WHERE id = %s
                """,
                (
                    movie["descripcion"],
                    movie["duracion"],
                    movie["genero"],
                    movie["categoria"],
                    movie["clasificacion"],
                    new_image_url,
                    movie["trailer_url"],
                    movie_id,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO peliculas (
                    titulo, descripcion, duracion, genero, categoria,
                    clasificacion, imagen_url, trailer_url, estado
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'activa')
                """,
                (
                    movie["titulo"],
                    movie["descripcion"],
                    movie["duracion"],
                    movie["genero"],
                    movie["categoria"],
                    movie["clasificacion"],
                    movie["imagen_url"],
                    movie["trailer_url"],
                ),
            )
            movie_id = cursor.lastrowid

        for show in movie["funciones"]:
            sede_id = sede_ids.get((show["city"], show["venue"]))
            if not sede_id:
                continue

            cursor.execute(
                """
                SELECT id
                FROM funciones
                WHERE pelicula_id = %s
                  AND fecha = DATE_ADD(CURDATE(), INTERVAL %s DAY)
                  AND hora = %s
                  AND sala = %s
                  AND sede_id = %s
                LIMIT 1
                """,
                (
                    movie_id,
                    show["offset_days"],
                    show["time"],
                    show["room"],
                    sede_id,
                ),
            )
            function_row = cursor.fetchone()

            if function_row:
                cursor.execute(
                    """
                    UPDATE funciones
                    SET formato = %s, precio = %s, estado = 'disponible'
                    WHERE id = %s
                    """,
                    (show["format"], show["price"], function_row[0]),
                )
                continue

            cursor.execute(
                """
                SELECT id
                FROM funciones
                WHERE fecha = DATE_ADD(CURDATE(), INTERVAL %s DAY)
                  AND hora = %s
                  AND sala = %s
                  AND sede_id = %s
                LIMIT 1
                """,
                (
                    show["offset_days"],
                    show["time"],
                    show["room"],
                    sede_id,
                ),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    """
                    INSERT INTO funciones (
                        pelicula_id, sede_id, fecha, hora, sala, formato, precio, estado
                    )
                    VALUES (
                        %s, %s, DATE_ADD(CURDATE(), INTERVAL %s DAY), %s, %s, %s, %s, 'disponible'
                    )
                    """,
                    (
                        movie_id,
                        sede_id,
                        show["offset_days"],
                        show["time"],
                        show["room"],
                        show["format"],
                        show["price"],
                    ),
                )


def repair_legacy_catalog(cursor, sede_ids):
    cursor.execute(
        """
        UPDATE peliculas
        SET categoria = 'Cartelera'
        WHERE categoria IS NULL OR categoria = ''
        """
    )
    cursor.execute(
        """
        UPDATE funciones
        SET formato = '2D'
        WHERE formato IS NULL OR formato = ''
        """
    )

    default_sede_id = sede_ids.get((DEFAULT_CITY_NAME, DEFAULT_SEDE_NAME))
    candidate_sede_ids = []
    if default_sede_id:
        candidate_sede_ids.append(default_sede_id)
    candidate_sede_ids.extend(
        sorted(sede_id for sede_id in set(sede_ids.values()) if sede_id != default_sede_id)
    )

    if default_sede_id:
        cursor.execute(
            """
            UPDATE funciones f
            LEFT JOIN sedes s ON s.id = f.sede_id
            SET f.sede_id = %s
            WHERE f.sede_id IS NOT NULL AND s.id IS NULL
            """,
            (default_sede_id,),
        )

    if not candidate_sede_ids:
        return

    cursor.execute(
        """
        SELECT id, sala, fecha, hora
        FROM funciones
        WHERE sede_id IS NULL
        ORDER BY fecha, hora, id
        """
    )
    legacy_functions = cursor.fetchall()

    for function_id, sala, fecha, hora in legacy_functions:
        assigned_sede_id = None
        for candidate_sede_id in candidate_sede_ids:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM funciones
                WHERE sede_id = %s AND sala = %s AND fecha = %s AND hora = %s AND id <> %s
                """,
                (candidate_sede_id, sala, fecha, hora, function_id),
            )
            if cursor.fetchone()[0] == 0:
                assigned_sede_id = candidate_sede_id
                break

        if assigned_sede_id is None:
            assigned_sede_id = candidate_sede_ids[0]

        cursor.execute(
            "UPDATE funciones SET sede_id = %s WHERE id = %s",
            (assigned_sede_id, function_id),
        )


def bootstrap_database():
    ensure_asset_directories()

    db_name = Config.MYSQL_DB
    connection = mysql_connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        port=int(Config.MYSQL_PORT),
        ssl_ca=Config.MYSQL_SSL_CA,
        connection_timeout=10,
    )
    cursor = connection.cursor()

    cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cursor.execute(f"USE `{db_name}`")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL,
            email VARCHAR(150) UNIQUE NOT NULL,
            contrasena VARCHAR(255) NOT NULL,
            rol ENUM('admin', 'cliente') DEFAULT 'cliente',
            verificado TINYINT(1) DEFAULT 0,
            activo TINYINT(1) DEFAULT 1,
            fecha_confirmacion TIMESTAMP NULL,
            ultimo_login TIMESTAMP NULL,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS peliculas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            titulo VARCHAR(200) NOT NULL,
            descripcion TEXT,
            duracion INT NOT NULL,
            genero VARCHAR(80),
            categoria VARCHAR(80) DEFAULT 'Cartelera',
            clasificacion VARCHAR(10),
            imagen_url VARCHAR(500),
            trailer_url VARCHAR(500),
            estado ENUM('activa', 'inactiva') DEFAULT 'activa',
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ciudades (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL UNIQUE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sedes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL,
            ciudad_id INT NOT NULL,
            UNIQUE KEY uq_sede_ciudad (nombre, ciudad_id),
            FOREIGN KEY (ciudad_id) REFERENCES ciudades(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS funciones (
            id INT AUTO_INCREMENT PRIMARY KEY,
            pelicula_id INT NOT NULL,
            sede_id INT NOT NULL,
            fecha DATE NOT NULL,
            hora TIME NOT NULL,
            sala VARCHAR(40) DEFAULT 'Sala 1',
            formato VARCHAR(20) DEFAULT '2D',
            precio DECIMAL(10,2) NOT NULL,
            estado ENUM('disponible', 'cancelada') DEFAULT 'disponible',
            FOREIGN KEY (pelicula_id) REFERENCES peliculas(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS asientos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            numero INT NOT NULL,
            fila CHAR(1) NOT NULL,
            columna INT NOT NULL,
            estado ENUM('activo', 'inactivo') DEFAULT 'activo',
            UNIQUE KEY asiento_unico (fila, columna)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tiquetes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            codigo VARCHAR(50) UNIQUE NOT NULL,
            usuario_id INT,
            funcion_id INT NOT NULL,
            fecha_compra TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            subtotal_boletas DECIMAL(10,2) DEFAULT 0.00,
            subtotal_comida DECIMAL(10,2) DEFAULT 0.00,
            metodo_pago VARCHAR(40),
            referencia_pago VARCHAR(120),
            payment_snapshot_json TEXT,
            extras_json TEXT,
            total DECIMAL(10,2) NOT NULL,
            estado_pago ENUM('aprobado', 'rechazado', 'pendiente') DEFAULT 'aprobado',
            pago_simulado TINYINT(1) DEFAULT 1,
            estado ENUM('activo', 'usado', 'cancelado') DEFAULT 'activo',
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (funcion_id) REFERENCES funciones(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS detalle_tiquete (
            id INT AUTO_INCREMENT PRIMARY KEY,
            tiquete_id INT NOT NULL,
            asiento_id INT NOT NULL,
            precio_unitario DECIMAL(10,2) NOT NULL,
            FOREIGN KEY (tiquete_id) REFERENCES tiquetes(id),
            FOREIGN KEY (asiento_id) REFERENCES asientos(id),
            UNIQUE KEY asiento_por_funcion (tiquete_id, asiento_id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS asientos_funcion (
            id INT AUTO_INCREMENT PRIMARY KEY,
            funcion_id INT NOT NULL,
            asiento_id INT NOT NULL,
            tiquete_id INT NOT NULL,
            FOREIGN KEY (funcion_id) REFERENCES funciones(id),
            FOREIGN KEY (asiento_id) REFERENCES asientos(id),
            FOREIGN KEY (tiquete_id) REFERENCES tiquetes(id),
            UNIQUE KEY no_doble_venta (funcion_id, asiento_id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS qr_tickets (
            id INT AUTO_INCREMENT PRIMARY KEY,
            tiquete_id INT NOT NULL,
            codigo_qr TEXT NOT NULL,
            fecha_generacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_qr_tiquete (tiquete_id),
            FOREIGN KEY (tiquete_id) REFERENCES tiquetes(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS resenas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            usuario_id INT NOT NULL,
            pelicula_id INT NOT NULL,
            comentario TEXT,
            puntuacion DECIMAL(3,1) NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (pelicula_id) REFERENCES peliculas(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_action_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            admin_id INT NOT NULL,
            action_type VARCHAR(80) NOT NULL,
            details_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            KEY idx_admin_logs_admin_fecha (admin_id, created_at),
            FOREIGN KEY (admin_id) REFERENCES usuarios(id)
        )
        """
    )

    ensure_column(cursor, db_name, "usuarios", "verificado", "TINYINT(1) DEFAULT 0")
    ensure_column(cursor, db_name, "usuarios", "activo", "TINYINT(1) DEFAULT 1")
    ensure_column(cursor, db_name, "usuarios", "fecha_confirmacion", "TIMESTAMP NULL")
    ensure_column(cursor, db_name, "usuarios", "ultimo_login", "TIMESTAMP NULL")
    ensure_column(cursor, db_name, "peliculas", "categoria", "VARCHAR(80) DEFAULT 'Cartelera'")
    ensure_column(cursor, db_name, "funciones", "sede_id", "INT NULL")
    ensure_column(cursor, db_name, "funciones", "formato", "VARCHAR(20) DEFAULT '2D'")
    ensure_column(cursor, db_name, "tiquetes", "subtotal_boletas", "DECIMAL(10,2) DEFAULT 0.00")
    ensure_column(cursor, db_name, "tiquetes", "subtotal_comida", "DECIMAL(10,2) DEFAULT 0.00")
    ensure_column(cursor, db_name, "tiquetes", "metodo_pago", "VARCHAR(40)")
    ensure_column(cursor, db_name, "tiquetes", "referencia_pago", "VARCHAR(120)")
    ensure_column(cursor, db_name, "tiquetes", "payment_snapshot_json", "TEXT")
    ensure_column(cursor, db_name, "tiquetes", "extras_json", "TEXT")
    ensure_column(cursor, db_name, "tiquetes", "estado_pago", "ENUM('aprobado', 'rechazado', 'pendiente') DEFAULT 'aprobado'")
    ensure_column(cursor, db_name, "tiquetes", "pago_simulado", "TINYINT(1) DEFAULT 1")

    ensure_index(cursor, "resenas", "uq_resena_usuario_pelicula", ["usuario_id", "pelicula_id"], unique=True)
    ensure_index(cursor, "qr_tickets", "uq_qr_tiquete", ["tiquete_id"], unique=True)
    ensure_index(cursor, "funciones", "no_traslape", ["sede_id", "sala", "fecha", "hora"], unique=True)

    _, sede_ids = seed_locations(cursor)
    seed_admin_user(cursor)

    cursor.execute("SELECT COUNT(*) FROM asientos")
    if cursor.fetchone()[0] == 0:
        seat_number = 1
        for row in "ABCDEFGHIJ":
            for column in range(1, 16):
                cursor.execute(
                    "INSERT INTO asientos (numero, fila, columna) VALUES (%s, %s, %s)",
                    (seat_number, row, column),
                )
                seat_number += 1

    seed_movies(cursor, sede_ids)
    repair_legacy_catalog(cursor, sede_ids)

    cursor.execute("SELECT COUNT(*) FROM funciones WHERE sede_id IS NULL")
    if cursor.fetchone()[0] == 0:
        cursor.execute("ALTER TABLE funciones MODIFY COLUMN sede_id INT NOT NULL")

    cursor.execute("ALTER TABLE funciones MODIFY COLUMN formato VARCHAR(20) NOT NULL DEFAULT '2D'")
    cursor.execute("ALTER TABLE peliculas MODIFY COLUMN categoria VARCHAR(80) NOT NULL DEFAULT 'Cartelera'")
    ensure_foreign_key(cursor, "funciones", "fk_funciones_sede", "sede_id", "sedes", "id")

    cursor.execute(
        """
        UPDATE funciones f
        JOIN sedes s ON s.id = f.sede_id
        JOIN ciudades c ON c.id = s.ciudad_id
        SET f.estado = 'disponible'
        WHERE c.nombre = %s AND s.nombre = %s
        """,
        (DEFAULT_CITY_NAME, DEFAULT_SEDE_NAME),
    )
    cursor.execute(
        """
        SELECT titulo, imagen_url
        FROM peliculas
        WHERE imagen_url IS NOT NULL AND imagen_url != ''
        ORDER BY titulo
        """
    )
    sync_asset_manifest(build_asset_manifest_entries(cursor.fetchall()))

    connection.commit()
    cursor.close()
    connection.close()
    logger.info("Bootstrap de base de datos completado.")
