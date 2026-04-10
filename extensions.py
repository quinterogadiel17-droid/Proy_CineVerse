import os
import mysql.connector as mysql_driver
from flask import current_app, g

class MySQL:
    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        app.config.setdefault('MYSQL_HOST', 'localhost')
        app.config.setdefault('MYSQL_USER', 'root')
        app.config.setdefault('MYSQL_PASSWORD', '')
        app.config.setdefault('MYSQL_DB', 'database')

    @property
    def connection(self):
        # Esto mantiene la conexión viva durante TODA la petición (request)
        if 'db_conn' not in g or not g.db_conn.is_connected():
            g.db_conn = mysql_driver.connect(
                host=current_app.config['MYSQL_HOST'],
                user=current_app.config['MYSQL_USER'],
                password=current_app.config['MYSQL_PASSWORD'],
                database=current_app.config['MYSQL_DB']
            )
        return g.db_conn

mysql = MySQL()