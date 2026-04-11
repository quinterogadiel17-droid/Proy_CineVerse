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
        app.config['MYSQL_DB']       = os.getenv('DB_NAME',     'cinecol')
        app.config['MYSQL_PORT']     = os.getenv('DB_PORT',     '3306')
        app.config['MYSQL_SSL_CA']   = os.getenv('DB_SSL_CA',   '/etc/ssl/certs/ca-certificates.crt')
        app.config['MYSQL_CONNECT_TIMEOUT'] = int(os.getenv('DB_CONNECT_TIMEOUT', '3'))
        app.config['MYSQL_PING_RECONNECT'] = os.getenv('DB_PING_RECONNECT', 'false').strip().lower() in {'1', 'true', 'yes', 'on'}

    def _connect(self):
        return mysql_driver.connect(
            host=current_app.config['MYSQL_HOST'],
            user=current_app.config['MYSQL_USER'],
            password=current_app.config['MYSQL_PASSWORD'],
            database=current_app.config['MYSQL_DB'],
            port=int(current_app.config['MYSQL_PORT']),
            ssl_ca=current_app.config.get('MYSQL_SSL_CA'),
            connection_timeout=int(current_app.config.get('MYSQL_CONNECT_TIMEOUT', 3)),
            autocommit=True,
        )

    @property
    def connection(self):
        try:
            if 'db_conn' not in g:
                g.db_conn = self._connect()
            else:
                try:
                    g.db_conn.ping(reconnect=bool(current_app.config.get('MYSQL_PING_RECONNECT', False)), attempts=1, delay=0)
                except Exception:
                    stale_conn = g.pop('db_conn', None)
                    if stale_conn is not None:
                        try:
                            stale_conn.close()
                        except Exception:
                            pass
                    g.db_conn = self._connect()
            return g.db_conn

        except Exception as e:
            current_app.logger.warning("ERROR CONECTANDO A MYSQL: %s", e)
            raise



# Objeto global que importa app.py
mysql = MySQL()
