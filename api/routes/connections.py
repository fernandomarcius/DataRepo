"""Conexoes com bancos externos via FDW (tds_fdw, postgres_fdw).

Dono de `_system_connections`, dos SERVERs/USER MAPPINGs e dos schemas
`ext_<conexao>`. Unico dominio que usa CONNECTIONS_ENCRYPTION_KEY.
"""
from flask import Blueprint, g, jsonify, request

from kit.auth import login_required, require_permission
from services.audit_service import log_event
from services.connection_service import (
    ConnectionValidationError,
    create_connection,
    delete_connection,
    get_connection,
    get_foreign_table_schema,
    list_connection_catalog,
    list_connections,
    list_foreign_tables,
    safe_connection_error,
    sync_connection,
    test_connection,
    update_connection,
)

bp = Blueprint("connections", __name__)


@bp.route('/api/v1/connections', methods=['GET'])
@login_required
def connections_list():
    try:
        perms = g.current_user.get("perms", {})
        if perms.get("can_manage_connections"):
            return jsonify({"connections": list_connections()}), 200
        if perms.get("can_query"):
            return jsonify({"connections": list_connection_catalog()}), 200
        return jsonify({"error": "Forbidden"}), 403
    except Exception as e:
        return jsonify({"error": safe_connection_error(e)}), 500


@bp.route('/api/v1/connections/<int:connection_id>', methods=['GET'])
@require_permission('can_manage_connections')
def connections_get(connection_id):
    try:
        conn = get_connection(connection_id)
        if not conn:
            return jsonify({"error": "Connection not found"}), 404
        return jsonify(conn), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/v1/connections', methods=['POST'])
@require_permission('can_manage_connections')
def connections_create():
    data = request.json or {}
    try:
        connection = create_connection(data)
        log_event("CREATE", "connection", str(connection["id"]), after=connection)
        return jsonify(connection), 201
    except ConnectionValidationError as e:
        log_event("CREATE", "connection", data.get("name"), status="failed", error=str(e))
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        msg = safe_connection_error(e, data.get("password"))
        log_event("CREATE", "connection", data.get("name"), status="failed", error=msg)
        return jsonify({"error": msg}), 500


@bp.route('/api/v1/connections/<int:connection_id>', methods=['PUT'])
@require_permission('can_manage_connections')
def connections_update(connection_id):
    data = request.json or {}
    before = get_connection(connection_id)
    try:
        connection = update_connection(connection_id, data)
        if not connection:
            return jsonify({"error": "Connection not found"}), 404
        log_event("UPDATE", "connection", str(connection_id), before=before, after=connection)
        return jsonify(connection), 200
    except ConnectionValidationError as e:
        log_event("UPDATE", "connection", str(connection_id), before=before, status="failed", error=str(e))
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        msg = safe_connection_error(e, data.get("password"))
        log_event("UPDATE", "connection", str(connection_id), before=before, status="failed", error=msg)
        return jsonify({"error": msg}), 500


@bp.route('/api/v1/connections/<int:connection_id>', methods=['DELETE'])
@require_permission('can_manage_connections')
def connections_delete(connection_id):
    before = get_connection(connection_id)
    try:
        deleted = delete_connection(connection_id)
        if not deleted:
            return jsonify({"error": "Connection not found"}), 404
        log_event("DELETE", "connection", str(connection_id), before=before)
        return jsonify({"message": "Connection deleted"}), 200
    except Exception as e:
        msg = safe_connection_error(e)
        log_event("DELETE", "connection", str(connection_id), before=before, status="failed", error=msg)
        return jsonify({"error": msg}), 500


@bp.route('/api/v1/connections/test', methods=['POST'])
@require_permission('can_manage_connections')
def connections_test():
    data = request.json or {}
    try:
        result = test_connection(data)
        return jsonify(result), 200
    except ConnectionValidationError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": safe_connection_error(e, data.get("password"))}), 400


@bp.route('/api/v1/connections/<int:connection_id>/sync', methods=['POST'])
@require_permission('can_manage_connections')
def connections_sync(connection_id):
    try:
        result = sync_connection(connection_id)
        if not result:
            return jsonify({"error": "Connection not found"}), 404
        log_event("SYNC", "connection", str(connection_id), after=result)
        return jsonify(result), 200
    except Exception as e:
        msg = safe_connection_error(e)
        log_event("SYNC", "connection", str(connection_id), status="failed", error=msg)
        return jsonify({"error": msg}), 500


@bp.route('/api/v1/connections/<int:connection_id>/tables', methods=['GET'])
@require_permission('can_query')
def connections_tables(connection_id):
    try:
        tables = list_foreign_tables(connection_id)
        if tables is None:
            return jsonify({"error": "Connection not found"}), 404
        return jsonify({"tables": tables}), 200
    except Exception as e:
        return jsonify({"error": safe_connection_error(e)}), 500


@bp.route('/api/v1/connections/<int:connection_id>/tables/<table_name>/schema', methods=['GET'])
@require_permission('can_query')
def connections_table_schema(connection_id, table_name):
    try:
        schema = get_foreign_table_schema(connection_id, table_name)
        if schema is None:
            return jsonify({"error": "Connection not found"}), 404
        return jsonify({"schema": schema}), 200
    except Exception as e:
        return jsonify({"error": safe_connection_error(e)}), 500
