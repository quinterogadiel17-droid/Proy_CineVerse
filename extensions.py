import os
import mysql.connector as mysql_driver
from flask import current_app, g


class MySQL:
    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        app.config['MYSQL_HOST']     = os.getenv('DB_HOST',     'localhost')
        app.config['MYSQL_USER']     = os.getenv('DB_USER',     'root')
        app.config['MYSQL_PASSWORD'] = os.getenv('DB_PASSWORD', '')
        app.config['MYSQL_DB']       = os.getenv('DB_NAME',     'defaultdb')
        app.config['MYSQL_PORT']     = os.getenv('DB_PORT',     '3306')

    @property
    def connection(self):
        try:
            if 'db_conn' not in g:
                g.db_conn = mysql_driver.connect(
                    host=current_app.config['MYSQL_HOST'],
                    user=current_app.config['MYSQL_USER'],
                    password=current_app.config['MYSQL_PASSWORD'],
                    database=current_app.config['MYSQL_DB'],
                    port=int(current_app.config['MYSQL_PORT']),
                    ssl_ca="/etc/ssl/certs/ca-certificates.crt",
                    connection_timeout=10,
                    autocommit=True
                )
            else:
                try:
                    g.db_conn.ping(reconnect=True, attempts=3, delay=2)
                except:
                    g.db_conn = mysql_driver.connect(
                        host=current_app.config['MYSQL_HOST'],
                        user=current_app.config['MYSQL_USER'],
                        password=current_app.config['MYSQL_PASSWORD'],
                        database=current_app.config['MYSQL_DB'],
                        port=int(current_app.config['MYSQL_PORT']),
                        ssl_ca="/etc/ssl/certs/ca-certificates.crt",
                        connection_timeout=10,
                        autocommit=True
                    )
            return g.db_conn

        except Exception as e:
            print("ERROR CONECTANDO A MYSQL:", e)
            raise



# Objeto global que importa app.py
mysql = MySQL()