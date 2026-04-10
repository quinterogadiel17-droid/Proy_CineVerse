import os
import mysql.connector as mysql_driver
from flask import current_app, g

class MySQL:
    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        # Lee las variables de entorno (Render/Aiven). Si no existen, usa local.
        app.config.setdefault('MYSQL_HOST', os.getenv('DB_HOST', 'localhost'))
        app.config.setdefault('MYSQL_USER', os.getenv('DB_USER', 'root'))
        app.config.setdefault('MYSQL_PASSWORD', os.getenv('DB_PASSWORD', ''))
        app.config.setdefault('MYSQL_DB', os.getenv('DB_NAME', 'defaultdb'))
        app.config.setdefault('MYSQL_PORT', os.getenv('DB_PORT', '3306'))

    @property
    def connection(self):
        # Mantiene la conexión activa durante la petición
        if 'db_conn' not in g or not g.db_conn.is_connected():
            g.db_conn = mysql_driver.connect(
                host=current_app.config['MYSQL_HOST'],
                user=current_app.config['MYSQL_USER'],
                password=current_app.config['MYSQL_PASSWORD'],
                database=current_app.config['MYSQL_DB'],
                port=int(current_app.config['MYSQL_PORT'])
            )
        return g.db_conn

# ESTA LÍNEA ES VITAL: Crea el objeto que importa app.py
mysql = MySQL()