"""Password reset tokens for the self-service "forgot my password" flow.

Tokens are random URL-safe strings handed out once by e-mail; only their SHA-256
digest is stored. Expiry is always evaluated by Postgres (``now()``) so the app
server's clock and timezone never matter.
"""
import hashlib
import os
import re
import secrets
from typing import Optional

from flask import request
from sqlalchemy import text

from db import engine, execute_query
from services.auth_service import update_user, validate_new_password

TOKEN_TTL_MINUTES = 30

# Deliberately permissive: this only decides whether the username can be used as a
# destination address, not whether the address is deliverable.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Tokens produced by secrets.token_urlsafe(32) are 43 chars of [A-Za-z0-9_-].
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")


def purge_expired_resets():
    """Apaga tokens vencidos ha mais de um dia. Roda no boot do api.

    A tabela e criada pela migration inicial (migrations/versions/0001_...);
    esta limpeza e manutencao de dados, nao de schema, por isso nao virou migration.
    """
    execute_query(
        "DELETE FROM _system_password_resets WHERE expires_at < now() - interval '1 day' RETURNING id"
    )


def public_base_url() -> str:
    """Public origin of the SPA, used to build the reset link.

    APP_BASE_URL wins when set; otherwise the origin comes from the request,
    honouring the forwarding headers set by the frontend nginx.
    """
    configured = os.getenv("APP_BASE_URL")
    if configured:
        return configured.rstrip("/")
    proto = request.headers.get("X-Forwarded-Proto") or request.scheme
    host = request.headers.get("X-Forwarded-Host") or request.host
    return proto + "://" + host


def looks_like_email(value) -> bool:
    return bool(value) and bool(_EMAIL_RE.match(value))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_reset_token(user_id: int, ip: Optional[str] = None) -> str:
    """Issue a single-use token, invalidating any outstanding one for the user.

    Returns the clear-text token; it is never stored and only travels in the e-mail.
    """
    token = secrets.token_urlsafe(32)
    params = {"uid": user_id, "th": _hash_token(token), "ttl": TOKEN_TTL_MINUTES, "ip": ip}
    with engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE _system_password_resets SET used_at = now() "
                "WHERE user_id = :uid AND used_at IS NULL"
            ),
            params,
        )
        conn.execute(
            text(
                "INSERT INTO _system_password_resets (user_id, token_hash, expires_at, ip) "
                "VALUES (:uid, :th, now() + make_interval(mins => :ttl), :ip)"
            ),
            params,
        )
        conn.commit()
    return token


def consume_reset_token(token) -> Optional[int]:
    """Atomically burn a token and return its user_id, or None if it is not usable.

    Lookup is by SHA-256 digest through a UNIQUE index. No constant-time compare is
    needed because the secret itself is never compared in Python — the attacker
    cannot observe or influence the stored digest.
    """
    if not token or not _TOKEN_RE.match(token):
        return None
    rows = execute_query(
        "UPDATE _system_password_resets SET used_at = now() "
        "WHERE token_hash = :th AND used_at IS NULL AND expires_at > now() "
        "RETURNING user_id",
        {"th": _hash_token(token)},
    )
    return rows[0]["user_id"] if rows else None


def reset_password(token, new_password) -> Optional[int]:
    """Validate, burn the token and set the new password. Returns the user id or None.

    Password validation happens first so a rejected password does not waste the
    token — the user can retry with the same link.
    """
    validate_new_password(new_password)
    user_id = consume_reset_token(token)
    if user_id is None:
        return None
    update_user(user_id, password=new_password)
    return user_id
