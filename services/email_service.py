import smtplib
from email.message import EmailMessage
from typing import Iterable, Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import Config


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


def send_email(subject, recipient, text_body, html_body=None, attachments: Optional[Iterable[dict]] = None):
    if not is_mail_configured():
        return False, "SMTP no configurado"

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

    smtp_client = smtplib.SMTP_SSL if Config.MAIL_USE_SSL else smtplib.SMTP

    with smtp_client(Config.MAIL_SERVER, Config.MAIL_PORT, timeout=20) as server:
        if Config.MAIL_DEBUG:
            server.set_debuglevel(1)
        server.ehlo()
        if Config.MAIL_USE_TLS and not Config.MAIL_USE_SSL:
            server.starttls()
            server.ehlo()
        try:
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
        except Exception as e:
            print("ERROR EMAIL:", e)
            return False, str(e)
        server.send_message(message)

    return True, None


def send_confirmation_email(user_name, email, confirm_url):
    subject = "Confirma tu cuenta en CineVerse"
    text_body = (
        f"Hola {user_name},\n\n"
        f"Confirma tu cuenta visitando este enlace:\n{confirm_url}\n\n"
        "Si no creaste esta cuenta, ignora este correo."
    )
    html_body = f"""
    <h2>Confirma tu cuenta</h2>
    <p>Hola <strong>{user_name}</strong>,</p>
    <p>Confirma tu cuenta de CineVerse haciendo clic en el siguiente enlace:</p>
    <p><a href="{confirm_url}">{confirm_url}</a></p>
    <p>Si no creaste esta cuenta, puedes ignorar este mensaje.</p>
    """
    return send_email(subject, email, text_body, html_body)


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
