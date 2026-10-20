import pandas as pd
from db import engine, execute_query, LOCAL_SCHEMA
from services.pdf_parser import extract_tables_from_pdf
import re
import unicodedata
from datetime import datetime
import pytz
from kit.identifiers import (  # noqa: F401 -- reexporta a regra de nome compartilhada com o catalog
    DATA_OBJECT_NAME_RE,
    SYSTEM_DATA_OBJECTS,
    quote_identifier as _quote_identifier,
    validate_data_object_name as _validate_data_object_name,
)

TIMESTAMP_COLUMN = 'data_registro_sistema'
# Preserva a ordem original das linhas do arquivo. Sem ela o Postgres nao garante
# a ordem de retorno de um SELECT sem ORDER BY: parallel seq scan,
# synchronize_seqscans, VACUUM e reescrita de pagina reordenam o heap, e com
# LIMIT muda ate quais linhas voltam.
ROW_ORDER_COLUMN = 'ordem_arquivo'
# Colunas geradas pelo sistema: nao vem do arquivo e nao sao serializadas como TEXT.
SYSTEM_COLUMNS = (TIMESTAMP_COLUMN, ROW_ORDER_COLUMN)
PG_MAX_IDENTIFIER_BYTES = 63
TEXT_DATA_TYPES = {'text', 'character varying', 'character', 'varchar'}


def get_aliases_for_table(table_name):
    """Return {alias: physical_column} for the given table."""
    rows = execute_query(
        "SELECT alias, physical_column FROM _column_aliases WHERE table_name = :t",
        {"t": table_name},
    ) or []
    return {r['alias']: r['physical_column'] for r in rows}


def upsert_alias(table_name, physical_column, alias):
    """Idempotently record alias -> physical_column for a table.

    No-op when alias equals physical_column (no shortening happened).
    """
    if alias == physical_column:
        return
    execute_query(
        """
        INSERT INTO _column_aliases (table_name, physical_column, alias)
        VALUES (:t, :p, :a)
        ON CONFLICT (table_name, alias) DO UPDATE SET physical_column = EXCLUDED.physical_column
        """,
        {"t": table_name, "p": physical_column, "a": alias},
    )


def remove_aliases_for_table(table_name):
    execute_query(
        "DELETE FROM _column_aliases WHERE table_name = :t",
        {"t": table_name},
    )


def _strip_diacritics(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))


def suggest_shortened_name(name, max_bytes=PG_MAX_IDENTIFIER_BYTES):
    """Build a deterministic shorter version of a column name that fits in max_bytes.

    Strategy: strip diacritics first (often enough), then UTF-8-safe truncate.
    """
    if len(name.encode('utf-8')) <= max_bytes:
        return name
    candidate = _strip_diacritics(name)
    if len(candidate.encode('utf-8')) <= max_bytes:
        return candidate
    return _utf8_truncate(candidate, max_bytes)


def _quote_column(name):
    return '"' + str(name).replace('"', '""') + '"'


def _utf8_truncate(s, max_bytes):
    encoded = s.encode('utf-8')
    if len(encoded) <= max_bytes:
        return s
    return encoded[:max_bytes].decode('utf-8', errors='ignore')


class OversizedColumnError(Exception):
    """Raised when a column name still exceeds the Postgres byte limit after renames."""
    def __init__(self, oversized):
        # oversized: list of {"name": str, "bytes": int, "suggestion": str}
        self.oversized = oversized
        names = ", ".join(f'"{c["name"]}" ({c["bytes"]} bytes)' for c in oversized)
        super().__init__(
            f"O Postgres limita nomes de coluna a {PG_MAX_IDENTIFIER_BYTES} bytes. "
            f"Colunas acima do limite: {names}. Renomeie antes de enviar."
        )


def _normalize_column_names(columns):
    """Validate column names fit Postgres's identifier limit.

    Returns (columns_as_list, empty_rename_map). Raises OversizedColumnError if
    any column exceeds the limit — caller must provide renames before reaching here.
    """
    oversized = []
    seen = set()
    for c in columns:
        size = len(c.encode('utf-8'))
        if size > PG_MAX_IDENTIFIER_BYTES:
            oversized.append({
                "name": c,
                "bytes": size,
                "suggestion": suggest_shortened_name(c),
            })
        if c in seen:
            raise ValueError(
                f"Column name collision: '{c}' appears more than once."
            )
        seen.add(c)
    if oversized:
        raise OversizedColumnError(oversized)
    return list(columns), {}


def _normalize_dataframe_columns(df):
    _normalize_column_names(df.columns.tolist())
    return df


def _apply_column_renames(df, column_renames):
    """Apply a {original: new} rename map to the dataframe before normalization.

    Validates: every new name fits the byte limit, no collisions are introduced.
    """
    if not column_renames:
        return df
    final_names = []
    for c in df.columns:
        target = column_renames.get(c, c)
        if len(target.encode('utf-8')) > PG_MAX_IDENTIFIER_BYTES:
            raise OversizedColumnError([{
                "name": target,
                "bytes": len(target.encode('utf-8')),
                "suggestion": suggest_shortened_name(target),
            }])
        final_names.append(target)
    if len(set(final_names)) != len(final_names):
        seen = set()
        dup = next(n for n in final_names if n in seen or seen.add(n))
        raise ValueError(f"Renames produzem colisão no nome '{dup}'.")
    df = df.rename(columns=column_renames)
    return df


def _to_text_or_none(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _serialize_dataframe_as_text(df):
    out = df.copy()
    for col in out.columns:
        if col in SYSTEM_COLUMNS:
            continue
        out[col] = out[col].map(_to_text_or_none).astype('object')
    return out


def _exec_ddl(conn, statements):
    """Execute literal DDL via the raw psycopg2 cursor (bypasses param interpolation).

    Required because column names like "Aluguel (%)" contain '%', which psycopg2
    treats as a parameter placeholder when SQLAlchemy's exec layer is used.
    """
    cursor = conn.connection.cursor()
    for stmt in statements:
        cursor.execute(stmt)


def _column_type_for(col):
    if col == TIMESTAMP_COLUMN:
        return 'TIMESTAMP'
    if col == ROW_ORDER_COLUMN:
        return 'BIGINT'
    return 'TEXT'


def _create_text_table(table_name, columns):
    column_defs = []
    for col in columns:
        column_defs.append(f'{_quote_column(col)} {_column_type_for(col)}')
    ddl = f'CREATE TABLE "{table_name}" ({", ".join(column_defs)})'
    with engine.begin() as conn:
        _exec_ddl(conn, [
            f'DROP TABLE IF EXISTS "{table_name}" CASCADE',
            ddl,
        ])


def _get_dependent_views_recursive(relation_name):
    """Return view names depending on the relation, transitively.

    Order: deepest dependents last. Drop in reverse, recreate in this order.
    """
    direct_query = f"""
        SELECT DISTINCT dependent.relname AS dep
        FROM pg_depend d
        JOIN pg_rewrite r ON d.objid = r.oid
        JOIN pg_class dependent ON r.ev_class = dependent.oid
        JOIN pg_class source ON d.refobjid = source.oid
        JOIN pg_namespace ns ON dependent.relnamespace = ns.oid
        WHERE source.relname = :name
          AND dependent.relkind = 'v'
          AND dependent.relname != :name
          AND ns.nspname = '{LOCAL_SCHEMA}'
    """
    visited = set()
    ordered = []

    def walk(name):
        if name in visited:
            return
        visited.add(name)
        rows = execute_query(direct_query, {"name": name}) or []
        for row in rows:
            dep = row['dep']
            walk(dep)
            if dep not in ordered:
                ordered.append(dep)

    walk(relation_name)
    return ordered


def _reconcile_table_schema(table_name, df_columns):
    """Ensure every df column exists in the table; relax non-text columns to TEXT.

    This is the structural guard that prevents append-time type mismatches.
    The timestamp column is preserved as TIMESTAMP; all other columns converge to TEXT.
    Dependent views are dropped and recreated around the ALTERs when needed.
    """
    rows = execute_query(
        "SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_schema = '{LOCAL_SCHEMA}' AND table_name = :t",
        {"t": table_name},
    ) or []
    existing_types = {r['column_name']: r['data_type'] for r in rows}

    add_stmts = []
    for col in df_columns:
        if col not in existing_types:
            add_stmts.append(
                f'ALTER TABLE "{table_name}" ADD COLUMN {_quote_column(col)} {_column_type_for(col)}'
            )

    alter_stmts = []
    for col, current_type in existing_types.items():
        if col in SYSTEM_COLUMNS:
            continue
        if current_type not in TEXT_DATA_TYPES:
            qcol = _quote_column(col)
            alter_stmts.append(
                f'ALTER TABLE "{table_name}" ALTER COLUMN {qcol} TYPE TEXT USING {qcol}::text'
            )

    if not add_stmts and not alter_stmts:
        return

    dependents = []
    saved_defs = {}
    if alter_stmts:
        dependents = _get_dependent_views_recursive(table_name)
        for v in dependents:
            d = execute_query("SELECT pg_get_viewdef(:v, true) AS def", {"v": v})
            if d and d[0].get('def'):
                saved_defs[v] = d[0]['def']

    with engine.begin() as conn:
        statements = []
        statements.extend(f'DROP VIEW IF EXISTS "{v}" CASCADE' for v in dependents)
        statements.extend(add_stmts)
        statements.extend(alter_stmts)
        statements.extend(
            f'CREATE VIEW "{v}" AS {saved_defs[v]}'
            for v in reversed(dependents) if v in saved_defs
        )
        _exec_ddl(conn, statements)

    if dependents:
        print(f"INFO: Recreated dependent views: {dependents}", flush=True)


HEADER_MODE_GENERIC = 'generic'
HEADER_MODE_FIRST_ROW = 'first_row'
VALID_HEADER_MODES = {HEADER_MODE_GENERIC, HEADER_MODE_FIRST_ROW}

GENERIC_COL_RE = re.compile(r'^Unnamed: \d+$')


class ColumnCountMismatchError(Exception):
    """Raised when the file's column count doesn't match the target table (generic mode)."""
    def __init__(self, table_name, file_count, table_count):
        self.table_name = table_name
        self.file_count = file_count
        self.table_count = table_count
        super().__init__(
            f"O arquivo tem {file_count} colunas, mas a tabela '{table_name}' "
            f"tem {table_count} colunas. As estruturas precisam bater. "
            f"Ajuste o arquivo ou use 'Criar nova tabela'."
        )


class ColumnNameMismatchError(Exception):
    """Raised when file column names don't match the target table (first_row mode)."""
    def __init__(self, table_name, missing_in_table, missing_in_file):
        self.table_name = table_name
        self.missing_in_table = list(missing_in_table)
        self.missing_in_file = list(missing_in_file)
        parts = []
        if self.missing_in_table:
            parts.append(
                "Colunas no arquivo que não existem na tabela: "
                + ", ".join(f'"{c}"' for c in self.missing_in_table)
            )
        if self.missing_in_file:
            parts.append(
                "Colunas na tabela ausentes no arquivo: "
                + ", ".join(f'"{c}"' for c in self.missing_in_file)
            )
        super().__init__(
            f"Cabeçalho do arquivo não bate com a tabela '{table_name}'. "
            + ". ".join(parts)
            + "."
        )


class IncompatibleHeaderModeError(Exception):
    """Raised when the chosen header_mode is incompatible with the table's schema shape."""
    def __init__(self, table_name, chosen_mode, table_shape):
        self.table_name = table_name
        self.chosen_mode = chosen_mode
        self.table_shape = table_shape  # 'generic' or 'semantic'
        if table_shape == 'generic':
            msg = (
                f"A tabela '{table_name}' foi criada com cabeçalho genérico "
                f"(Unnamed: 0..N). Use o modo 'Cabeçalho genérico' para inserir aqui."
            )
        else:
            msg = (
                f"A tabela '{table_name}' tem colunas com nomes semânticos. "
                f"Use o modo 'Primeira linha do arquivo é o cabeçalho' para inserir aqui."
            )
        super().__init__(msg)


def _normalize_header_mode(value):
    if value is None or value == '':
        return HEADER_MODE_GENERIC
    if value not in VALID_HEADER_MODES:
        raise ValueError(f"header_mode inválido: {value}. Use 'generic' ou 'first_row'.")
    return value


def _is_generic_schema(existing_data_cols):
    """True if every data column matches the generic 'Unnamed: <n>' pattern."""
    return bool(existing_data_cols) and all(GENERIC_COL_RE.match(c) for c in existing_data_cols)


def _read_excel_raw(file_storage):
    """Read Excel preserving raw layout: every row becomes a data row, column
    names are positional ("Unnamed: <i>"). No header detection, no row filtering.

    Drops only rows that are entirely empty.
    """
    file_storage.seek(0)
    df = pd.read_excel(file_storage, engine='calamine', header=None)
    df.columns = [f'Unnamed: {i}' for i in range(df.shape[1])]
    df = df.dropna(how='all').reset_index(drop=True)
    print(f"INFO: Raw Excel read — {df.shape[0]} rows, {df.shape[1]} columns "
          f"(Unnamed: 0..{df.shape[1]-1}).", flush=True)
    return df


def _read_excel_first_row(file_storage):
    """Read Excel using row 0 as header. Column names come from cell values in
    row 1 of the source. Empty header cells become Unnamed: <i> (pandas default).
    """
    file_storage.seek(0)
    df = pd.read_excel(file_storage, engine='calamine', header=0)
    df = df.dropna(how='all').reset_index(drop=True)
    print(f"INFO: First-row header Excel read — {df.shape[0]} rows, "
          f"columns: {df.columns.tolist()}", flush=True)
    return df


def _read_csv_raw(file_storage):
    file_storage.seek(0)
    df = pd.read_csv(file_storage, sep=None, engine='python', header=None)
    df.columns = [f'Unnamed: {i}' for i in range(df.shape[1])]
    df = df.dropna(how='all').reset_index(drop=True)
    return df


def _read_csv_first_row(file_storage):
    file_storage.seek(0)
    df = pd.read_csv(file_storage, sep=None, engine='python', header=0)
    df = df.dropna(how='all').reset_index(drop=True)
    return df


def _read_headers_only(file_storage, header_mode):
    """Read just the file headers for inspect-headers — fast path that doesn't
    process the body. Mirrors the column-name behavior of the full read.
    """
    file_storage.seek(0)
    filename = file_storage.filename.lower()
    if filename.endswith('.csv'):
        if header_mode == HEADER_MODE_FIRST_ROW:
            df = pd.read_csv(file_storage, sep=None, engine='python', header=0, nrows=0)
            return list(df.columns)
        df = pd.read_csv(file_storage, sep=None, engine='python', header=None, nrows=1)
        return [f'Unnamed: {i}' for i in range(df.shape[1])]
    if filename.endswith('.pdf'):
        # PDF inspection forces a full parse; reuse the upload path.
        file_storage.seek(0)
        df = extract_tables_from_pdf(file_storage)
        if header_mode == HEADER_MODE_GENERIC:
            return [f'Unnamed: {i}' for i in range(df.shape[1])]
        return list(df.columns)
    # Excel: read first row only.
    if header_mode == HEADER_MODE_FIRST_ROW:
        df = pd.read_excel(file_storage, engine='calamine', header=0, nrows=0)
        return list(df.columns)
    df = pd.read_excel(file_storage, engine='calamine', header=None, nrows=1)
    return [f'Unnamed: {i}' for i in range(df.shape[1])]


def inspect_file_headers(file_storage, header_mode=HEADER_MODE_GENERIC, table_name=None):
    """Inspect a file's header row. Returns the columns, which ones exceed the
    Postgres byte limit (with suggestions), plus alias/existence context for the
    target table when provided. Never alters the database except for auto-backfilling
    aliases that map cleanly onto existing physical columns.
    """
    header_mode = _normalize_header_mode(header_mode)
    headers = [str(h) for h in _read_headers_only(file_storage, header_mode)]

    existing_data_cols = []
    aliases = {}
    if table_name:
        try:
            _validate_data_object_name(table_name)
            existing = execute_query(
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_schema='{LOCAL_SCHEMA}' AND table_name=:t "
                "ORDER BY ordinal_position",
                {"t": table_name},
            ) or []
            existing_data_cols = [r['column_name'] for r in existing if r['column_name'] not in SYSTEM_COLUMNS]
            if header_mode == HEADER_MODE_FIRST_ROW and existing_data_cols:
                _backfill_aliases_for_existing_table(table_name, existing_data_cols, headers)
            aliases = get_aliases_for_table(table_name)
        except ValueError:
            existing_data_cols = []
            aliases = {}

    existing_set = set(existing_data_cols)
    columns = []
    oversized = []
    for h in headers:
        b = len(h.encode('utf-8'))
        suggestion = suggest_shortened_name(h) if b > PG_MAX_IDENTIFIER_BYTES else h
        matched_alias = aliases.get(h)
        # In append mode, prefer the alias as suggestion (so file→table maps cleanly).
        if matched_alias and h != matched_alias:
            suggestion = matched_alias
        is_existing = (h in existing_set) or (matched_alias in existing_set if matched_alias else False)
        info = {
            "name": h,
            "bytes": b,
            "fits": b <= PG_MAX_IDENTIFIER_BYTES,
            "suggestion": suggestion,
            "matched_alias": matched_alias,
            "is_existing": is_existing,
        }
        columns.append(info)
        # Flag for the modal when: byte-oversized AND not already auto-resolved by alias.
        if b > PG_MAX_IDENTIFIER_BYTES and not matched_alias:
            oversized.append({
                "name": h,
                "bytes": b,
                "suggestion": suggestion,
            })

    return {
        "columns": columns,
        "oversized": oversized,
        "existing_columns": existing_data_cols,
        "max_bytes": PG_MAX_IDENTIFIER_BYTES,
        "header_mode": header_mode,
    }


def _read_uploaded_dataframe(file_storage, header_mode=HEADER_MODE_GENERIC):
    file_storage.seek(0)
    filename = file_storage.filename.lower()
    if filename.endswith('.csv'):
        if header_mode == HEADER_MODE_FIRST_ROW:
            return _read_csv_first_row(file_storage)
        return _read_csv_raw(file_storage)
    if filename.endswith('.pdf'):
        # PDF extractor's structure is fixed; the header_mode flag is a hint that
        # we honor only by renaming columns to Unnamed: <i> in generic mode.
        df = extract_tables_from_pdf(file_storage)
        if header_mode == HEADER_MODE_GENERIC:
            df.columns = [f'Unnamed: {i}' for i in range(df.shape[1])]
        return df
    if header_mode == HEADER_MODE_FIRST_ROW:
        return _read_excel_first_row(file_storage)
    return _read_excel_raw(file_storage)


def get_current_time_gmt3():
    tz = pytz.timezone('America/Sao_Paulo')
    return datetime.now(tz).replace(tzinfo=None)


def clean_table_name(filename):
    # Remove extension and special chars, keep alphanumeric and underscores
    name = filename.rsplit('.', 1)[0]
    cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', name).lower()
    # Prevent system table prefix
    while cleaned.startswith('_'):
        cleaned = cleaned[1:]
    if not cleaned:
        cleaned = 'table_upload'
    if cleaned == 'reports':
        cleaned = 'reports_upload'
    return cleaned


def _next_row_order(table_name):
    """Proxima posicao livre na sequencia de ordem do arquivo."""
    result = execute_query(
        f'SELECT COALESCE(MAX({_quote_column(ROW_ORDER_COLUMN)}), 0) AS ultima_ordem '
        f'FROM {_quote_identifier(table_name)}'
    )
    if not result or result[0]['ultima_ordem'] is None:
        return 1
    return int(result[0]['ultima_ordem']) + 1


def _backfill_row_order(table_name):
    """Numera linhas pre-existentes que estao sem ordem, pela ordem fisica atual (ctid).

    So aproxima a ordem original do arquivo: se a tabela sofreu UPDATE ou VACUUM
    desde a carga, o ctid ja nao reflete a ordem de insercao. Reenviar o arquivo
    (upload_excel) e a unica forma de recuperar a ordem com garantia.
    """
    quoted = _quote_identifier(table_name)
    qcol = _quote_column(ROW_ORDER_COLUMN)
    pending = execute_query(
        f'SELECT 1 FROM {quoted} WHERE {qcol} IS NULL LIMIT 1'
    )
    if not pending:
        return 0
    offset = _next_row_order(table_name) - 1
    execute_query(
        f"""
        UPDATE {quoted} AS t
        SET {qcol} = {offset} + s.seq
        FROM (
            SELECT ctid, row_number() OVER (ORDER BY ctid) AS seq
            FROM {quoted}
            WHERE {qcol} IS NULL
        ) AS s
        WHERE t.ctid = s.ctid
        """
    )
    print(f"INFO: Backfilled {ROW_ORDER_COLUMN} on pre-existing rows of {table_name}", flush=True)
    return 1


def _apply_row_order(df, start):
    """Materializa a ordem das linhas do arquivo numa coluna persistida."""
    if ROW_ORDER_COLUMN in df.columns:
        df = df.drop(columns=[ROW_ORDER_COLUMN])
    df[ROW_ORDER_COLUMN] = range(start, start + len(df))
    return df


def upload_excel(file_storage, table_name=None, header_mode=HEADER_MODE_GENERIC, column_renames=None):
    try:
        header_mode = _normalize_header_mode(header_mode)
        df = _read_uploaded_dataframe(file_storage, header_mode=header_mode)
        filename = file_storage.filename.lower()

        print(f"DEBUG: Uploading {filename} (header_mode={header_mode})", flush=True)
        print(f"DEBUG: Shape: {df.shape}", flush=True)
        print(f"DEBUG: Columns: {df.columns.tolist()}", flush=True)

        if df.empty:
            raise Exception("The uploaded file contains no data (empty dataframe).")

        original_columns = df.columns.tolist()
        df = _apply_column_renames(df, column_renames or {})
        df[TIMESTAMP_COLUMN] = get_current_time_gmt3()
        df = _apply_row_order(df, start=1)
        df = _normalize_dataframe_columns(df)

        table_name = clean_table_name(table_name if table_name else file_storage.filename)
        _validate_data_object_name(table_name)

        print(f"DEBUG: Creating table {table_name} with TEXT columns...", flush=True)
        _create_text_table(table_name, df.columns.tolist())

        df_text = _serialize_dataframe_as_text(df)
        df_text.to_sql(table_name, engine, if_exists='append', index=False)
        print(f"DEBUG: Inserted {len(df_text)} rows into {table_name}", flush=True)

        # Persist aliases: original full name -> physical (renamed) column.
        remove_aliases_for_table(table_name)
        for original in original_columns:
            physical = (column_renames or {}).get(original, original)
            upsert_alias(table_name, physical, original)

        return {"message": f"Table '{table_name}' created successfully", "rows": len(df), "table_name": table_name}
    except OversizedColumnError:
        raise
    except Exception as e:
        raise Exception(f"Error processing file: {str(e)}")


def _shortening_candidates(name):
    """Possible physical-column candidates for a long name, in priority order.

    Covers both the legacy UTF-8 truncation and the diacritic-stripping suggestion,
    so backfills work for pre-alias-era tables truncated by either algorithm.
    """
    candidates = []
    seen = set()

    def add(c):
        if c and c not in seen:
            seen.add(c)
            candidates.append(c)

    add(_utf8_truncate(name, PG_MAX_IDENTIFIER_BYTES))
    stripped = _strip_diacritics(name)
    if len(stripped.encode('utf-8')) <= PG_MAX_IDENTIFIER_BYTES:
        add(stripped)
    add(_utf8_truncate(stripped, PG_MAX_IDENTIFIER_BYTES))
    return candidates


def _backfill_aliases_for_existing_table(table_name, existing_data_cols, file_cols):
    """Auto-create aliases for file columns whose canonical truncation matches an
    existing physical column. Lets pre-alias-era tables become alias-aware on
    the first append after this feature shipped.
    """
    existing_aliases = get_aliases_for_table(table_name)
    existing_set = set(existing_data_cols)
    created = {}
    for fc in file_cols:
        if fc in existing_set or fc in existing_aliases:
            continue
        if len(fc.encode('utf-8')) <= PG_MAX_IDENTIFIER_BYTES:
            continue
        for candidate in _shortening_candidates(fc):
            if candidate in existing_set:
                upsert_alias(table_name, candidate, fc)
                created[fc] = candidate
                break
    if created:
        print(f"INFO: Backfilled aliases for {table_name}: {created}", flush=True)
    return created


def append_excel(file_storage, table_name, header_mode=HEADER_MODE_GENERIC, column_renames=None):
    try:
        _validate_data_object_name(table_name)
        header_mode = _normalize_header_mode(header_mode)

        existing = execute_query(
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_schema='{LOCAL_SCHEMA}' AND table_name=:t "
            "ORDER BY ordinal_position",
            {"t": table_name},
        ) or []
        existing_data_cols = [r['column_name'] for r in existing if r['column_name'] not in SYSTEM_COLUMNS]

        # Enforce mode/schema compatibility BEFORE reading the file, so the user
        # gets a clear error pointing at the configuration mismatch.
        if existing_data_cols:
            table_is_generic = _is_generic_schema(existing_data_cols)
            if header_mode == HEADER_MODE_GENERIC and not table_is_generic:
                raise IncompatibleHeaderModeError(table_name, header_mode, 'semantic')
            if header_mode == HEADER_MODE_FIRST_ROW and table_is_generic:
                raise IncompatibleHeaderModeError(table_name, header_mode, 'generic')

        df = _read_uploaded_dataframe(file_storage, header_mode=header_mode)
        filename = file_storage.filename.lower()

        print(f"DEBUG: Appending file {filename} to {table_name} (header_mode={header_mode})", flush=True)

        if df.empty:
            raise Exception("The uploaded file contains no data (empty dataframe).")

        original_columns = df.columns.tolist()

        # First, apply explicit user-provided renames.
        df = _apply_column_renames(df, column_renames or {})

        # Then resolve aliases: file column names (post explicit-rename) that match
        # an alias get mapped to the physical column. Backfill aliases for any
        # oversized file column whose canonical short form already exists in the table.
        if header_mode == HEADER_MODE_FIRST_ROW and existing_data_cols:
            _backfill_aliases_for_existing_table(table_name, existing_data_cols, df.columns.tolist())
            aliases = get_aliases_for_table(table_name)
            alias_renames = {c: aliases[c] for c in df.columns if c in aliases}
            if alias_renames:
                print(f"DEBUG: Applying alias renames: {alias_renames}", flush=True)
                df = df.rename(columns=alias_renames)

        if existing_data_cols:
            if header_mode == HEADER_MODE_GENERIC:
                if len(df.columns) != len(existing_data_cols):
                    raise ColumnCountMismatchError(
                        table_name,
                        file_count=len(df.columns),
                        table_count=len(existing_data_cols),
                    )
                df.columns = existing_data_cols
            else:  # HEADER_MODE_FIRST_ROW
                file_cols = set(df.columns)
                table_cols = set(existing_data_cols)
                missing_in_table = file_cols - table_cols
                missing_in_file = table_cols - file_cols
                if missing_in_table or missing_in_file:
                    raise ColumnNameMismatchError(
                        table_name,
                        missing_in_table=sorted(missing_in_table),
                        missing_in_file=sorted(missing_in_file),
                    )

        df[TIMESTAMP_COLUMN] = get_current_time_gmt3()
        df = _apply_row_order(df, start=1)
        df = _normalize_dataframe_columns(df)

        _reconcile_table_schema(table_name, df.columns.tolist())
        # A coluna de ordem so existe apos o reconcile em tabelas antigas.
        _backfill_row_order(table_name)
        df = _apply_row_order(df, start=_next_row_order(table_name))

        df_text = _serialize_dataframe_as_text(df)
        df_text.to_sql(table_name, engine, if_exists='append', index=False)
        print(f"DEBUG: Appended {len(df_text)} rows to {table_name}", flush=True)

        # Save aliases for any explicit user rename so future appends auto-resolve.
        if column_renames:
            for original, physical in column_renames.items():
                if original in original_columns:
                    upsert_alias(table_name, physical, original)

        return {"message": f"Data appended to '{table_name}' successfully", "rows": len(df)}
    except (ColumnCountMismatchError, ColumnNameMismatchError, IncompatibleHeaderModeError, OversizedColumnError):
        raise
    except Exception as e:
        raise Exception(f"Error appending file: {str(e)}")


def insert_row(table_name, data):
    """
    Inserts a single row into the specified table.
    data: dict where keys are column names and values are values.
    """
    print(f"DEBUG: insert_row called for {table_name}", flush=True)
    print(f"DEBUG: Data received: {data}", flush=True)

    _validate_data_object_name(table_name)

    data = dict(data)
    data.pop(ROW_ORDER_COLUMN, None)
    data[TIMESTAMP_COLUMN] = get_current_time_gmt3()

    df = pd.DataFrame([data])
    df = _apply_row_order(df, start=1)
    df = _normalize_dataframe_columns(df)
    print(f"DEBUG: DataFrame created:\n{df}", flush=True)

    try:
        _reconcile_table_schema(table_name, df.columns.tolist())
        _backfill_row_order(table_name)
        df = _apply_row_order(df, start=_next_row_order(table_name))
        df_text = _serialize_dataframe_as_text(df)
        df_text.to_sql(table_name, engine, if_exists='append', index=False)
        print("DEBUG: Insertion successful", flush=True)
        return {"message": "Data inserted successfully"}
    except Exception as e:
        print(f"DEBUG: Insertion failed: {str(e)}", flush=True)
        raise Exception(f"Failed to insert data: {str(e)}")
