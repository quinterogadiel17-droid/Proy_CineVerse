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

    MYSQL_HOST     = os.getenv("DB_HOST",     "localhost")
    MYSQL_USER     = os.getenv("DB_USER",     "root")
    MYSQL_PASSWORD = os.getenv("DB_PASSWORD", "")
    MYSQL_DB       = os.getenv("DB_NAME",     "cinecol")
    MYSQL_PORT     = int(os.getenv("DB_PORT", "3306"))
    MYSQL_SSL_CA   = os.getenv("DB_SSL_CA", "/etc/ssl/certs/ca-certificates.crt")
    MYSQL_CURSORCLASS = "DictCursor"

    PROJECT_ROOT = BASE_DIR
    UPLOAD_FOLDER = BASE_DIR / "static" / "uploads"
    POSTER_UPLOAD_FOLDER = UPLOAD_FOLDER / "posters"
    ASSET_MANIFEST = BASE_DIR / "assets_manifest.txt"
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}

    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5000")
    EMAIL_TOKEN_SALT = os.getenv("EMAIL_TOKEN_SALT", "cinecol-email-confirmation")

    MAIL_SERVER   = os.getenv("MAIL_SERVER", "")
    MAIL_PORT     = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS  = env_bool("MAIL_USE_TLS", True)
    MAIL_USE_SSL  = env_bool("MAIL_USE_SSL", False)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_FROM     = os.getenv("MAIL_FROM", "no-reply@cinecol.com")
    MAIL_DEBUG    = env_bool("MAIL_DEBUG", False)

    QR_SCAN_INTERVAL_MS = int(os.getenv("QR_SCAN_INTERVAL_MS", "1200"))
