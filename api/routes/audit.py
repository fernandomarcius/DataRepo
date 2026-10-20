"""Consulta da trilha de auditoria e ingestao interna de eventos.

Os eventos do proprio api sao gravados na requisicao (services.audit_service.log_event).
O `ingestion`, que roda em outro container, envia os dele por
POST /internal/v1/events — rota que o nginx do web nao publica e que exige o token
interno.
"""
import sys

from flask import Blueprint, jsonify, request

from kit.auth import require_permission
from kit.internal import internal_only
from services.audit_service import (
    InvalidAuditEvent,
    get_log,
    get_logs,
    record_event,
)

bp = Blueprint("audit", __name__)


@bp.route('/internal/v1/events', methods=['POST'])
@internal_only
def ingest_event():
    try:
        event_id = record_event(request.get_json(silent=True))
        return jsonify({"id": event_id}), 201
    except InvalidAuditEvent as e:
        # 4xx: o cliente nao reenvia, e o evento fica no stderr dele.
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        # 5xx: o cliente tenta de novo antes de desistir.
        print(f"AUDIT INSERT ERROR: {e}", file=sys.stderr, flush=True)
        return jsonify({"error": "Internal server error"}), 500


@bp.route('/api/v1/audit-logs', methods=['GET'])
@require_permission('can_view_audit')
def list_audit_logs():
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 25))
        filters = {}
        for key in ('entity_type', 'action', 'user_id', 'from', 'to', 'q'):
            val = request.args.get(key)
            if val is not None:
                filters[key] = val
        if 'user_id' in filters:
            try:
                filters['user_id'] = int(filters['user_id'])
            except ValueError:
                return jsonify({"error": "user_id must be an integer"}), 400

        result = get_logs(filters, page=page, page_size=page_size)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/v1/audit-logs/<int:log_id>', methods=['GET'])
@require_permission('can_view_audit')
def get_audit_log(log_id):
    try:
        entry = get_log(log_id)
        if entry is None:
            return jsonify({"error": "Audit log entry not found"}), 404
        return jsonify(entry), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
