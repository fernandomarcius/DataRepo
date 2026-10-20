"""Outbound e-mail via corporate SMTP (Office 365).

Standard library only (smtplib + email.message) — no new dependency. Settings are
read lazily from the environment, following the same fail-fast-on-first-use pattern
as ``auth_service._jwt_secret``: the app boots without SMTP configured and only
fails when it actually tries to send.
"""
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

SMTP_TIMEOUT_SECONDS = 15
DEFAULT_SMTP_PORT = 587


class EmailSendError(Exception):
    """Raised when the message could not be handed to the SMTP server."""


def _smtp_settings():
    server = os.getenv("SMTP_SERVER")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    if not server or not user or not password:
        raise RuntimeError(
            "SMTP_SERVER, SMTP_USER and SMTP_PASSWORD environment variables are required"
        )
    try:
        port = int(os.getenv("SMTP_PORT") or DEFAULT_SMTP_PORT)
    except ValueError:
        raise RuntimeError("SMTP_PORT must be an integer")
    return {"server": server, "port": port, "user": user, "password": password}


def send_email(to: str, subject: str, text: str, html: Optional[str] = None) -> None:
    """Send a message over STARTTLS. Raises EmailSendError on any delivery failure.

    The From address is always the authenticated mailbox: Office 365 rejects a
    different sender unless the account holds an explicit "Send As" grant.
    """
    settings = _smtp_settings()

    msg = EmailMessage()
    msg["From"] = settings["user"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(settings["server"], settings["port"], timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(settings["user"], settings["password"])
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise EmailSendError(str(e)) from e
