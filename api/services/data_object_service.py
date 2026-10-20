"""Objetos de dados do schema local: listagem, tipo, renomear, apagar, schema.

Extraido de `data_service` do monolito. As tabelas nascem no `ingestion`
(upload), mas o CICLO DE VIDA delas — e de views e views materializadas — fica
no api: renomear/apagar precisa manter relatorios e materializacoes coerentes,
e esses moram aqui.
"""
from db import execute_query, LOCAL_SCHEMA
from kit.identifiers import (
    quote_identifier as _quote_identifier,
    validate_data_object_name as _validate_data_object_name,
)


def get_tables():
    # information_schema.tables does NOT list materialized views, so UNION them in
    # from pg_matviews; otherwise a materialized Saved View vanishes from the catalog.
    query = f"""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = '{LOCAL_SCHEMA}'
        AND table_name NOT LIKE '\\_%'
        AND table_name != 'reports'
        AND table_name != 'audit_log'
        UNION
        SELECT matviewname AS table_name
        FROM pg_matviews
        WHERE schemaname = '{LOCAL_SCHEMA}'
        AND matviewname NOT LIKE '\\_%'
        ORDER BY table_name
    """
    result = execute_query(query)
    return [row['table_name'] for row in result]


_DDL_TYPE_BY_OBJECT = {
    "view": "VIEW",
    "materialized_view": "MATERIALIZED VIEW",
    "table": "TABLE",
}


def get_data_object_type(name):
    _validate_data_object_name(name)
    # Use pg_class.relkind so materialized views ('m') are detected too.
    query = f"""
        SELECT c.relkind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = '{LOCAL_SCHEMA}'
        AND c.relname = :name
        AND c.relkind IN ('r', 'v', 'm', 'p', 'f')
    """
    result = execute_query(query, {"name": name})
    if not result:
        return None
    relkind = result[0]["relkind"]
    if relkind == 'm':
        return "materialized_view"
    if relkind == 'v':
        return "view"
    return "table"


def rename_data_object(current_name, new_name):
    from services import materialized_view_service as mv_service

    current_name = _validate_data_object_name(current_name)
    new_name = _validate_data_object_name(new_name)
    object_type = get_data_object_type(current_name)
    if not object_type:
        return None
    if get_data_object_type(new_name):
        raise ValueError(f"An object named '{new_name}' already exists.")

    ddl_type = _DDL_TYPE_BY_OBJECT.get(object_type, "TABLE")
    execute_query(
        f"ALTER {ddl_type} {_quote_identifier(current_name)} RENAME TO {_quote_identifier(new_name)}"
    )
    if object_type == "materialized_view":
        mv_service.rename_materialization(current_name, new_name)
    return {"name": new_name, "previous_name": current_name, "type": object_type}


def delete_data_object(name):
    from services import materialized_view_service as mv_service

    name = _validate_data_object_name(name)
    object_type = get_data_object_type(name)
    if not object_type:
        return None

    ddl_type = _DDL_TYPE_BY_OBJECT.get(object_type, "TABLE")
    if object_type == "materialized_view":
        mv_service.drop_materialization_metadata(name)
    execute_query(f"DROP {ddl_type} IF EXISTS {_quote_identifier(name)} CASCADE")
    return {"name": name, "type": object_type}


def get_aliases_for_table(table_name):
    """{alias: physical_column} de uma tabela.

    `_column_aliases` e escrita pelo `ingestion` no upload; o api so le, para
    devolver o nome original das colunas encurtadas no schema.
    """
    rows = execute_query(
        "SELECT alias, physical_column FROM _column_aliases WHERE table_name = :t",
        {"t": table_name},
    ) or []
    return {r['alias']: r['physical_column'] for r in rows}


def get_table_schema(table_name):
    _validate_data_object_name(table_name)
    query = """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = :table_name
        ORDER BY ordinal_position
    """
    return execute_query(query, {"table_name": table_name})
