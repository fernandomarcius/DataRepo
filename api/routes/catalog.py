"""Ciclo de vida dos objetos de dados do schema local.

Tabelas (listar, schema, renomear, apagar), views (redefinir com cascata de
dependentes), relatorios salvos (que SAO views) e views materializadas com
refresh agendado no pg_cron. Mudam o mesmo grafo de dependencias do Postgres:
renomear uma view precisa renomear a materializacao e o relatorio que a
descrevem, na mesma operacao.
"""
from flask import Blueprint, g, jsonify, request

from db import execute_readonly_query
from kit.auth import login_required, require_permission
from kit.sql_guard import ReadOnlySQLError, validate_readonly_sql
from services.audit_service import log_event
from services.data_object_service import (
    delete_data_object,
    get_aliases_for_table,
    get_table_schema,
    get_tables,
    rename_data_object,
)
from services.materialized_view_service import (
    RefreshInProgress,
    materialize_view,
    refresh_now,
    unmaterialize_view,
)
from services.report_service import (
    create_report,
    delete_report,
    get_all_reports,
    get_report,
    sync_report_name_for_view_rename,
    update_report,
)
from services.view_service import smart_update_view

bp = Blueprint("catalog", __name__)


@bp.route('/api/v1/tables', methods=['GET'])
@login_required
def list_tables():
    try:
        tables = get_tables()
        return jsonify({"tables": tables}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/v1/tables/<table_name>/schema', methods=['GET'])
@login_required
def get_schema(table_name):
    try:
        schema = get_table_schema(table_name)
        aliases = get_aliases_for_table(table_name)
        # alias_by_physical maps physical_column -> alias (long original name)
        alias_by_physical = {v: k for k, v in aliases.items()}
        for col in schema:
            col['alias'] = alias_by_physical.get(col['column_name'])
        return jsonify({"schema": schema}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/v1/tables/<table_name>', methods=['PUT'])
@require_permission('can_manage_views')
def rename_table_or_view(table_name):
    data = request.json or {}
    new_name = data.get('new_name')
    if not new_name:
        return jsonify({"error": "New name is required"}), 400

    try:
        result = rename_data_object(table_name, new_name)
        if not result:
            return jsonify({"error": "Table or view not found"}), 404
        synced_report = None
        if result["type"] in ("view", "materialized_view"):
            synced_report = sync_report_name_for_view_rename(table_name, result["name"])
        log_event(
            "RENAME", result["type"], table_name,
            before={"name": table_name},
            after={"name": result["name"], "synced_report": synced_report},
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log_event("RENAME", "table", table_name, status="failed", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@bp.route('/api/v1/tables/<table_name>', methods=['DELETE'])
@require_permission('can_manage_views')
def delete_table_or_view(table_name):
    try:
        result = delete_data_object(table_name)
        if not result:
            return jsonify({"error": "Table or view not found"}), 404
        log_event("DELETE", result["type"], table_name, before={"name": table_name})
        return jsonify({"message": f"{result['type'].title()} deleted", **result}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log_event("DELETE", "table", table_name, status="failed", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@bp.route('/api/v1/reports', methods=['GET'])
@login_required
def list_reports():
    try:
        reports = get_all_reports()
        return jsonify({"reports": reports}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/v1/reports', methods=['POST'])
@require_permission('can_manage_views')
def add_report():
    data = request.json
    if not data.get('name') or not data.get('sql_query'):
        return jsonify({"error": "Name and SQL query are required"}), 400

    try:
        report = create_report(data.get('name'), data.get('description'), data.get('sql_query'))
        log_event("CREATE", "report", str(report["id"]), after=report)
        return jsonify(report), 201
    except Exception as e:
        log_event("CREATE", "report", None, status="failed", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@bp.route('/api/v1/reports/<int:report_id>', methods=['PUT'])
@require_permission('can_manage_views')
def update_report_endpoint(report_id):
    data = request.json
    if not data.get('name') or not data.get('sql_query'):
        return jsonify({"error": "Name and SQL query are required"}), 400

    before = get_report(report_id)

    try:
        report = update_report(report_id, data.get('name'), data.get('description'), data.get('sql_query'))
        if report:
            log_event("UPDATE", "report", str(report_id), before=before, after=report)
            return jsonify(report), 200
        return jsonify({"error": "Report not found"}), 404
    except Exception as e:
        log_event("UPDATE", "report", str(report_id), before=before, status="failed", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@bp.route('/api/v1/reports/<int:report_id>', methods=['DELETE'])
@require_permission('can_manage_views')
def remove_report(report_id):
    before = get_report(report_id)
    try:
        result = delete_report(report_id)
        if result:
            log_event("DELETE", "report", str(report_id), before=before)
            return jsonify({"message": "Report deleted"}), 200
        return jsonify({"error": "Report not found"}), 404
    except Exception as e:
        log_event("DELETE", "report", str(report_id), before=before, status="failed", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@bp.route('/api/v1/reports/<int:report_id>/materialize', methods=['POST'])
@require_permission('can_manage_views')
def materialize_report(report_id):
    report = get_report(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    schedule = (request.json or {}).get('schedule')
    try:
        result = materialize_view(
            report['view_name'],
            report['sql_query'],
            schedule,
            g.current_user.get("username"),
            report_id=report_id,
        )
        if result.get("status") == "already_materialized":
            return jsonify(result), 409
        log_event("MATERIALIZE", "report", str(report_id), after=result)
        return jsonify(result), 202
    except ValueError as e:
        # Bad schedule / dependent views exist.
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log_event("MATERIALIZE", "report", str(report_id), status="failed", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@bp.route('/api/v1/reports/<int:report_id>/materialize', methods=['DELETE'])
@require_permission('can_manage_views')
def unmaterialize_report(report_id):
    report = get_report(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    try:
        result = unmaterialize_view(report['view_name'], report['sql_query'])
        log_event("UNMATERIALIZE", "report", str(report_id), after=result)
        return jsonify(result), 200
    except Exception as e:
        log_event("UNMATERIALIZE", "report", str(report_id), status="failed", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@bp.route('/api/v1/reports/<int:report_id>/refresh', methods=['POST'])
@require_permission('can_manage_views')
def refresh_report(report_id):
    report = get_report(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    try:
        result = refresh_now(report['view_name'])
        log_event("REFRESH", "report", str(report_id), after=result)
        return jsonify(result), 202
    except RefreshInProgress as e:
        return jsonify({"error": str(e)}), 409
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log_event("REFRESH", "report", str(report_id), status="failed", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@bp.route('/api/v1/reports/<int:report_id>/execute', methods=['GET'])
@login_required
def execute_report(report_id):
    try:
        report = get_report(report_id)
        if not report:
            return jsonify({"error": "Report not found"}), 404

        results = execute_readonly_query(validate_readonly_sql(report['sql_query']))
        return jsonify({"results": results, "report": report}), 200
    except ReadOnlySQLError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/v1/views/<view_name>', methods=['PUT'])
@require_permission('can_manage_views')
def update_view(view_name):
    """
    Smart update of a view with automatic dependency handling.
    Optionally renames the view if new_name is provided.
    Request body: { "definition": "SELECT ... FROM ...", "new_name": "optional_new_name" }
    """
    data = request.json
    definition = data.get('definition')
    new_name = data.get('new_name')

    if not definition:
        return jsonify({"error": "View definition is required"}), 400

    try:
        result = smart_update_view(view_name, definition, new_name)
        if result.get('success'):
            old_def = result.get('old_definition')
            action = "RENAME" if new_name else "UPDATE"
            log_event(
                action, "view", view_name,
                before={"definition": old_def} if old_def else None,
                after={"definition": definition, "name": new_name or view_name},
            )
            return jsonify(result), 200
        else:
            return jsonify(result), 400
    except Exception as e:
        log_event(
            "RENAME" if new_name else "UPDATE", "view", view_name,
            status="failed",
            error=str(e),
        )
        return jsonify({"error": "Internal server error"}), 500
