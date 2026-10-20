"""Consultas SQL ad-hoc, read-only.

Em producao este blueprint e atendido por um container proprio (`api-query`,
mesma imagem): o nginx do web manda /api/v1/query para ele, e uma consulta de 4
minutos nao ocupa os workers que atendem login e cadastros. Nao e dono de
nenhuma tabela: so le, dentro de transacao READ ONLY.
"""
from flask import Blueprint, jsonify, request

from db import execute_readonly_query
from kit.auth import require_permission
from kit.sql_guard import ReadOnlySQLError, validate_readonly_sql

bp = Blueprint("query", __name__)


@bp.route('/api/v1/query', methods=['POST'])
@require_permission('can_query')
def run_query():
    data = request.get_json(silent=True) or {}
    sql = data.get('sql')

    if not sql:
        return jsonify({"error": "SQL query is required"}), 400

    try:
        sql = validate_readonly_sql(sql)
        results = execute_readonly_query(sql)
        return jsonify({"results": results}), 200
    except ReadOnlySQLError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500
