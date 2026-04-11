import logging
import smtplib
import time
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from typing import Iterable, Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import Config

logger = logging.getLogger(__name__)
_mail_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mail-worker")


def _serializer():
    return URLSafeTimedSerializer(Config.SECRET_KEY)


def is_mail_configured():
    return all([Config.MAIL_SERVER, Config.MAIL_USERNAME, Config.MAIL_PASSWORD, Config.MAIL_FROM])


def generate_email_token(email):
    return _serializer().dumps(email, salt=Config.EMAIL_TOKEN_SALT)


def confirm_email_token(token, max_age=60 * 60 * 24):
    try:
        return _serializer().loads(token, salt=Config.EMAIL_TOKEN_SALT, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def generate_password_reset_token(email):
    return _serializer().dumps(email, salt=Config.PASSWORD_RESET_TOKEN_SALT)


def confirm_password_reset_token(token, max_age=None):
    max_age = max_age or Config.PASSWORD_RESET_MAX_AGE_SECONDS
    try:
        return _serializer().loads(token, salt=Config.PASSWORD_RESET_TOKEN_SALT, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def _build_message(subject, recipient, text_body, html_body=None, attachments: Optional[Iterable[dict]] = None):
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = Config.MAIL_FROM
    message["To"] = recipient
    message.set_content(text_body)

    if html_body:
        message.add_alternative(html_body, subtype="html")

    for attachment in attachments or []:
        message.add_attachment(
            attachment["content"],
            maintype=attachment.get("maintype", "application"),
            subtype=attachment.get("subtype", "octet-stream"),
            filename=attachment.get("filename", "archivo.bin"),
        )

    return message


def send_email(subject, recipient, text_body, html_body=None, attachments: Optional[Iterable[dict]] = None):
    if not is_mail_configured():
        return False, "SMTP no configurado"

    message = _build_message(subject, recipient, text_body, html_body, attachments)
    smtp_client = smtplib.SMTP_SSL if Config.MAIL_USE_SSL else smtplib.SMTP

    try:
        with smtp_client(Config.MAIL_SERVER, Config.MAIL_PORT, timeout=20) as server:
            if Config.MAIL_DEBUG:
                server.set_debuglevel(1)
            server.ehlo()
            if Config.MAIL_USE_TLS and not Config.MAIL_USE_SSL:
                server.starttls()
                server.ehlo()
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            server.send_message(message)
        return True, None
    except Exception as exc:
        logger.warning("Fallo enviando correo a %s: %s", recipient, exc)
        return False, str(exc)


def _run_async_email(payload):
    subject = payload["subject"]
    recipient = payload["recipient"]
    text_body = payload["text_body"]
    html_body = payload.get("html_body")
    attachments = payload.get("attachments")

    last_error = None
    max_attempts = max(Config.MAIL_MAX_RETRIES + 1, 1)

    for attempt in range(1, max_attempts + 1):
        sent, error = send_email(subject, recipient, text_body, html_body, attachments)
        if sent:
            logger.info("Correo enviado a %s en intento %s.", recipient, attempt)
            return True
        last_error = error
        if attempt < max_attempts:
            time.sleep(Config.MAIL_RETRY_DELAY_SECONDS)

    logger.error("No fue posible enviar correo a %s despues de %s intentos: %s", recipient, max_attempts, last_error)
    return False


def send_email_async(subject, recipient, text_body, html_body=None, attachments: Optional[Iterable[dict]] = None):
    if not is_mail_configured():
        return False, "SMTP no configurado"

    payload = {
        "subject": subject,
        "recipient": recipient,
        "text_body": text_body,
        "html_body": html_body,
        "attachments": list(attachments or []),
    }

    try:
        _mail_executor.submit(_run_async_email, payload)
        return True, None
    except Exception as exc:
        logger.exception("No se pudo encolar el correo para %s", recipient)
        return False, str(exc)


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
            "maintype": "image",
            "subtype": "png",
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
            "maintype": "image",
            "subtype": "png",
            "filename": f"{ticket_code}.png",
        }
    ]
    return send_email_async(subject, email, text_body, html_body, attachments=attachments)
