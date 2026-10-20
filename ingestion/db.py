import os
from sqlalchemy import create_engine, text

from kit.serialization import convert_to_serializable

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/data_app")

LOCAL_SCHEMA = os.getenv("LOCAL_SCHEMA", "public")

engine = create_engine(DATABASE_URL)


def get_db_connection():
    return engine.connect()


def execute_query(query, params=None):
    with engine.connect() as conn:
        result = conn.execute(text(query), params or {})
        conn.commit()
        try:
            keys = result.keys()
            rows = []
            for row in result.fetchall():
                row_dict = {}
                for key, value in zip(keys, row):
                    row_dict[key] = convert_to_serializable(value)
                rows.append(row_dict)
            return rows
        except Exception:
            return None


def _rows_to_dicts(result):
    keys = result.keys()
    rows = []
    for row in result.fetchall():
        row_dict = {}
        for key, value in zip(keys, row):
            row_dict[key] = convert_to_serializable(value)
        rows.append(row_dict)
    return rows


def execute_readonly_query(query, statement_timeout_ms=240000):
    """Execute a user query inside a read-only transaction.

    SQLAlchemy + psycopg2 use pyformat paramstyle, so any literal '%' in the
    query (LIKE patterns, regex, etc.) is interpreted as a format marker and
    blows up with "immutabledict is not a sequence" when SQLAlchemy passes
    an empty immutabledict as parameters. We use the raw DBAPI cursor with
    no parameters, which skips %-interpolation entirely.
    """
    raw_conn = engine.raw_connection()
    try:
        raw_conn.autocommit = False
        cursor = raw_conn.cursor()
        try:
            cursor.execute(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}")
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(query)
            keys = [desc[0] for desc in cursor.description] if cursor.description else []
            fetched = cursor.fetchall() if cursor.description else []
            rows = []
            for row in fetched:
                row_dict = {k: convert_to_serializable(v) for k, v in zip(keys, row)}
                rows.append(row_dict)
            return rows
        finally:
            cursor.close()
            raw_conn.rollback()
    finally:
        raw_conn.close()
