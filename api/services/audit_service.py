"""Universal Audit Log service.

Owns the audit_log table (schema in migrations/): event recording and queries.

Two ways in:
- log_event(): used by every route of this api. Same contract as the monolith —
  synchronous INSERT in the request, NEVER raises (audit must not break the
  business operation).
- record_event(): server side of POST /internal/v1/events, used by the
  `ingestion` service through kit/audit_client.py. It re-applies redaction and
  the 64 KB truncation, and DOES raise on a database error so the remote client
  gets a non-2xx answer and retries.
"""
import json
import sys
from typing import Any, Optional

from db import execute_query
from kit.audit_client import build_event
from kit.serialization import convert_to_serializable


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

_SENSITIVE_KEYS = {"password", "password_hash", "token", "secret"}


def redact(obj: Any) -> Any:
    """Recursively redact sensitive keys from dicts/lists."""
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if k.lower() in _SENSITIVE_KEYS else redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact(item) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# JSON serialization with truncation
# ---------------------------------------------------------------------------

TRUNCATE_LIMIT = 64 * 1024  # 64 KB — see spec.md Edge Cases


def _json_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        safe = redact(convert_to_serializable(value))
        return json.dumps(safe, separators=(',', ':'), ensure_ascii=False)
    except TypeError:
        safe = redact(value)
        return json.dumps(safe, separators=(',', ':'), ensure_ascii=False)


def _to_json(obj: Any, enriched_meta: Optional[dict] = None, field_name: Optional[str] = None) -> Optional[str]:
    """Serialize a Python object to JSON, redacting sensitive keys and
    truncating payloads above ``TRUNCATE_LIMIT``. When truncation kicks in
    and ``enriched_meta`` / ``field_name`` are provided, the metadata dict
    is mutated in place to record ``<field>_truncated`` and
    ``<field>_original_size`` so callers can persist that signal.
    """
    if obj is None:
        return None
    serialized = _json_or_none(obj)
    if len(serialized) > TRUNCATE_LIMIT:
        if enriched_meta is not None and field_name:
            enriched_meta[f"{field_name}_truncated"] = True
            enriched_meta[f"{field_name}_original_size"] = len(serialized)
        return json.dumps({"truncated": True, "original_size": len(serialized)})
    return serialized


# ---------------------------------------------------------------------------
# record_event
# ---------------------------------------------------------------------------

class InvalidAuditEvent(ValueError):
    """The event payload is missing required fields or has the wrong shape."""


_REQUIRED_TEXT_FIELDS = ("action", "entity_type")


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise InvalidAuditEvent("user_id must be an integer")


def record_event(event: dict) -> Optional[int]:
    """Persist one event received from another service. Returns the new id."""
    if not isinstance(event, dict):
        raise InvalidAuditEvent("event must be a JSON object")
    for field in _REQUIRED_TEXT_FIELDS:
        if not isinstance(event.get(field), str) or not event[field].strip():
            raise InvalidAuditEvent(f"{field} is required")
    metadata = event.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise InvalidAuditEvent("metadata must be an object")

    enriched_meta: dict = dict(metadata or {})
    if event.get("source"):
        enriched_meta.setdefault("source_service", event["source"])

    # Serialize before/after FIRST so any truncation flags land in
    # enriched_meta before metadata itself is dumped.
    before_state = _to_json(event.get("before"), enriched_meta, "before_state")
    after_state = _to_json(event.get("after"), enriched_meta, "after_state")
    entity_id = event.get("entity_id")

    rows = execute_query(
        """
        INSERT INTO audit_log
            (user_id, username, action, entity_type, entity_id,
             before_state, after_state, metadata, status, error)
        VALUES
            (:user_id, :username, :action, :entity_type, :entity_id,
             CAST(:before_state AS jsonb), CAST(:after_state AS jsonb), CAST(:metadata AS jsonb),
             :status, :error)
        RETURNING id
        """,
        {
            "user_id": _optional_int(event.get("user_id")),
            "username": event.get("username"),
            "action": event["action"],
            "entity_type": event["entity_type"],
            "entity_id": str(entity_id) if entity_id is not None else None,
            "before_state": before_state,
            "after_state": after_state,
            "metadata": _json_or_none(enriched_meta) if enriched_meta else None,
            "status": event.get("status") or "success",
            "error": event.get("error"),
        },
    )
    return rows[0]["id"] if rows else None


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def get_logs(filters: dict, page: int = 1, page_size: int = 50) -> dict:
    """
    Returns paginated audit log entries.

    Supported filters: entity_type, action, user_id, from (ISO ts), to (ISO ts),
    q (ILIKE on entity_id and username).
    """
    page_size = min(page_size, 100)
    page = max(page, 1)
    offset = (page - 1) * page_size

    where_clauses = []
    params: dict = {}

    if filters.get("action") != "LOGIN":
        where_clauses.append("action != 'LOGIN'")

    if filters.get("entity_type"):
        where_clauses.append("entity_type = :entity_type")
        params["entity_type"] = filters["entity_type"]

    if filters.get("action"):
        where_clauses.append("action = :action")
        params["action"] = filters["action"]

    if filters.get("user_id") is not None:
        where_clauses.append("user_id = :user_id")
        params["user_id"] = filters["user_id"]

    if filters.get("from"):
        where_clauses.append("ts >= :ts_from")
        params["ts_from"] = filters["from"]

    if filters.get("to"):
        where_clauses.append("ts <= :ts_to")
        params["ts_to"] = filters["to"]

    if filters.get("q"):
        where_clauses.append(
            "(entity_id ILIKE :q OR username ILIKE :q)"
        )
        params["q"] = f"%{filters['q']}%"

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count_rows = execute_query(
        f"SELECT COUNT(*) AS total FROM audit_log {where_sql}", params
    )
    total = count_rows[0]["total"] if count_rows else 0

    params["limit"] = page_size
    params["offset"] = offset
    rows = execute_query(
        f"""
        SELECT id, ts, user_id, username, action, entity_type, entity_id,
               before_state, after_state, metadata, status, error
        FROM audit_log
        {where_sql}
        ORDER BY ts DESC
        LIMIT :limit OFFSET :offset
        """,
        params,
    )

    return {
        "logs": rows or [],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_log(log_id: int) -> Optional[dict]:
    """Returns a single audit log entry by id, or None if not found."""
    rows = execute_query(
        """
        SELECT id, ts, user_id, username, action, entity_type, entity_id,
               before_state, after_state, metadata, status, error
        FROM audit_log
        WHERE id = :id
        """,
        {"id": log_id},
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# log_event — in-process, for this api's own routes
# ---------------------------------------------------------------------------

def _persist(event: dict) -> None:
    """Seam for tests (tests/conftest.py captures events here)."""
    record_event(event)


def log_event(
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    *,
    before: Any = None,
    after: Any = None,
    status: str = "success",
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Persist an audit event in the current request. NEVER raises."""
    try:
        _persist(build_event(
            action, entity_type, entity_id,
            before=before, after=after, status=status, error=error, metadata=metadata,
        ))
    except Exception as exc:
        print(f"AUDIT ERROR: {exc}", file=sys.stderr, flush=True)
