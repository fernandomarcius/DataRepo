"""Conversao de tipos do Postgres para JSON (compartilhada por db e audit_client)."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import uuid


def convert_to_serializable(value):
    """Convert PostgreSQL-specific types to JSON-serializable formats."""
    if value is None:
        return None

    # Handle NumericRange, Int4Range, Int8Range, DateRange, etc.
    if hasattr(value, 'lower') and hasattr(value, 'upper') and hasattr(value, 'bounds'):
        return {
            'lower': convert_to_serializable(value.lower),
            'upper': convert_to_serializable(value.upper),
            'bounds': value.bounds if hasattr(value, 'bounds') else '[)'
        }

    # Handle datetime types
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)

    # Handle Decimal
    if isinstance(value, Decimal):
        return float(value)

    # Handle UUID
    if isinstance(value, uuid.UUID):
        return str(value)

    # Handle bytes/memoryview
    if isinstance(value, (bytes, memoryview)):
        return value.hex() if isinstance(value, bytes) else bytes(value).hex()

    # Handle lists/tuples containing special types
    if isinstance(value, (list, tuple)):
        return [convert_to_serializable(item) for item in value]

    # Handle nested dicts
    if isinstance(value, dict):
        return {k: convert_to_serializable(v) for k, v in value.items()}

    return value
