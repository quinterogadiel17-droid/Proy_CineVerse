import os
import mysql.connector as mysql_driver
from flask import current_app, g


class MySQL:
    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        # Sobreescribe siempre con las variables de entorno.
        # Si la variable no existe en el entorno, cae al valor local.
        app.config['MYSQL_HOST']     = os.getenv('DB_HOST')
        app.config['MYSQL_USER']     = os.getenv('DB_USER')
        app.config['MYSQL_PASSWORD'] = os.getenv('DB_PASSWORD')
        app.config['MYSQL_DB']       = os.getenv('DB_NAME')
        app.config['MYSQL_PORT']     = os.getenv('DB_PORT')

    @property
    def connection(self):
        if 'db_conn' not in g or not g.db_conn.is_connected():
            g.db_conn = mysql_driver.connect(
                host=current_app.config['MYSQL_HOST'],
                user=current_app.config['MYSQL_USER'],
                password=current_app.config['MYSQL_PASSWORD'],
                database=current_app.config['MYSQL_DB'],
                port=int(current_app.config['MYSQL_PORT']),
                ssl_disabled=False,          # Aiven exige SSL
                connection_timeout=10,
            )
        return g.db_conn


# ESTA LÍNEA ES VITAL: Crea el objeto que importa app.py
mysql = MySQL()