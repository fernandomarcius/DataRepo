"""Funcoes SQL gerenciadas (CREATE FUNCTION no schema local).

Dono de `_system_functions` e das funcoes que ela descreve.
"""
from flask import Blueprint, g, jsonify, request

from kit.auth import login_required, require_permission
from services.audit_service import log_event
from services.function_service import (
    FunctionValidationError,
    create_function,
    delete_function,
    get_function,
    list_functions,
    update_function as update_managed_function,
    validate_function_definition,
)

bp = Blueprint("functions", __name__)


@bp.route('/api/v1/functions', methods=['GET'])
@login_required
def functions_list():
    try:
        include_body = bool(g.current_user["perms"].get("can_manage_functions"))
        return jsonify({"functions": list_functions(include_body=include_body)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/v1/functions/<int:function_id>', methods=['GET'])
@require_permission('can_manage_functions')
def functions_get(function_id):
    try:
        function = get_function(function_id, include_body=True)
        if not function:
            return jsonify({"error": "Function not found"}), 404
        return jsonify(function), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/v1/functions/validate', methods=['POST'])
@require_permission('can_manage_functions')
def functions_validate():
    try:
        result = validate_function_definition(request.json or {})
        return jsonify(result), 200
    except FunctionValidationError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route('/api/v1/functions', methods=['POST'])
@require_permission('can_manage_functions')
def functions_create():
    data = request.json or {}
    try:
        function = create_function(data)
        log_event("CREATE", "function", str(function["id"]), after=function)
        return jsonify(function), 201
    except FunctionValidationError as e:
        log_event(
            "CREATE", "function", None,
            status="failed", error=str(e),
            metadata={"name": data.get("name")},
        )
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log_event(
            "CREATE", "function", None,
            status="failed", error=str(e),
            metadata={"name": data.get("name")},
        )
        return jsonify({"error": str(e)}), 500


@bp.route('/api/v1/functions/<int:function_id>', methods=['PUT'])
@require_permission('can_manage_functions')
def functions_update(function_id):
    data = request.json or {}
    before = get_function(function_id, include_body=True)
    try:
        function = update_managed_function(function_id, data)
        if not function:
            return jsonify({"error": "Function not found"}), 404
        log_event("UPDATE", "function", str(function_id), before=before, after=function)
        return jsonify(function), 200
    except FunctionValidationError as e:
        log_event("UPDATE", "function", str(function_id), before=before, status="failed", error=str(e))
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log_event("UPDATE", "function", str(function_id), before=before, status="failed", error=str(e))
        return jsonify({"error": str(e)}), 500


@bp.route('/api/v1/functions/<int:function_id>', methods=['DELETE'])
@require_permission('can_manage_functions')
def functions_delete(function_id):
    before = get_function(function_id, include_body=True)
    try:
        function = delete_function(function_id)
        if not function:
            return jsonify({"error": "Function not found"}), 404
        log_event("DELETE", "function", str(function_id), before=before)
        return jsonify({"message": "Function deleted"}), 200
    except Exception as e:
        log_event("DELETE", "function", str(function_id), before=before, status="failed", error=str(e))
        return jsonify({"error": str(e)}), 500
