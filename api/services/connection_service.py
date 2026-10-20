"""External database connections (linked-server style) via Postgres FDW.

Backed by the `_system_connections` table. Each row materializes a
Postgres `SERVER` + `USER MAPPING` and imports the remote schema into a
dedicated local schema `ext_<name>`, so foreign tables can be referenced
in regular SELECT/JOIN queries alongside local tables and `fn_*` functions.

Supported `db_type` values: 'sqlserver' (tds_fdw) and 'postgres' (postgres_fdw).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import uuid
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from db import engine, execute_query


SUPPORTED_TYPES = ("sqlserver", "postgres")
DEFAULT_PORTS = {"sqlserver": 1433, "postgres": 5432}
DEFAULT_REMOTE_SCHEMAS = {"sqlserver": "dbo", "postgres": "public"}
FDW_HANDLERS = {"sqlserver": "tds_fdw", "postgres": "postgres_fdw"}

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


class ConnectionValidationError(ValueError):
    """Raised when a connection payload is invalid."""


def safe_connection_error(exc: Exception, *secrets: str | None) -> str:
    """Return an error message safe for API responses and audit logs."""
    msg = str(exc) or exc.__class__.__name__
    for secret in secrets:
        if secret:
            msg = msg.replace(secret, "[redacted]")
    msg = re.sub(r"password\s+'(?:''|[^'])*'", "password '[redacted]'", msg, flags=re.IGNORECASE)
    msg = re.sub(r'password\s+"(?:""|[^"])*"', 'password "[redacted]"', msg, flags=re.IGNORECASE)
    return msg


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Crypto
# ---------------------------------------------------------------------------

def _fernet() -> Fernet:
    key = os.getenv("CONNECTIONS_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("CONNECTIONS_ENCRYPTION_KEY environment variable is required")
    if len(key) == 44 and key.endswith("="):
        try:
            return Fernet(key.encode())
        except (ValueError, InvalidToken):
            pass
    if len(key) < 32:
        raise RuntimeError("CONNECTIONS_ENCRYPTION_KEY must be a Fernet key or a passphrase of at least 32 characters")
    digest = hashlib.sha256(key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


# ---------------------------------------------------------------------------
# Validation / normalization
# ---------------------------------------------------------------------------

def _normalize_payload(data: dict, *, partial: bool = False, existing: dict | None = None) -> dict:
    if not isinstance(data, dict):
        raise ConnectionValidationError("Payload inválido")

    def field(key: str, required: bool = True) -> Any:
        if key in data and data[key] not in (None, ""):
            return data[key]
        if existing and key in existing:
            return existing[key]
        if required and not partial:
            raise ConnectionValidationError(f"Campo obrigatório: {key}")
        return None

    name = (field("name") or "").strip().lower()
    if not NAME_RE.match(name):
        raise ConnectionValidationError(
            "Nome inválido: use letras minúsculas, números e _, "
            "começando por letra (até 41 chars)"
        )

    db_type = (field("db_type") or "").strip().lower()
    if db_type not in SUPPORTED_TYPES:
        raise ConnectionValidationError(f"Tipo não suportado. Use um de: {', '.join(SUPPORTED_TYPES)}")

    display_name = (field("display_name") or name).strip()
    host = (field("host") or "").strip()
    if not host:
        raise ConnectionValidationError("Host obrigatório")

    raw_port = data.get("port") if "port" in data else (existing.get("port") if existing else None)
    if raw_port in (None, ""):
        port = DEFAULT_PORTS[db_type]
    else:
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            raise ConnectionValidationError("Porta inválida")
        if port < 1 or port > 65535:
            raise ConnectionValidationError("Porta fora do intervalo 1-65535")

    database = (field("database") or "").strip()
    if not database:
        raise ConnectionValidationError("Database obrigatório")

    remote_schema = (
        data.get("remote_schema")
        or (existing or {}).get("remote_schema")
        or DEFAULT_REMOTE_SCHEMAS[db_type]
    ).strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", remote_schema):
        raise ConnectionValidationError("remote_schema inválido")

    username = (field("username") or "").strip()
    if not username:
        raise ConnectionValidationError("Usuário obrigatório")

    password = data.get("password")
    if not password:
        if existing and existing.get("password_enc"):
            password_enc = existing["password_enc"]
        else:
            raise ConnectionValidationError("Senha obrigatória")
    else:
        if not isinstance(password, str):
            raise ConnectionValidationError("Senha inválida")
        password_enc = _encrypt(password)

    options = data.get("options")
    if options is None and existing:
        options = existing.get("options")
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ConnectionValidationError("options deve ser um objeto")

    return {
        "name": name,
        "display_name": display_name,
        "db_type": db_type,
        "host": host,
        "port": port,
        "database": database,
        "remote_schema": remote_schema,
        "username": username,
        "password_enc": password_enc,
        "options": options,
    }


def _row_to_connection(row: dict | None, *, include_options: bool = True) -> dict | None:
    if not row:
        return None
    options = row.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    out = {
        "id": row["id"],
        "name": row["name"],
        "display_name": row.get("display_name") or row["name"],
        "db_type": row["db_type"],
        "host": row["host"],
        "port": row["port"],
        "database": row["database"],
        "remote_schema": row.get("remote_schema"),
        "username": row["username"],
        "schema_name": _local_schema(row["name"]),
        "last_synced_at": row.get("last_synced_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
    if include_options:
        out["options"] = options or {}
    return out


# ---------------------------------------------------------------------------
# Provisioning helpers
# ---------------------------------------------------------------------------

def _local_schema(name: str) -> str:
    return f"ext_{name}"


def _server_name(name: str) -> str:
    return f"conn_{name}"


def _ident(value: str) -> str:
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', value):
        raise ConnectionValidationError(f"Identificador inválido: {value}")
    return f'"{value}"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _server_options_sql(definition: dict) -> str:
    db_type = definition["db_type"]
    if db_type == "sqlserver":
        servername = definition["host"]
        port = definition["port"]
        opts = [
            f"servername {_quote_literal(servername)}",
            f"port {_quote_literal(str(port))}",
            f"database {_quote_literal(definition['database'])}",
        ]
    elif db_type == "postgres":
        opts = [
            f"host {_quote_literal(definition['host'])}",
            f"port {_quote_literal(str(definition['port']))}",
            f"dbname {_quote_literal(definition['database'])}",
        ]
    else:
        raise ConnectionValidationError(f"Tipo não suportado: {db_type}")
    return ", ".join(opts)


def _user_mapping_options_sql(definition: dict, password_plain: str) -> str:
    username_option = "username" if definition["db_type"] == "sqlserver" else "user"
    return (
        f"{username_option} {_quote_literal(definition['username'])}, "
        f"password {_quote_literal(password_plain)}"
    )


def _provision(definition: dict, password_plain: str, *, provision_name: str | None = None) -> int:
    """Materialize SERVER + USER MAPPING + IMPORT FOREIGN SCHEMA. Returns foreign-table count."""
    fdw = FDW_HANDLERS[definition["db_type"]]
    name = provision_name or definition["name"]
    schema = _local_schema(name)
    server = _server_name(name)
    server_opts = _server_options_sql(definition)
    user_opts = _user_mapping_options_sql(definition, password_plain)
    remote_schema = definition["remote_schema"]

    with engine.begin() as conn:
        conn.exec_driver_sql(f"DROP SCHEMA IF EXISTS {_ident(schema)} CASCADE")
        conn.exec_driver_sql(f"DROP SERVER IF EXISTS {_ident(server)} CASCADE")
        conn.exec_driver_sql(
            f"CREATE SERVER {_ident(server)} FOREIGN DATA WRAPPER {fdw} OPTIONS ({server_opts})"
        )
        conn.exec_driver_sql(
            f"CREATE USER MAPPING FOR CURRENT_USER SERVER {_ident(server)} OPTIONS ({user_opts})"
        )
        conn.exec_driver_sql(f"CREATE SCHEMA {_ident(schema)}")
        conn.exec_driver_sql(
            f"IMPORT FOREIGN SCHEMA {_ident(remote_schema)} FROM SERVER {_ident(server)} INTO {_ident(schema)}"
        )
        result = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM information_schema.foreign_tables WHERE foreign_table_schema = %s",
            (schema,),
        )
        return int(result.scalar() or 0)


def _replace_provisioned_objects(existing_name: str, staged_name: str, final_name: str) -> None:
    """Atomically replace a provisioned schema/server with staged objects."""
    existing_schema = _local_schema(existing_name)
    existing_server = _server_name(existing_name)
    staged_schema = _local_schema(staged_name)
    staged_server = _server_name(staged_name)
    final_schema = _local_schema(final_name)
    final_server = _server_name(final_name)

    with engine.begin() as conn:
        conn.exec_driver_sql(f"DROP SCHEMA IF EXISTS {_ident(existing_schema)} CASCADE")
        conn.exec_driver_sql(f"DROP SERVER IF EXISTS {_ident(existing_server)} CASCADE")
        if staged_schema != final_schema:
            conn.exec_driver_sql(f"ALTER SCHEMA {_ident(staged_schema)} RENAME TO {_ident(final_schema)}")
        if staged_server != final_server:
            conn.exec_driver_sql(f"ALTER SERVER {_ident(staged_server)} RENAME TO {_ident(final_server)}")


def _deprovision(name: str) -> None:
    schema = _local_schema(name)
    server = _server_name(name)
    with engine.begin() as conn:
        conn.exec_driver_sql(f"DROP SCHEMA IF EXISTS {_ident(schema)} CASCADE")
        conn.exec_driver_sql(f"DROP SERVER IF EXISTS {_ident(server)} CASCADE")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_connections() -> list[dict]:
    rows = execute_query(
        """
        SELECT id, name, display_name, db_type, host, port, database, remote_schema,
               username, options, last_synced_at, created_at, updated_at
        FROM _system_connections
        ORDER BY name ASC
        """
    )
    return [_row_to_connection(row) for row in (rows or [])]


def list_connection_catalog() -> list[dict]:
    rows = execute_query(
        """
        SELECT id, name, display_name, db_type, remote_schema, last_synced_at
        FROM _system_connections
        ORDER BY name ASC
        """
    )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "display_name": row.get("display_name") or row["name"],
            "db_type": row["db_type"],
            "remote_schema": row.get("remote_schema"),
            "schema_name": _local_schema(row["name"]),
            "last_synced_at": row.get("last_synced_at"),
        }
        for row in (rows or [])
    ]


def get_connection(connection_id: int, *, with_password_enc: bool = False) -> dict | None:
    columns = (
        "id, name, display_name, db_type, host, port, database, remote_schema, "
        "username, options, last_synced_at, created_at, updated_at"
    )
    if with_password_enc:
        columns += ", password_enc"
    rows = execute_query(
        f"SELECT {columns} FROM _system_connections WHERE id = :id",
        {"id": connection_id},
    )
    if not rows:
        return None
    return _row_to_connection(rows[0])


def _check_unique(name: str, exclude_id: int | None = None) -> None:
    sql = "SELECT id FROM _system_connections WHERE name = :name"
    params: dict = {"name": name}
    if exclude_id is not None:
        sql += " AND id != :id"
        params["id"] = exclude_id
    rows = execute_query(sql, params) or []
    if rows:
        raise ConnectionValidationError("Já existe uma conexão com este nome")


def create_connection(data: dict) -> dict:
    definition = _normalize_payload(data)
    _check_unique(definition["name"])

    password_plain = _decrypt(definition["password_enc"])
    table_count = _provision(definition, password_plain)

    try:
        rows = execute_query(
            """
            INSERT INTO _system_connections
                (name, display_name, db_type, host, port, database, remote_schema,
                 username, password_enc, options, last_synced_at)
            VALUES
                (:name, :display_name, :db_type, :host, :port, :database, :remote_schema,
                 :username, :password_enc, CAST(:options AS jsonb), now())
            RETURNING id, name, display_name, db_type, host, port, database, remote_schema,
                      username, options, last_synced_at, created_at, updated_at
            """,
            {**definition, "options": json.dumps(definition["options"])},
        )
    except Exception:
        _deprovision(definition["name"])
        raise
    result = _row_to_connection(rows[0])
    result["foreign_table_count"] = table_count
    return result


def update_connection(connection_id: int, data: dict) -> dict | None:
    rows = execute_query(
        "SELECT id, name, display_name, db_type, host, port, database, remote_schema, "
        "username, password_enc, options FROM _system_connections WHERE id = :id",
        {"id": connection_id},
    )
    if not rows:
        return None
    existing = dict(rows[0])
    if isinstance(existing.get("options"), str):
        try:
            existing["options"] = json.loads(existing["options"])
        except json.JSONDecodeError:
            existing["options"] = {}

    definition = _normalize_payload(data, existing=existing)
    if definition["name"] != existing["name"]:
        _check_unique(definition["name"], exclude_id=connection_id)

    password_plain = _decrypt(definition["password_enc"])

    staged_name = f"stage_{uuid.uuid4().hex[:12]}"
    try:
        table_count = _provision(definition, password_plain, provision_name=staged_name)
        _replace_provisioned_objects(existing["name"], staged_name, definition["name"])
    except Exception:
        try:
            _deprovision(staged_name)
        except Exception:
            pass
        raise

    updated_rows = execute_query(
        """
        UPDATE _system_connections
        SET name = :name,
            display_name = :display_name,
            db_type = :db_type,
            host = :host,
            port = :port,
            database = :database,
            remote_schema = :remote_schema,
            username = :username,
            password_enc = :password_enc,
            options = CAST(:options AS jsonb),
            last_synced_at = now(),
            updated_at = now()
        WHERE id = :id
        RETURNING id, name, display_name, db_type, host, port, database, remote_schema,
                  username, options, last_synced_at, created_at, updated_at
        """,
        {**definition, "id": connection_id, "options": json.dumps(definition["options"])},
    )
    result = _row_to_connection(updated_rows[0])
    result["foreign_table_count"] = table_count
    return result


def delete_connection(connection_id: int) -> dict | None:
    existing = get_connection(connection_id)
    if not existing:
        return None
    _deprovision(existing["name"])
    execute_query("DELETE FROM _system_connections WHERE id = :id", {"id": connection_id})
    return existing


def sync_connection(connection_id: int) -> dict | None:
    rows = execute_query(
        "SELECT id, name, db_type, host, port, database, remote_schema, username, "
        "password_enc, options FROM _system_connections WHERE id = :id",
        {"id": connection_id},
    )
    if not rows:
        return None
    row = dict(rows[0])
    if isinstance(row.get("options"), str):
        try:
            row["options"] = json.loads(row["options"])
        except json.JSONDecodeError:
            row["options"] = {}
    password_plain = _decrypt(row["password_enc"])
    staged_name = f"stage_{uuid.uuid4().hex[:12]}"
    try:
        table_count = _provision(row, password_plain, provision_name=staged_name)
        _replace_provisioned_objects(row["name"], staged_name, row["name"])
    except Exception:
        try:
            _deprovision(staged_name)
        except Exception:
            pass
        raise
    execute_query(
        "UPDATE _system_connections SET last_synced_at = now(), updated_at = now() WHERE id = :id",
        {"id": connection_id},
    )
    return {
        "id": connection_id,
        "name": row["name"],
        "schema_name": _local_schema(row["name"]),
        "foreign_table_count": table_count,
    }


def test_connection(data: dict) -> dict:
    """Provision a temporary SERVER, query a single foreign table list, then drop it."""
    definition = _normalize_payload(data)
    password_plain = _decrypt(definition["password_enc"])
    probe_name = f"probe_{uuid.uuid4().hex[:12]}"
    probe_def = {**definition, "name": probe_name}
    try:
        table_count = _provision(probe_def, password_plain)
        return {"ok": True, "foreign_table_count": table_count}
    finally:
        try:
            _deprovision(probe_name)
        except Exception:
            pass


def list_foreign_tables(connection_id: int) -> list[str] | None:
    existing = get_connection(connection_id)
    if not existing:
        return None
    schema = _local_schema(existing["name"])
    rows = execute_query(
        """
        SELECT foreign_table_name AS name
        FROM information_schema.foreign_tables
        WHERE foreign_table_schema = :schema
        ORDER BY foreign_table_name
        """,
        {"schema": schema},
    )
    return [r["name"] for r in (rows or [])]


def get_foreign_table_schema(connection_id: int, table_name: str) -> list[dict] | None:
    existing = get_connection(connection_id)
    if not existing:
        return None
    schema = _local_schema(existing["name"])
    rows = execute_query(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table
        ORDER BY ordinal_position
        """,
        {"schema": schema, "table": table_name},
    )
    return rows or []
