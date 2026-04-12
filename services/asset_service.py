import base64
import logging
import re

from werkzeug.utils import secure_filename

from config import Config

logger = logging.getLogger(__name__)

DATA_URL_RE = re.compile(r"^data:(?P<mime>image/[a-zA-Z0-9.+-]+);base64,(?P<data>.+)$")


def is_allowed_image(filename):
    if "." not in filename:
        return False
    extension = filename.rsplit(".", 1)[1].lower()
    return extension in Config.ALLOWED_IMAGE_EXTENSIONS


def _normalize_mime_type(mime_type):
    return (mime_type or "").strip().lower()


def _is_allowed_mime_type(mime_type):
    return _normalize_mime_type(mime_type) in Config.ALLOWED_IMAGE_MIME_TYPES


def _validate_size(size_bytes):
    if size_bytes > Config.POSTER_MAX_BYTES:
        raise ValueError(f"La imagen supera el maximo permitido ({Config.POSTER_MAX_BYTES} bytes).")


def read_uploaded_poster_bytes(file_storage):
    original_name = secure_filename(file_storage.filename or "")
    if not original_name:
        raise ValueError("Debes seleccionar una imagen.")
    if not is_allowed_image(original_name):
        raise ValueError("Formato de imagen no permitido.")

    mime_type = _normalize_mime_type(file_storage.mimetype)
    if not _is_allowed_mime_type(mime_type):
        raise ValueError("Tipo MIME de imagen no permitido.")

    payload = file_storage.read()
    if not payload:
        raise ValueError("El archivo de imagen esta vacio.")
    _validate_size(len(payload))
    return payload, mime_type


def build_data_url(image_bytes, mime_type):
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def parse_data_url(data_url):
    if not data_url:
        return None, None

    value = str(data_url).strip()
    match = DATA_URL_RE.match(value)
    if not match:
        return None, None

    mime_type = _normalize_mime_type(match.group("mime"))
    if not _is_allowed_mime_type(mime_type):
        raise ValueError("Tipo MIME de imagen no permitido.")

    try:
        image_bytes = base64.b64decode(match.group("data"), validate=True)
    except Exception as exc:
        raise ValueError("La imagen enviada no es valida.") from exc

    if not image_bytes:
        raise ValueError("La imagen enviada esta vacia.")
    _validate_size(len(image_bytes))
    return image_bytes, mime_type


def resolve_poster_url(raw_url):
    value = (raw_url or "").strip()
    if not value:
        return Config.DEFAULT_POSTER_URL
    return value


def append_asset_manifest(name, path, description, ui_location):
    current = ""
    if Config.ASSET_MANIFEST.exists():
        current = Config.ASSET_MANIFEST.read_text(encoding="utf-8")
        if path in current:
            return

    block = (
        f"Nombre de imagen: {name}\n"
        f"Ruta: {path}\n"
        f"Descripcion: {description}\n"
        f"Ubicacion en UI: {ui_location}\n"
        + "-" * 40
        + "\n"
    )

    if not current:
        current = "MANIFIESTO DE IMAGENES CINEVERSE\n================================\n\n"

    Config.ASSET_MANIFEST.write_text(current + block, encoding="utf-8")


def log_storage_configuration(context="runtime"):
    logger.info(
        "STORAGE CONFIG [%s]: backend=%s poster_max_bytes=%s allowed_mime_types=%s",
        context,
        Config.IMAGE_STORAGE_BACKEND,
        Config.POSTER_MAX_BYTES,
        ",".join(sorted(Config.ALLOWED_IMAGE_MIME_TYPES)),
    )


def get_storage_configuration_status():
    return {
        "backend": Config.IMAGE_STORAGE_BACKEND,
        "configured": Config.IMAGE_STORAGE_BACKEND == "db",
        "poster_max_bytes": Config.POSTER_MAX_BYTES,
        "allowed_mime_types": sorted(Config.ALLOWED_IMAGE_MIME_TYPES),
        "missing": [] if Config.IMAGE_STORAGE_BACKEND == "db" else ["IMAGE_STORAGE_BACKEND=db"],
    }
