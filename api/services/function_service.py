from __future__ import annotations

"""Managed SQL functions for queries and saved views."""
import json
import re
import uuid
from typing import Any

from db import engine, execute_query, LOCAL_SCHEMA
from kit.sql_guard import ReadOnlySQLError, validate_readonly_sql as _guard_readonly_sql
from sqlalchemy import text


IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

TYPE_ALIASES = {
    "int": "integer",
    "int4": "integer",
    "int8": "bigint",
    "decimal": "numeric",
    "float": "double precision",
    "float8": "double precision",
    "bool": "boolean",
    "varchar": "text",
    "character varying": "text",
    "timestamp with time zone": "timestamptz",
    "timestamp without time zone": "timestamp",
}

ALLOWED_TYPES = {
    "text",
    "integer",
    "bigint",
    "numeric",
    "double precision",
    "boolean",
    "date",
    "timestamp",
    "timestamptz",
    "jsonb",
    "uuid",
}


class FunctionValidationError(ValueError):
    """Raised when a function definition is invalid."""


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_]", "_", (value or "").lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        slug = "funcao"
    if not slug.startswith("fn_"):
        slug = f"fn_{slug}"
    if not re.match(r"^[a-z]", slug):
        slug = f"fn_{slug}"
    return slug[:63].rstrip("_")


def _normalize_type(value: str) -> str:
    normalized = re.sub(r"\s+", " ", (value or "").strip().lower())
    normalized = TYPE_ALIASES.get(normalized, normalized)
    if normalized not in ALLOWED_TYPES:
        raise FunctionValidationError(f"Tipo não permitido: {value}")
    return normalized


def _normalize_identifier(value: str, label: str) -> str:
    normalized = (value or "").strip().lower()
    if not IDENTIFIER_RE.match(normalized):
        raise FunctionValidationError(f"{label} inválido: use letras, números e _, começando por letra")
    return normalized


def _normalize_parameters(parameters: Any) -> list[dict]:
    if parameters is None:
        return []
    if not isinstance(parameters, list):
        raise FunctionValidationError("Parâmetros devem ser uma lista")

    normalized = []
    seen = set()
    for item in parameters:
        if not isinstance(item, dict):
            raise FunctionValidationError("Cada parâmetro deve ter nome e tipo")
        name = _normalize_identifier(item.get("name"), "Parâmetro")
        if name in seen:
            raise FunctionValidationError(f"Parâmetro duplicado: {name}")
        seen.add(name)
        normalized.append({"name": name, "type": _normalize_type(item.get("type"))})
    return normalized


def _normalize_return_columns(columns: Any) -> list[dict]:
    if columns is None:
        return []
    if not isinstance(columns, list):
        raise FunctionValidationError("Colunas de retorno devem ser uma lista")

    normalized = []
    seen = set()
    for item in columns:
        if not isinstance(item, dict):
            raise FunctionValidationError("Cada coluna de retorno deve ter nome e tipo")
        name = _normalize_identifier(item.get("name"), "Coluna de retorno")
        if name in seen:
            raise FunctionValidationError(f"Coluna de retorno duplicada: {name}")
        seen.add(name)
        normalized.append({"name": name, "type": _normalize_type(item.get("type"))})
    return normalized


def validate_readonly_sql(sql: str) -> str:
    """Guarda read-only do kit, com o erro de dominio deste servico."""
    try:
        return _guard_readonly_sql(sql)
    except ReadOnlySQLError as e:
        raise FunctionValidationError(str(e)) from e


def normalize_function_payload(data: dict, existing_function_name: str | None = None) -> dict:
    if not isinstance(data, dict):
        raise FunctionValidationError("Payload inválido")

    name = (data.get("name") or "").strip()
    if not name:
        raise FunctionValidationError("Nome obrigatório")
    if len(name) > 255:
        raise FunctionValidationError("Nome muito longo")

    function_name = data.get("function_name") or existing_function_name or _slugify(name)
    function_name = _normalize_identifier(function_name, "Nome SQL da função")
    if not function_name.startswith("fn_"):
        raise FunctionValidationError("Nome SQL da função deve começar com fn_")

    kind = (data.get("kind") or "scalar").strip().lower()
    if kind not in {"scalar", "table"}:
        raise FunctionValidationError("Tipo de função inválido")

    parameters = _normalize_parameters(data.get("parameters") or [])
    sql_body = validate_readonly_sql(data.get("sql_body") or "")

    return_type = None
    return_columns = []
    if kind == "scalar":
        return_type = _normalize_type(data.get("return_type"))
    else:
        return_columns = _normalize_return_columns(data.get("return_columns") or [])
        if not return_columns:
            raise FunctionValidationError("Funções tabulares precisam de pelo menos uma coluna de retorno")

    return {
        "name": name,
        "function_name": function_name,
        "description": (data.get("description") or "").strip() or None,
        "kind": kind,
        "parameters": parameters,
        "return_type": return_type,
        "return_columns": return_columns,
        "sql_body": sql_body,
    }


def _json_load(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value


def _row_to_function(row: dict | None, include_body: bool = True) -> dict | None:
    if not row:
        return None
    result = {
        "id": row["id"],
        "name": row["name"],
        "function_name": row["function_name"],
        "description": row.get("description"),
        "kind": row["kind"],
        "parameters": _json_load(row.get("parameters"), []),
        "return_type": row.get("return_type"),
        "return_columns": _json_load(row.get("return_columns"), []),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
    result["signature"] = build_signature(result)
    result["call_example"] = build_call_example(result)
    if include_body:
        result["sql_body"] = row.get("sql_body")
    return result


def build_signature(definition: dict) -> str:
    params = ", ".join(f"{p['name']} {p['type']}" for p in definition.get("parameters", []))
    if definition.get("kind") == "table":
        returns = ", ".join(f"{c['name']} {c['type']}" for c in definition.get("return_columns", []))
        return f"{definition['function_name']}({params}) RETURNS TABLE ({returns})"
    return f"{definition['function_name']}({params}) RETURNS {definition.get('return_type')}"


def build_call_example(definition: dict) -> str:
    placeholders = ", ".join(p["name"] for p in definition.get("parameters", []))
    if definition.get("kind") == "table":
        return f"SELECT * FROM {definition['function_name']}({placeholders})"
    return f"{definition['function_name']}({placeholders})"


def _ddl_for(definition: dict) -> str:
    params = ", ".join(f"{p['name']} {p['type']}" for p in definition["parameters"])
    if definition["kind"] == "table":
        returns = "RETURNS TABLE (" + ", ".join(
            f"{c['name']} {c['type']}" for c in definition["return_columns"]
        ) + ")"
    else:
        returns = f"RETURNS {definition['return_type']}"

    tag = f"$dr_fn_{uuid.uuid4().hex}$"
    return f"""
CREATE OR REPLACE FUNCTION {LOCAL_SCHEMA}.{definition['function_name']}({params})
{returns}
LANGUAGE sql
STABLE
AS {tag}
{definition['sql_body']}
{tag}
"""


def _drop_ddl_for(definition: dict) -> str:
    arg_types = ", ".join(p["type"] for p in definition.get("parameters", []))
    return f"DROP FUNCTION IF EXISTS {LOCAL_SCHEMA}.{definition['function_name']}({arg_types})"


def _same_signature(a: dict, b: dict) -> bool:
    return (
        a["function_name"] == b["function_name"]
        and [p["type"] for p in a.get("parameters", [])] == [p["type"] for p in b.get("parameters", [])]
        and a["kind"] == b["kind"]
        and a.get("return_type") == b.get("return_type")
        and a.get("return_columns") == b.get("return_columns")
    )


def validate_function_definition(data: dict) -> dict:
    definition = normalize_function_payload(data)
    temp_definition = {**definition, "function_name": f"fn_validate_{uuid.uuid4().hex[:20]}"}
    ddl = _ddl_for(temp_definition)

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.exec_driver_sql(ddl)
            trans.rollback()
        except Exception:
            trans.rollback()
            raise

    return {
        "valid": True,
        "function_name": definition["function_name"],
        "signature": build_signature(definition),
        "call_example": build_call_example(definition),
    }


def list_functions(include_body: bool = False) -> list[dict]:
    columns = """
        id, name, function_name, description, kind, parameters, return_type,
        return_columns, created_at, updated_at
    """
    if include_body:
        columns += ", sql_body"
    rows = execute_query(f"SELECT {columns} FROM _system_functions ORDER BY name ASC")
    return [_row_to_function(row, include_body=include_body) for row in (rows or [])]


def get_function(function_id: int, include_body: bool = True) -> dict | None:
    rows = execute_query(
        """
        SELECT id, name, function_name, description, kind, parameters, return_type,
               return_columns, sql_body, created_at, updated_at
        FROM _system_functions
        WHERE id = :id
        """,
        {"id": function_id},
    )
    return _row_to_function(rows[0], include_body=include_body) if rows else None


def _check_unique(definition: dict, exclude_id: int | None = None) -> None:
    sql = """
        SELECT id, name, function_name
        FROM _system_functions
        WHERE (LOWER(name) = LOWER(:name) OR function_name = :function_name)
    """
    params = {"name": definition["name"], "function_name": definition["function_name"]}
    if exclude_id is not None:
        sql += " AND id != :id"
        params["id"] = exclude_id
    rows = execute_query(sql, params) or []
    if rows:
        raise FunctionValidationError("Já existe uma função com este nome ou nome SQL")


def create_function(data: dict) -> dict:
    definition = normalize_function_payload(data)
    _check_unique(definition)

    with engine.begin() as conn:
        conn.exec_driver_sql(_ddl_for(definition))
        result = conn.execute(
            text(
                """
                INSERT INTO _system_functions
                    (name, function_name, description, kind, parameters, return_type, return_columns, sql_body)
                VALUES
                    (:name, :function_name, :description, :kind, CAST(:parameters AS jsonb),
                     :return_type, CAST(:return_columns AS jsonb), :sql_body)
                RETURNING id, name, function_name, description, kind, parameters, return_type,
                          return_columns, sql_body, created_at, updated_at
                """
            ),
            {
                **definition,
                "parameters": json.dumps(definition["parameters"]),
                "return_columns": json.dumps(definition["return_columns"]),
            },
        )
        row = result.mappings().first()

    return _row_to_function(dict(row), include_body=True)


def update_function(function_id: int, data: dict) -> dict | None:
    existing = get_function(function_id, include_body=True)
    if not existing:
        return None

    definition = normalize_function_payload(data)
    _check_unique(definition, exclude_id=function_id)

    with engine.begin() as conn:
        if not _same_signature(existing, definition):
            conn.exec_driver_sql(_drop_ddl_for(existing))
        conn.exec_driver_sql(_ddl_for(definition))
        result = conn.execute(
            text(
                """
                UPDATE _system_functions
                SET name = :name,
                    function_name = :function_name,
                    description = :description,
                    kind = :kind,
                    parameters = CAST(:parameters AS jsonb),
                    return_type = :return_type,
                    return_columns = CAST(:return_columns AS jsonb),
                    sql_body = :sql_body,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                RETURNING id, name, function_name, description, kind, parameters, return_type,
                          return_columns, sql_body, created_at, updated_at
                """
            ),
            {
                **definition,
                "id": function_id,
                "parameters": json.dumps(definition["parameters"]),
                "return_columns": json.dumps(definition["return_columns"]),
            },
        )
        row = result.mappings().first()

    return _row_to_function(dict(row), include_body=True)


def delete_function(function_id: int) -> dict | None:
    existing = get_function(function_id, include_body=True)
    if not existing:
        return None

    with engine.begin() as conn:
        conn.exec_driver_sql(_drop_ddl_for(existing))
        conn.execute(text("DELETE FROM _system_functions WHERE id = :id"), {"id": function_id})

    return existing
