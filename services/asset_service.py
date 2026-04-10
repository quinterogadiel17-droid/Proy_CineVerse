import os
import uuid
from pathlib import Path

from werkzeug.utils import secure_filename

from config import Config


def ensure_asset_directories():
    Config.POSTER_UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)


def is_allowed_image(filename):
    if "." not in filename:
        return False
    extension = filename.rsplit(".", 1)[1].lower()
    return extension in Config.ALLOWED_IMAGE_EXTENSIONS


def save_uploaded_poster(file_storage):
    ensure_asset_directories()
    original_name = secure_filename(file_storage.filename or "")
    if not original_name or not is_allowed_image(original_name):
        raise ValueError("Formato de imagen no permitido")

    extension = original_name.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{extension}"
    destination = Config.POSTER_UPLOAD_FOLDER / unique_name
    file_storage.save(destination)
    relative_path = f"/static/uploads/posters/{unique_name}"
    return unique_name, relative_path


def sync_asset_manifest(entries):
    lines = [
        "MANIFIESTO DE IMAGENES CINEVERSE",
        "================================",
        "",
    ]
    for entry in entries:
        lines.extend(
            [
                f"Nombre de imagen: {entry['name']}",
                f"Ruta: {entry['path']}",
                f"Descripcion: {entry['description']}",
                f"Ubicacion en UI: {entry['ui_location']}",
                "-" * 40,
            ]
        )

    Config.ASSET_MANIFEST.write_text("\n".join(lines), encoding="utf-8")


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
