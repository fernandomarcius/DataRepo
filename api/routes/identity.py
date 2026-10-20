"""Rotas de autenticacao, usuarios e redefinicao de senha.

Unico ponto que EMITE o JWT e le/escreve `_system_users` e
`_system_password_resets`. Os demais dominios so verificam o token (kit/auth.py).
"""
import html
import threading

from flask import Blueprint, g, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from services.audit_service import log_event
from services.auth_service import (
    PERMISSION_FLAGS,
    authenticate,
    count_admins,
    create_user,
    delete_user,
    get_user_by_id,
    get_user_by_username,
    issue_token,
    list_users,
    login_required,
    require_permission,
    update_user,
    validate_new_password,
)
from services.email_service import send_email
from services.password_reset_service import (
    TOKEN_TTL_MINUTES,
    create_reset_token,
    looks_like_email,
    public_base_url,
    reset_password,
)

bp = Blueprint("identity", __name__)
# Ligado ao app em app.py (limiter.init_app). Memoria local por processo: o
# limite vale por worker do gunicorn, como no monolito.
limiter = Limiter(get_remote_address, default_limits=[], storage_uri="memory://")


@bp.route('/api/v1/auth/login', methods=['POST'])
@limiter.limit("10 per minute")
def auth_login():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = authenticate(username, password)
    if not user:
        log_event(
            "LOGIN", "session", username,
            status="failed",
            error="Invalid credentials",
            metadata={"ip": request.remote_addr, "user_agent": request.headers.get("User-Agent")},
        )
        return jsonify({"error": "Invalid credentials"}), 401

    # Set g.current_user so log_event can read it
    g.current_user = user
    try:
        token = issue_token(user)
    except Exception as e:
        log_event(
            "LOGIN", "session", username,
            status="failed",
            error=f"Token issuance failed: {e}",
            metadata={"ip": request.remote_addr, "user_agent": request.headers.get("User-Agent")},
        )
        return jsonify({"error": "Internal server error"}), 500

    log_event(
        "LOGIN", "session", username,
        status="success",
        metadata={"ip": request.remote_addr, "user_agent": request.headers.get("User-Agent")},
    )

    return jsonify({"token": token, "user": user}), 200


@bp.route('/api/v1/auth/me', methods=['GET'])
@login_required
def auth_me():
    user = get_user_by_id(g.current_user["id"])
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user), 200


GENERIC_RESET_RESPONSE = {"message": "If the account exists, a reset link has been sent"}


def _reset_email_body(username, link):
    safe_user = html.escape(username)
    safe_link = html.escape(link)
    text_body = (
        f"Ola, {username}.\n\n"
        "Recebemos um pedido para redefinir a senha da sua conta no Data App.\n"
        f"Acesse o link abaixo para cadastrar uma nova senha (valido por {TOKEN_TTL_MINUTES} minutos):\n\n"
        f"{link}\n\n"
        "Se voce nao pediu a redefinicao, ignore esta mensagem: sua senha continua a mesma.\n"
    )
    html_body = (
        "<html><body style=\"font-family: Arial, sans-serif; color: #1e293b;\">"
        f"<p>Ola, {safe_user}.</p>"
        "<p>Recebemos um pedido para redefinir a senha da sua conta no <strong>Data App</strong>.</p>"
        f"<p><a href=\"{safe_link}\">Cadastrar uma nova senha</a> "
        f"(link valido por {TOKEN_TTL_MINUTES} minutos).</p>"
        f"<p style=\"font-size: 12px; color: #64748b;\">{safe_link}</p>"
        "<p>Se voce nao pediu a redefinicao, ignore esta mensagem: sua senha continua a mesma.</p>"
        "</body></html>"
    )
    return text_body, html_body


def _send_reset_email_async(username, link, ip, user_agent):
    """Deliver the reset e-mail off the request thread.

    Sending inline would make a request for an existing account take seconds while
    an unknown one returns instantly, which is a username-enumeration oracle, and
    would tie up a gunicorn worker for the whole SMTP round trip.
    """
    text_body, html_body = _reset_email_body(username, link)
    metadata = {"ip": ip, "user_agent": user_agent}

    def _run():
        try:
            send_email(username, "Data App - redefinicao de senha", text_body, html_body)
            log_event(
                "PASSWORD_RESET_REQUEST", "user", username,
                status="success", metadata=metadata,
            )
        except Exception as e:
            log_event(
                "PASSWORD_RESET_REQUEST", "user", username,
                status="failed", error=f"Email delivery failed: {e}", metadata=metadata,
            )

    threading.Thread(target=_run, daemon=True).start()


@bp.route('/api/v1/auth/forgot-password', methods=['POST'])
@limiter.limit("5 per minute")
def auth_forgot_password():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    if not username:
        return jsonify({"error": "Username is required"}), 400

    ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")
    metadata = {"ip": ip, "user_agent": user_agent}

    # Every branch below answers exactly the same, so the response never reveals
    # whether the account exists.
    if not looks_like_email(username):
        log_event(
            "PASSWORD_RESET_REQUEST", "user", username,
            status="failed", error="Username is not an email address", metadata=metadata,
        )
        return jsonify(GENERIC_RESET_RESPONSE), 200

    user = get_user_by_username(username)
    if not user:
        log_event(
            "PASSWORD_RESET_REQUEST", "user", username,
            status="failed", error="Unknown user", metadata=metadata,
        )
        return jsonify(GENERIC_RESET_RESPONSE), 200

    try:
        token = create_reset_token(user["id"], ip)
        # The link carries the token, so it must never reach the audit log.
        link = f"{public_base_url()}/reset-password/{token}"
        _send_reset_email_async(username, link, ip, user_agent)
    except Exception as e:
        log_event(
            "PASSWORD_RESET_REQUEST", "user", username,
            status="failed", error=str(e), metadata=metadata,
        )

    return jsonify(GENERIC_RESET_RESPONSE), 200


@bp.route('/api/v1/auth/reset-password', methods=['POST'])
@limiter.limit("10 per minute")
def auth_reset_password():
    data = request.json or {}
    token = data.get('token')
    password = data.get('password')
    if not token or not password:
        return jsonify({"error": "Token and password are required"}), 400

    try:
        user_id = reset_password(token, password)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log_event("PASSWORD_RESET", "user", None, status="failed", error=str(e))
        return jsonify({"error": "Internal server error"}), 500

    if user_id is None:
        # 400 and not 401: the frontend interceptor treats 401 as "session died"
        # and wipes the stored token.
        log_event(
            "PASSWORD_RESET", "user", None,
            status="failed", error="Invalid or expired token",
            metadata={"ip": request.remote_addr},
        )
        return jsonify({"error": "Invalid or expired token"}), 400

    # Set g.current_user so the audit entry names the account that changed.
    g.current_user = get_user_by_id(user_id)
    log_event(
        "PASSWORD_RESET", "user", str(user_id),
        status="success", metadata={"ip": request.remote_addr},
    )
    return jsonify({"message": "Password updated"}), 200


@bp.route('/api/v1/auth/change-password', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def auth_change_password():
    data = request.json or {}
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    if not current_password or not new_password:
        return jsonify({"error": "Current and new password are required"}), 400

    try:
        validate_new_password(new_password)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    user_id = g.current_user["id"]
    username = g.current_user["username"]

    # The username is never taken from the body: only an admin can rename an account.
    if not authenticate(username, current_password):
        log_event(
            "PASSWORD_CHANGE", "user", str(user_id),
            status="failed", error="Invalid current password",
        )
        return jsonify({"error": "Current password is incorrect"}), 400

    try:
        update_user(user_id, password=new_password)
    except Exception as e:
        log_event("PASSWORD_CHANGE", "user", str(user_id), status="failed", error=str(e))
        return jsonify({"error": "Internal server error"}), 500

    log_event("PASSWORD_CHANGE", "user", str(user_id), status="success")
    return jsonify({"message": "Password updated"}), 200


@bp.route('/api/v1/users', methods=['GET'])
@require_permission('can_manage_users')
def users_list():
    return jsonify({"users": list_users()}), 200


@bp.route('/api/v1/users', methods=['POST'])
@require_permission('can_manage_users')
def users_create():
    data = request.json or {}
    try:
        user = create_user(
            data.get('username'),
            data.get('password'),
            {flag: data.get(flag, False) for flag in PERMISSION_FLAGS},
        )
        log_event("CREATE", "user", str(user["id"]), after=user)
        return jsonify(user), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        msg = str(e)
        log_event("CREATE", "user", None, status="failed", error=msg)
        if 'unique' in msg.lower():
            return jsonify({"error": "Username already exists"}), 409
        return jsonify({"error": "Internal server error"}), 500


@bp.route('/api/v1/users/<int:user_id>', methods=['PUT'])
@require_permission('can_manage_users')
def users_update(user_id):
    data = request.json or {}
    target = get_user_by_id(user_id)
    if not target:
        return jsonify({"error": "User not found"}), 404

    before = get_user_by_id(user_id)

    perms = None
    if any(flag in data for flag in PERMISSION_FLAGS):
        perms = {flag: data.get(flag, target["perms"][flag]) for flag in PERMISSION_FLAGS}
        # Don't let an admin demote themselves and leave the system without admins
        if (
            user_id == g.current_user["id"]
            and target["perms"]["can_manage_users"]
            and not perms["can_manage_users"]
            and count_admins() <= 1
        ):
            return jsonify({"error": "Cannot remove your own admin permission as the last admin"}), 400

    try:
        user = update_user(
            user_id,
            username=data.get('username'),
            password=data.get('password') or None,
            perms=perms,
        )
        log_event("UPDATE", "user", str(user_id), before=before, after=user)
        return jsonify(user), 200
    except Exception as e:
        msg = str(e)
        log_event("UPDATE", "user", str(user_id), before=before, status="failed", error=msg)
        if 'unique' in msg.lower():
            return jsonify({"error": "Username already exists"}), 409
        return jsonify({"error": "Internal server error"}), 500


@bp.route('/api/v1/users/<int:user_id>', methods=['DELETE'])
@require_permission('can_manage_users')
def users_delete(user_id):
    if user_id == g.current_user["id"]:
        return jsonify({"error": "You cannot delete your own user"}), 400
    target = get_user_by_id(user_id)
    if not target:
        return jsonify({"error": "User not found"}), 404
    if target["perms"]["can_manage_users"] and count_admins() <= 1:
        return jsonify({"error": "Cannot delete the last admin"}), 400

    before = get_user_by_id(user_id)
    try:
        delete_user(user_id)
        log_event("DELETE", "user", str(user_id), before=before)
        return jsonify({"message": "User deleted"}), 200
    except Exception as e:
        msg = str(e)
        log_event("DELETE", "user", str(user_id), before=before, status="failed", error=msg)
        return jsonify({"error": "Internal server error"}), 500
