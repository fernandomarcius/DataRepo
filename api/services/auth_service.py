"""Authentication service.

Manages the _system_users table, password hashing and JWT issuance. Token
VERIFICATION and the route decorators live in the platform kit (kit/auth.py),
because every service verifies tokens but only this one issues them.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash as _generate_password_hash


def generate_password_hash(password: str) -> str:
    """Wrap werkzeug's generate_password_hash forcing pbkdf2 for Python 3.9 compat."""
    return _generate_password_hash(password, method="pbkdf2:sha256")


from db import execute_query  # noqa: E402 -- import depois do shim de hash definido acima
from kit.auth import (  # noqa: E402,F401 -- import depois do shim; reexporta a API de token do kit
    JWT_ALGORITHM,
    PERMISSION_FLAGS,
    decode_token,
    jwt_secret as _jwt_secret,
    login_required,
    normalize_perms as _normalize_perms,
    require_permission,
)

# Pre-computed dummy hash used to keep authenticate() constant-time when the
# username is unknown. The plaintext is random bytes nobody has access to, so
# this provides no timing oracle for real passwords. Format must match the
# hashes produced by ``generate_password_hash`` (pbkdf2:sha256), otherwise
# ``check_password_hash`` short-circuits and skips the work that protects
# against username-enumeration timing attacks.
_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_hex(32))

JWT_TTL_HOURS = 12

# Minimum length enforced on self-service password flows (reset by e-mail and
# "change my password"). Admin-driven create/update keep their current behaviour
# so this change does not break existing user management.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def validate_new_password(password):
    """Validate a user-chosen password. Raises ValueError with a client-safe message."""
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")


def seed_admin_user():
    count_row = execute_query("SELECT COUNT(*) AS c FROM _system_users")
    if count_row and count_row[0]["c"] > 0:
        return

    username = os.getenv("ADMIN_USERNAME")
    password = os.getenv("ADMIN_PASSWORD")
    if not username or not password:
        print(
            "WARN: _system_users empty but ADMIN_USERNAME/ADMIN_PASSWORD not set; "
            "no admin will be seeded",
            flush=True,
        )
        return

    try:
        create_user(
            username,
            password,
            {flag: True for flag in PERMISSION_FLAGS},  # includes can_view_audit
        )
        print("INFO: seeded initial admin user", flush=True)
    except Exception as e:
        if "unique" in str(e).lower():
            return  # already seeded by another process
        raise


def _row_to_user(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "perms": {flag: bool(row[flag]) for flag in PERMISSION_FLAGS},
        "created_at": row.get("created_at"),
    }


def get_user_by_id(user_id):
    rows = execute_query(
        "SELECT id, username, can_query, can_upload, can_manage_views, "
        "can_manage_functions, can_manage_users, can_view_audit, can_manage_connections, created_at "
        "FROM _system_users WHERE id = :id",
        {"id": user_id},
    )
    return _row_to_user(rows[0]) if rows else None


def get_user_by_username(username):
    rows = execute_query(
        "SELECT id, username, can_query, can_upload, can_manage_views, "
        "can_manage_functions, can_manage_users, can_view_audit, can_manage_connections, created_at "
        "FROM _system_users WHERE username = :username",
        {"username": username},
    )
    return _row_to_user(rows[0]) if rows else None


def authenticate(username, password):
    rows = execute_query(
        "SELECT id, username, password_hash, can_query, can_upload, "
        "can_manage_views, can_manage_functions, can_manage_users, can_view_audit, "
        "can_manage_connections, created_at "
        "FROM _system_users WHERE username = :username",
        {"username": username},
    )
    if not rows:
        check_password_hash(_DUMMY_PASSWORD_HASH, password)
        return None
    row = rows[0]
    if not check_password_hash(row["password_hash"], password):
        return None
    return _row_to_user(row)


def issue_token(user):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "perms": user["perms"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=JWT_TTL_HOURS)).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def list_users():
    rows = execute_query(
        "SELECT id, username, can_query, can_upload, can_manage_views, "
        "can_manage_functions, can_manage_users, can_view_audit, can_manage_connections, created_at "
        "FROM _system_users ORDER BY id"
    )
    return [_row_to_user(row) for row in (rows or [])]


def create_user(username, password, perms):
    if not username or not password:
        raise ValueError("username and password are required")
    perms = _normalize_perms(perms)
    rows = execute_query(
        "INSERT INTO _system_users (username, password_hash, can_query, "
        "can_upload, can_manage_views, can_manage_functions, can_manage_users, "
        "can_view_audit, can_manage_connections) "
        "VALUES (:username, :pwd, :can_query, :can_upload, "
        ":can_manage_views, :can_manage_functions, :can_manage_users, "
        ":can_view_audit, :can_manage_connections) "
        "RETURNING id, username, can_query, can_upload, can_manage_views, "
        "can_manage_functions, can_manage_users, can_view_audit, can_manage_connections, created_at",
        {
            "username": username,
            "pwd": generate_password_hash(password),
            **perms,
        },
    )
    return _row_to_user(rows[0]) if rows else None


def update_user(user_id, username=None, password=None, perms=None):
    sets = []
    params = {"id": user_id}
    if username is not None:
        sets.append("username = :username")
        params["username"] = username
    if password:
        sets.append("password_hash = :pwd")
        params["pwd"] = generate_password_hash(password)
    if perms is not None:
        normalized = _normalize_perms(perms)
        for flag, value in normalized.items():
            sets.append(f"{flag} = :{flag}")
            params[flag] = value
    if not sets:
        return get_user_by_id(user_id)

    rows = execute_query(
        f"UPDATE _system_users SET {', '.join(sets)} WHERE id = :id "
        "RETURNING id, username, can_query, can_upload, can_manage_views, "
        "can_manage_functions, can_manage_users, can_view_audit, can_manage_connections, created_at",
        params,
    )
    return _row_to_user(rows[0]) if rows else None


def count_admins():
    rows = execute_query(
        "SELECT COUNT(*) AS c FROM _system_users WHERE can_manage_users = TRUE"
    )
    return rows[0]["c"] if rows else 0


def delete_user(user_id):
    rows = execute_query(
        "DELETE FROM _system_users WHERE id = :id RETURNING id",
        {"id": user_id},
    )
    return rows[0] if rows else None
