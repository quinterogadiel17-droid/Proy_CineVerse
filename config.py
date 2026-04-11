import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "cinecol-secret-2024-adso18")
    ENVIRONMENT = os.getenv("FLASK_ENV", "production")

    MYSQL_HOST     = os.getenv("DB_HOST",     "localhost")
    MYSQL_USER     = os.getenv("DB_USER",     "root")
    MYSQL_PASSWORD = os.getenv("DB_PASSWORD", "")
    MYSQL_DB       = os.getenv("DB_NAME",     "cinecol")
    MYSQL_PORT     = int(os.getenv("DB_PORT", "3306"))
    MYSQL_SSL_CA   = os.getenv("DB_SSL_CA", "/etc/ssl/certs/ca-certificates.crt")
    MYSQL_CURSORCLASS = "DictCursor"
    MYSQL_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "3"))
    MYSQL_PING_RECONNECT = env_bool("DB_PING_RECONNECT", False)
    MYSQL_LOCATION_CACHE_SECONDS = int(os.getenv("DB_LOCATION_CACHE_SECONDS", "120"))

    PROJECT_ROOT = BASE_DIR
    UPLOAD_FOLDER = BASE_DIR / "static" / "uploads"
    POSTER_UPLOAD_FOLDER = UPLOAD_FOLDER / "posters"
    ASSET_MANIFEST = BASE_DIR / "assets_manifest.txt"
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}

    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5000")
    EMAIL_TOKEN_SALT = os.getenv("EMAIL_TOKEN_SALT", "cinecol-email-confirmation")
    PASSWORD_RESET_TOKEN_SALT = os.getenv("PASSWORD_RESET_TOKEN_SALT", "cinecol-password-reset")
    PASSWORD_RESET_MAX_AGE_SECONDS = int(os.getenv("PASSWORD_RESET_MAX_AGE_SECONDS", "3600"))

    MAIL_FROM     = os.getenv("MAIL_FROM", "no-reply@cinecol.com")
    MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "CineVerse")
    BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
    MAIL_DEBUG    = env_bool("MAIL_DEBUG", False)
    MAIL_MAX_RETRIES = int(os.getenv("MAIL_MAX_RETRIES", "2"))
    MAIL_RETRY_DELAY_SECONDS = float(os.getenv("MAIL_RETRY_DELAY_SECONDS", "1.5"))
    MAIL_TIMEOUT_SECONDS = int(os.getenv("MAIL_TIMEOUT_SECONDS", "10"))
    MAIL_ASYNC_WAIT_TIMEOUT = float(os.getenv("MAIL_ASYNC_WAIT_TIMEOUT", "0"))

    QR_SCAN_INTERVAL_MS = int(os.getenv("QR_SCAN_INTERVAL_MS", "1200"))
