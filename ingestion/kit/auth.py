"""Verificacao de JWT e decorators de autorizacao, comuns ao api e ao ingestion.

Somente o api EMITE token (services/auth_service.py). api e ingestion o
VERIFICAM com o segredo compartilhado `JWT_SECRET` (HS256), sem consultar o
banco: o payload ja carrega id, username e as flags de permissao. E o mesmo
contrato do monolito, so que agora cruzando a fronteira de processo.

Adicionar uma flag de permissao exige atualizar PERMISSION_FLAGS aqui e
propagar o kit para o ingestion (copia manual) — com a lista antiga ele
descarta a flag nova ao normalizar o token.
"""
import os
from functools import wraps
from typing import Optional

import jwt
from flask import g, jsonify, request

PERMISSION_FLAGS = (
    "can_query",
    "can_upload",
    "can_manage_views",
    "can_manage_functions",
    "can_manage_users",
    "can_view_audit",
    "can_manage_connections",
)

JWT_ALGORITHM = "HS256"

_JWT_SECRET: Optional[str] = None


def jwt_secret() -> str:
    global _JWT_SECRET
    if _JWT_SECRET is None:
        secret = os.getenv("JWT_SECRET")
        if not secret:
            raise RuntimeError("JWT_SECRET environment variable is required")
        _JWT_SECRET = secret
    return _JWT_SECRET


def decode_token(token):
    return jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])


def normalize_perms(perms):
    perms = perms or {}
    return {flag: bool(perms.get(flag, False)) for flag in PERMISSION_FLAGS}


def _extract_token():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    return header[len("Bearer "):].strip() or None


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _extract_token()
        if not token:
            return jsonify({"error": "Unauthorized"}), 401
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        g.current_user = {
            "id": int(payload.get("sub")),
            "username": payload.get("username"),
            "perms": normalize_perms(payload.get("perms")),
        }
        return fn(*args, **kwargs)

    return wrapper


def require_permission(flag):
    if flag not in PERMISSION_FLAGS:
        raise ValueError(f"Unknown permission flag: {flag}")

    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if not g.current_user["perms"].get(flag):
                return jsonify({"error": "Forbidden"}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator
