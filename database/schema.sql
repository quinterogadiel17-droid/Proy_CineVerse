-- MODIFICACION ACADEMICA 2026-04-09:
-- Se agrego la columna `pago_simulado` en `tiquetes` para dejar trazabilidad
-- de que el backend procesa pagos en modo de simulacion academica, sin validar
-- medios reales ni conectarse a pasarelas externas.
-- Tambien se agrego la tabla `admin_action_logs` para auditar liberaciones
-- manuales de asientos y acciones criticas de administracion sobre usuarios.
--
-- ============================================================
-- CINEVERSE / CINECOL
-- Esquema relacional base para Flask + MySQL
-- ============================================================

CREATE DATABASE IF NOT EXISTS cinecol CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE cinecol;

SET NAMES utf8mb4;

-- ------------------------------------------------------------
-- USUARIOS Y AUTENTICACION
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    contrasena VARCHAR(255) NOT NULL,
    rol ENUM('admin', 'cliente') NOT NULL DEFAULT 'cliente',
    verificado TINYINT(1) NOT NULL DEFAULT 0,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    fecha_confirmacion TIMESTAMP NULL,
    ultimo_login TIMESTAMP NULL,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Admin inicial. Contrasena sugerida: admin123
INSERT INTO usuarios (nombre, email, contrasena, rol, verificado, activo)
SELECT
    'Administrador CineVerse',
    'admin@cinecol.com',
    'scrypt:32768:8:1$KNCms314d0014aIP$aedb174400f50c8989f936608a29065b20ff09f13ab475818d83e00d437a4a8d000a6743c5fd05126f807078d0fbf229e6742dad749acfdc69af52855be3f14a',
    'admin',
    1,
    1
WHERE NOT EXISTS (
    SELECT 1
    FROM usuarios
    WHERE email = 'admin@cinecol.com'
);

-- ------------------------------------------------------------
-- CATALOGO
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS peliculas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    titulo VARCHAR(200) NOT NULL,
    descripcion TEXT,
    duracion INT NOT NULL COMMENT 'Duracion en minutos',
    genero VARCHAR(80),
    categoria VARCHAR(80) NOT NULL DEFAULT 'Cartelera',
    clasificacion VARCHAR(10),
    imagen_url VARCHAR(500),
    poster_blob MEDIUMBLOB,
    poster_mime VARCHAR(100),
    trailer_url VARCHAR(500),
    estado ENUM('activa', 'inactiva') NOT NULL DEFAULT 'activa',
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ciudades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS sedes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    ciudad_id INT NOT NULL,
    UNIQUE KEY uq_sede_ciudad (nombre, ciudad_id),
    CONSTRAINT fk_sedes_ciudad
        FOREIGN KEY (ciudad_id) REFERENCES ciudades(id)
);

CREATE TABLE IF NOT EXISTS funciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pelicula_id INT NOT NULL,
    sede_id INT NOT NULL,
    fecha DATE NOT NULL,
    hora TIME NOT NULL,
    sala VARCHAR(40) NOT NULL DEFAULT 'Sala 1',
    formato VARCHAR(20) NOT NULL DEFAULT '2D',
    precio DECIMAL(10,2) NOT NULL,
    estado ENUM('disponible', 'cancelada') NOT NULL DEFAULT 'disponible',
    CONSTRAINT fk_funciones_pelicula
        FOREIGN KEY (pelicula_id) REFERENCES peliculas(id) ON DELETE CASCADE,
    CONSTRAINT fk_funciones_sede
        FOREIGN KEY (sede_id) REFERENCES sedes(id),
    UNIQUE KEY no_traslape (sede_id, sala, fecha, hora),
    KEY idx_funciones_cartelera (pelicula_id, sede_id, fecha, estado)
);

CREATE TABLE IF NOT EXISTS asientos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    numero INT NOT NULL,
    fila CHAR(1) NOT NULL,
    columna INT NOT NULL,
    estado ENUM('activo', 'inactivo') NOT NULL DEFAULT 'activo',
    UNIQUE KEY asiento_unico (fila, columna)
);

CREATE TABLE IF NOT EXISTS tiquetes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(50) NOT NULL UNIQUE,
    usuario_id INT NULL,
    funcion_id INT NOT NULL,
    fecha_compra TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    subtotal_boletas DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    subtotal_comida DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    metodo_pago VARCHAR(40),
    referencia_pago VARCHAR(120),
    payment_snapshot_json TEXT,
    extras_json TEXT,
    total DECIMAL(10,2) NOT NULL,
    estado_pago ENUM('aprobado', 'rechazado', 'pendiente') NOT NULL DEFAULT 'aprobado',
    pago_simulado TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1 = pago academico simulado',
    estado ENUM('activo', 'usado', 'cancelado') NOT NULL DEFAULT 'activo',
    CONSTRAINT fk_tiquetes_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
    CONSTRAINT fk_tiquetes_funcion
        FOREIGN KEY (funcion_id) REFERENCES funciones(id),
    KEY idx_tiquetes_usuario_fecha (usuario_id, fecha_compra),
    KEY idx_tiquetes_funcion_estado (funcion_id, estado)
);

CREATE TABLE IF NOT EXISTS detalle_tiquete (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tiquete_id INT NOT NULL,
    asiento_id INT NOT NULL,
    precio_unitario DECIMAL(10,2) NOT NULL,
    CONSTRAINT fk_detalle_tiquete_tiquete
        FOREIGN KEY (tiquete_id) REFERENCES tiquetes(id) ON DELETE CASCADE,
    CONSTRAINT fk_detalle_tiquete_asiento
        FOREIGN KEY (asiento_id) REFERENCES asientos(id),
    UNIQUE KEY asiento_por_tiquete (tiquete_id, asiento_id)
);

CREATE TABLE IF NOT EXISTS asientos_funcion (
    id INT AUTO_INCREMENT PRIMARY KEY,
    funcion_id INT NOT NULL,
    asiento_id INT NOT NULL,
    tiquete_id INT NOT NULL,
    CONSTRAINT fk_asientos_funcion_funcion
        FOREIGN KEY (funcion_id) REFERENCES funciones(id) ON DELETE CASCADE,
    CONSTRAINT fk_asientos_funcion_asiento
        FOREIGN KEY (asiento_id) REFERENCES asientos(id),
    CONSTRAINT fk_asientos_funcion_tiquete
        FOREIGN KEY (tiquete_id) REFERENCES tiquetes(id) ON DELETE CASCADE,
    UNIQUE KEY no_doble_venta (funcion_id, asiento_id)
);

CREATE TABLE IF NOT EXISTS qr_tickets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tiquete_id INT NOT NULL,
    codigo_qr TEXT NOT NULL,
    fecha_generacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_qr_tiquete
        FOREIGN KEY (tiquete_id) REFERENCES tiquetes(id) ON DELETE CASCADE,
    UNIQUE KEY uq_qr_tiquete (tiquete_id)
);

CREATE TABLE IF NOT EXISTS resenas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    pelicula_id INT NOT NULL,
    comentario TEXT,
    puntuacion DECIMAL(3,1) NOT NULL,
    fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_resenas_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    CONSTRAINT fk_resenas_pelicula
        FOREIGN KEY (pelicula_id) REFERENCES peliculas(id) ON DELETE CASCADE,
    CONSTRAINT chk_resenas_puntuacion CHECK (puntuacion >= 1.0 AND puntuacion <= 10.0),
    UNIQUE KEY uq_resena_usuario_pelicula (usuario_id, pelicula_id)
);

CREATE TABLE IF NOT EXISTS admin_action_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    admin_id INT NOT NULL,
    action_type VARCHAR(80) NOT NULL,
    details_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_admin_logs_admin_fecha (admin_id, created_at),
    CONSTRAINT fk_admin_action_logs_admin
        FOREIGN KEY (admin_id) REFERENCES usuarios(id)
);

-- ------------------------------------------------------------
-- DATOS BASE DE UBICACIONES
-- ------------------------------------------------------------
INSERT INTO ciudades (nombre)
SELECT 'Barranquilla' WHERE NOT EXISTS (SELECT 1 FROM ciudades WHERE nombre = 'Barranquilla');
INSERT INTO ciudades (nombre)
SELECT 'Bogota' WHERE NOT EXISTS (SELECT 1 FROM ciudades WHERE nombre = 'Bogota');
INSERT INTO ciudades (nombre)
SELECT 'Medellin' WHERE NOT EXISTS (SELECT 1 FROM ciudades WHERE nombre = 'Medellin');
INSERT INTO ciudades (nombre)
SELECT 'Cali' WHERE NOT EXISTS (SELECT 1 FROM ciudades WHERE nombre = 'Cali');
INSERT INTO ciudades (nombre)
SELECT 'Cartagena' WHERE NOT EXISTS (SELECT 1 FROM ciudades WHERE nombre = 'Cartagena');
INSERT INTO ciudades (nombre)
SELECT 'Bucaramanga' WHERE NOT EXISTS (SELECT 1 FROM ciudades WHERE nombre = 'Bucaramanga');
INSERT INTO ciudades (nombre)
SELECT 'Armenia' WHERE NOT EXISTS (SELECT 1 FROM ciudades WHERE nombre = 'Armenia');

INSERT INTO sedes (nombre, ciudad_id)
SELECT 'CineVerse Buenavista', c.id
FROM ciudades c
WHERE c.nombre = 'Barranquilla'
  AND NOT EXISTS (
      SELECT 1 FROM sedes s
      WHERE s.nombre = 'CineVerse Buenavista' AND s.ciudad_id = c.id
  );

INSERT INTO sedes (nombre, ciudad_id)
SELECT 'CineVerse Portal del Rio', c.id
FROM ciudades c
WHERE c.nombre = 'Barranquilla'
  AND NOT EXISTS (
      SELECT 1 FROM sedes s
      WHERE s.nombre = 'CineVerse Portal del Rio' AND s.ciudad_id = c.id
  );

INSERT INTO sedes (nombre, ciudad_id)
SELECT 'CineVerse Andino', c.id
FROM ciudades c
WHERE c.nombre = 'Bogota'
  AND NOT EXISTS (
      SELECT 1 FROM sedes s
      WHERE s.nombre = 'CineVerse Andino' AND s.ciudad_id = c.id
  );

INSERT INTO sedes (nombre, ciudad_id)
SELECT 'CineVerse Gran Estacion', c.id
FROM ciudades c
WHERE c.nombre = 'Bogota'
  AND NOT EXISTS (
      SELECT 1 FROM sedes s
      WHERE s.nombre = 'CineVerse Gran Estacion' AND s.ciudad_id = c.id
  );

INSERT INTO sedes (nombre, ciudad_id)
SELECT 'CineVerse El Tesoro', c.id
FROM ciudades c
WHERE c.nombre = 'Medellin'
  AND NOT EXISTS (
      SELECT 1 FROM sedes s
      WHERE s.nombre = 'CineVerse El Tesoro' AND s.ciudad_id = c.id
  );

INSERT INTO sedes (nombre, ciudad_id)
SELECT 'CineVerse Oviedo', c.id
FROM ciudades c
WHERE c.nombre = 'Medellin'
  AND NOT EXISTS (
      SELECT 1 FROM sedes s
      WHERE s.nombre = 'CineVerse Oviedo' AND s.ciudad_id = c.id
  );

INSERT INTO sedes (nombre, ciudad_id)
SELECT 'CineVerse Chipichape', c.id
FROM ciudades c
WHERE c.nombre = 'Cali'
  AND NOT EXISTS (
      SELECT 1 FROM sedes s
      WHERE s.nombre = 'CineVerse Chipichape' AND s.ciudad_id = c.id
  );

INSERT INTO sedes (nombre, ciudad_id)
SELECT 'CineVerse Caribe Plaza', c.id
FROM ciudades c
WHERE c.nombre = 'Cartagena'
  AND NOT EXISTS (
      SELECT 1 FROM sedes s
      WHERE s.nombre = 'CineVerse Caribe Plaza' AND s.ciudad_id = c.id
  );

INSERT INTO sedes (nombre, ciudad_id)
SELECT 'CineVerse Cacique', c.id
FROM ciudades c
WHERE c.nombre = 'Bucaramanga'
  AND NOT EXISTS (
      SELECT 1 FROM sedes s
      WHERE s.nombre = 'CineVerse Cacique' AND s.ciudad_id = c.id
  );

INSERT INTO sedes (nombre, ciudad_id)
SELECT 'CineVerse Portal del Quindio', c.id
FROM ciudades c
WHERE c.nombre = 'Armenia'
  AND NOT EXISTS (
      SELECT 1 FROM sedes s
      WHERE s.nombre = 'CineVerse Portal del Quindio' AND s.ciudad_id = c.id
  );

-- ------------------------------------------------------------
-- PRECARGA DE ASIENTOS (150)
-- ------------------------------------------------------------
INSERT IGNORE INTO asientos (numero, fila, columna)
WITH RECURSIVE seat_numbers AS (
    SELECT 1 AS numero
    UNION ALL
    SELECT numero + 1
    FROM seat_numbers
    WHERE numero < 150
)
SELECT
    numero,
    CHAR(65 + FLOOR((numero - 1) / 15)) AS fila,
    ((numero - 1) % 15) + 1 AS columna
FROM seat_numbers;

-- Nota:
-- El catalogo de peliculas, funciones, posters y el manifiesto de activos
-- se completan automaticamente al iniciar la aplicacion Flask.
