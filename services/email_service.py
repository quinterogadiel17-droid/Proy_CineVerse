import base64
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, Optional

import requests
from flask import current_app, has_app_context
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import Config

logger = logging.getLogger(__name__)
_mail_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mail-worker")
BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def _get_config_value(name):
    if has_app_context():
        return current_app.config.get(name, getattr(Config, name, None))
    return getattr(Config, name, None)


def _get_mail_settings():
    return {
        "api_key": (_get_config_value("BREVO_API_KEY") or "").strip(),
        "from_email": (_get_config_value("MAIL_FROM") or "").strip(),
        "from_name": (_get_config_value("MAIL_FROM_NAME") or "").strip(),
        "debug": bool(_get_config_value("MAIL_DEBUG")),
        "max_retries": int(_get_config_value("MAIL_MAX_RETRIES") or 2),
        "retry_delay_seconds": float(_get_config_value("MAIL_RETRY_DELAY_SECONDS") or 1.5),
        "timeout_seconds": int(_get_config_value("MAIL_TIMEOUT_SECONDS") or 10),
    }


def _mask_secret(value):
    if not value:
        return "(empty)"
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}***{value[-3:]}"


def get_mail_configuration_status():
    settings = _get_mail_settings()
    missing = [
        key
        for key, value in {
            "BREVO_API_KEY": settings["api_key"],
            "MAIL_FROM": settings["from_email"],
        }.items()
        if not value
    ]
    return {
        "configured": not missing,
        "missing": missing,
        "provider": "brevo",
        "api_key_masked": _mask_secret(settings["api_key"]),
        "from_email": settings["from_email"] or "(empty)",
        "from_name": settings["from_name"] or "CineVerse",
        "timeout_seconds": settings["timeout_seconds"],
    }


def log_mail_configuration(context="runtime"):
    status = get_mail_configuration_status()
    logger.info(
        "MAIL CONFIG [%s]: provider=%s configured=%s from=%s from_name=%s api_key=%s timeout=%s missing=%s",
        context,
        status["provider"],
        status["configured"],
        status["from_email"],
        status["from_name"],
        status["api_key_masked"],
        status["timeout_seconds"],
        ",".join(status["missing"]) if status["missing"] else "none",
    )
    return status


def _serializer():
    return URLSafeTimedSerializer(_get_config_value("SECRET_KEY"))


def is_mail_configured():
    return get_mail_configuration_status()["configured"]


def generate_email_token(email):
    return _serializer().dumps(email, salt=_get_config_value("EMAIL_TOKEN_SALT"))


def confirm_email_token(token, max_age=60 * 60 * 24):
    try:
        return _serializer().loads(token, salt=_get_config_value("EMAIL_TOKEN_SALT"), max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def generate_password_reset_token(email):
    return _serializer().dumps(email, salt=_get_config_value("PASSWORD_RESET_TOKEN_SALT"))


def confirm_password_reset_token(token, max_age=None):
    max_age = max_age or _get_config_value("PASSWORD_RESET_MAX_AGE_SECONDS")
    try:
        return _serializer().loads(token, salt=_get_config_value("PASSWORD_RESET_TOKEN_SALT"), max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def _build_brevo_payload(subject, recipient, text_body, html_body=None, attachments: Optional[Iterable[dict]] = None, mail_settings=None):
    mail_settings = mail_settings or _get_mail_settings()
    payload = {
        "sender": {
            "email": mail_settings["from_email"],
            "name": mail_settings["from_name"] or "CineVerse",
        },
        "to": [{"email": recipient}],
        "subject": subject,
        "textContent": text_body,
        "htmlContent": html_body or f"<pre>{text_body}</pre>",
        "headers": {
            "X-Auto-Response-Suppress": "All",
        },
    }

    encoded_attachments = []
    for attachment in attachments or []:
        encoded_attachments.append(
            {
                "name": attachment.get("filename", "archivo.bin"),
                "content": base64.b64encode(attachment["content"]).decode("ascii"),
            }
        )

    if encoded_attachments:
        payload["attachment"] = encoded_attachments

    return payload


def _send_via_brevo(payload, recipient, mail_settings):
    response = requests.post(
        BREVO_API_URL,
        headers={
            "accept": "application/json",
            "api-key": mail_settings["api_key"],
            "content-type": "application/json",
        },
        json=payload,
        timeout=mail_settings["timeout_seconds"],
    )

    if response.ok:
        logger.info("Correo entregado a Brevo para %s con status=%s", recipient, response.status_code)
        return True, None

    error_message = f"Brevo devolvio {response.status_code}"
    try:
        body = response.json()
        api_message = body.get("message") or body.get("code") or str(body)
        error_message = f"{error_message}: {api_message}"
    except Exception:
        if response.text:
            error_message = f"{error_message}: {response.text[:200]}"

    logger.warning("Error Brevo para %s: %s", recipient, error_message)
    return False, error_message


def _send_email_with_settings(subject, recipient, text_body, html_body=None, attachments: Optional[Iterable[dict]] = None, mail_settings=None):
    mail_settings = mail_settings or _get_mail_settings()
    missing = [
        key
        for key, value in {
            "BREVO_API_KEY": mail_settings["api_key"],
            "MAIL_FROM": mail_settings["from_email"],
        }.items()
        if not value
    ]
    if missing:
        logger.warning("Servicio de correo incompleto para %s. Faltan: %s", recipient, ",".join(missing))
        return False, f"Correo no configurado. Faltan: {', '.join(missing)}"

    payload = _build_brevo_payload(
        subject,
        recipient,
        text_body,
        html_body=html_body,
        attachments=attachments,
        mail_settings=mail_settings,
    )

    try:
        return _send_via_brevo(payload, recipient, mail_settings)
    except requests.Timeout as exc:
        message = f"Timeout enviando correo con Brevo: {exc}"
        logger.warning("Timeout Brevo para %s: %s", recipient, exc)
        return False, message
    except requests.RequestException as exc:
        message = f"Error de red con Brevo: {exc}"
        logger.warning("Error de red Brevo para %s: %s", recipient, exc)
        return False, message
    except Exception as exc:
        message = f"Error inesperado enviando correo: {exc}"
        logger.exception("Error inesperado Brevo para %s", recipient)
        return False, message


def send_email(subject, recipient, text_body, html_body=None, attachments: Optional[Iterable[dict]] = None):
    return _send_email_with_settings(subject, recipient, text_body, html_body, attachments)


def _run_async_email(payload):
    mail_settings = payload["mail_settings"]
    last_error = None
    max_attempts = max(mail_settings["max_retries"] + 1, 1)

    for attempt in range(1, max_attempts + 1):
        sent, error = _send_email_with_settings(
            payload["subject"],
            payload["recipient"],
            payload["text_body"],
            payload.get("html_body"),
            payload.get("attachments"),
            mail_settings=mail_settings,
        )
        if sent:
            return {"ok": True, "error": None, "attempts": attempt}
        last_error = error
        if attempt < max_attempts:
            time.sleep(mail_settings["retry_delay_seconds"])

    logger.error(
        "No fue posible enviar correo a %s por Brevo despues de %s intentos: %s",
        payload["recipient"],
        max_attempts,
        last_error,
    )
    return {"ok": False, "error": last_error or "No fue posible enviar el correo.", "attempts": max_attempts}


def _log_async_result(recipient, future):
    try:
        result = future.result()
        if result["ok"]:
            logger.info("Entrega Brevo completada para %s tras %s intento(s).", recipient, result["attempts"])
        else:
            logger.error("Entrega Brevo fallida para %s: %s", recipient, result["error"])
    except Exception:
        logger.exception("Fallo inesperado procesando el resultado del correo a %s", recipient)


def send_email_async(subject, recipient, text_body, html_body=None, attachments: Optional[Iterable[dict]] = None):
    mail_status = get_mail_configuration_status()
    if not mail_status["configured"]:
        logger.warning("Brevo no disponible al encolar correo para %s. Faltan: %s", recipient, ",".join(mail_status["missing"]))
        return "failed", f"Correo no configurado. Faltan: {', '.join(mail_status['missing'])}"

    payload = {
        "subject": subject,
        "recipient": recipient,
        "text_body": text_body,
        "html_body": html_body,
        "attachments": list(attachments or []),
        "mail_settings": _get_mail_settings(),
    }

    try:
        future = _mail_executor.submit(_run_async_email, payload)
        future.add_done_callback(lambda done: _log_async_result(recipient, done))
    except Exception as exc:
        logger.exception("No se pudo encolar el correo para %s", recipient)
        return "failed", str(exc)

    logger.info("Correo a %s encolado para entrega en background con Brevo.", recipient)
    return "queued", None


def send_confirmation_email(user_name, email, confirm_url):
    subject = "Confirma tu cuenta en CineVerse"
    text_body = (
        f"Hola {user_name},\n\n"
        f"Confirma tu cuenta visitando este enlace:\n{confirm_url}\n\n"
        "Si no creaste esta cuenta, ignora este correo.\n"
        "Si no lo ves, revisa tu carpeta de spam."
    )
    html_body = f"""
    <h2>Confirma tu cuenta</h2>
    <p>Hola <strong>{user_name}</strong>,</p>
    <p>Confirma tu cuenta de CineVerse haciendo clic en el siguiente enlace:</p>
    <p><a href="{confirm_url}">{confirm_url}</a></p>
    <p>Si no creaste esta cuenta, puedes ignorar este mensaje.</p>
    <p>Si no lo ves en bandeja principal, revisa spam o promociones.</p>
    """
    return send_email(subject, email, text_body, html_body)


def send_confirmation_email_async(user_name, email, confirm_url):
    subject = "Confirma tu cuenta en CineVerse"
    text_body = (
        f"Hola {user_name},\n\n"
        f"Confirma tu cuenta visitando este enlace:\n{confirm_url}\n\n"
        "Si no creaste esta cuenta, ignora este correo.\n"
        "Si no lo ves, revisa tu carpeta de spam."
    )
    html_body = f"""
    <h2>Confirma tu cuenta</h2>
    <p>Hola <strong>{user_name}</strong>,</p>
    <p>Confirma tu cuenta de CineVerse haciendo clic en el siguiente enlace:</p>
    <p><a href="{confirm_url}">{confirm_url}</a></p>
    <p>Si no creaste esta cuenta, puedes ignorar este mensaje.</p>
    <p>Si no lo ves en bandeja principal, revisa spam o promociones.</p>
    """
    return send_email_async(subject, email, text_body, html_body)


def send_password_reset_email_async(user_name, email, reset_url):
    subject = "Restablece tu contrasena de CineVerse"
    text_body = (
        f"Hola {user_name},\n\n"
        f"Para restablecer tu contrasena visita este enlace:\n{reset_url}\n\n"
        "Si no solicitaste este cambio, ignora este correo.\n"
        "Si no lo ves, revisa tu carpeta de spam."
    )
    html_body = f"""
    <h2>Restablece tu contrasena</h2>
    <p>Hola <strong>{user_name}</strong>,</p>
    <p>Recibimos una solicitud para cambiar tu contrasena.</p>
    <p><a href="{reset_url}">{reset_url}</a></p>
    <p>Si no solicitaste este cambio, ignora este mensaje.</p>
    <p>Si no lo ves en bandeja principal, revisa spam o promociones.</p>
    """
    return send_email_async(subject, email, text_body, html_body)


def send_ticket_email(user_name, email, ticket_url, ticket_code, qr_png_bytes):
    subject = "Tu tiquete CineVerse con codigo QR"
    text_body = (
        f"Hola {user_name},\n\n"
        f"Tu compra fue confirmada. Puedes ver tu tiquete aqui:\n{ticket_url}\n\n"
        f"Codigo: {ticket_code}\n"
    )
    html_body = f"""
    <h2>Tu tiquete esta listo</h2>
    <p>Hola <strong>{user_name}</strong>,</p>
    <p>Tu compra fue confirmada. Puedes abrir tu tiquete desde este enlace:</p>
    <p><a href="{ticket_url}">{ticket_url}</a></p>
    <p><strong>Codigo:</strong> {ticket_code}</p>
    """
    attachments = [
        {
            "content": qr_png_bytes,
            "filename": f"{ticket_code}.png",
        }
    ]
    return send_email(subject, email, text_body, html_body, attachments=attachments)


def send_ticket_email_async(user_name, email, ticket_url, ticket_code, qr_png_bytes):
    subject = "Tu tiquete CineVerse con codigo QR"
    text_body = (
        f"Hola {user_name},\n\n"
        f"Tu compra fue confirmada. Puedes ver tu tiquete aqui:\n{ticket_url}\n\n"
        f"Codigo: {ticket_code}\n"
        "Si no encuentras el correo, revisa tu carpeta de spam."
    )
    html_body = f"""
    <h2>Tu tiquete esta listo</h2>
    <p>Hola <strong>{user_name}</strong>,</p>
    <p>Tu compra fue confirmada. Puedes abrir tu tiquete desde este enlace:</p>
    <p><a href="{ticket_url}">{ticket_url}</a></p>
    <p><strong>Codigo:</strong> {ticket_code}</p>
    <p>Si no ves este correo en tu bandeja principal, revisa spam o promociones.</p>
    """
    attachments = [
        {
            "content": qr_png_bytes,
            "filename": f"{ticket_code}.png",
        }
    ]
    return send_email_async(subject, email, text_body, html_body, attachments=attachments)
