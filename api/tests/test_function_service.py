"""Unit tests for managed SQL function validation."""
import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")

_mock_engine = MagicMock()
_mock_execute_query = MagicMock(return_value=[])

sys.modules.setdefault(
    "db",
    MagicMock(engine=_mock_engine, execute_query=_mock_execute_query),
)

from services.function_service import (  # noqa: E402 -- import depois do setup de sys.modules acima
    FunctionValidationError,
    build_call_example,
    build_signature,
    normalize_function_payload,
    validate_readonly_sql,
)


class TestReadonlySqlValidation(unittest.TestCase):

    def test_accepts_select(self):
        self.assertEqual(validate_readonly_sql("SELECT 1;"), "SELECT 1")

    def test_accepts_with_select(self):
        sql = "WITH x AS (SELECT 1 AS n) SELECT n FROM x"
        self.assertEqual(validate_readonly_sql(sql), sql)

    def test_rejects_insert(self):
        with self.assertRaises(FunctionValidationError):
            validate_readonly_sql("INSERT INTO t VALUES (1)")

    def test_rejects_data_modifying_cte(self):
        with self.assertRaises(FunctionValidationError):
            validate_readonly_sql("WITH x AS (DELETE FROM t RETURNING id) SELECT * FROM x")

    def test_allows_forbidden_word_inside_string(self):
        self.assertEqual(validate_readonly_sql("SELECT 'drop table' AS msg"), "SELECT 'drop table' AS msg")

    def test_rejects_multiple_statements(self):
        with self.assertRaises(FunctionValidationError):
            validate_readonly_sql("SELECT 1; SELECT 2")


class TestFunctionPayload(unittest.TestCase):

    def test_normalizes_scalar_function(self):
        payload = normalize_function_payload({
            "name": "Calcular Total",
            "kind": "scalar",
            "parameters": [{"name": "valor", "type": "numeric"}],
            "return_type": "numeric",
            "sql_body": "SELECT valor * 2",
        })

        self.assertEqual(payload["function_name"], "fn_calcular_total")
        self.assertEqual(payload["parameters"], [{"name": "valor", "type": "numeric"}])
        self.assertEqual(build_signature(payload), "fn_calcular_total(valor numeric) RETURNS numeric")
        self.assertEqual(build_call_example(payload), "fn_calcular_total(valor)")

    def test_normalizes_table_function(self):
        payload = normalize_function_payload({
            "name": "Linhas Ativas",
            "kind": "table",
            "return_columns": [
                {"name": "id", "type": "bigint"},
                {"name": "nome", "type": "text"},
            ],
            "sql_body": "SELECT 1::bigint AS id, 'a' AS nome",
        })

        self.assertEqual(payload["kind"], "table")
        self.assertEqual(build_call_example(payload), "SELECT * FROM fn_linhas_ativas()")

    def test_rejects_function_name_without_prefix(self):
        with self.assertRaises(FunctionValidationError):
            normalize_function_payload({
                "name": "Teste",
                "function_name": "teste",
                "kind": "scalar",
                "return_type": "text",
                "sql_body": "SELECT 'ok'",
            })

    def test_rejects_unknown_type(self):
        with self.assertRaises(FunctionValidationError):
            normalize_function_payload({
                "name": "Teste",
                "kind": "scalar",
                "return_type": "regclass",
                "sql_body": "SELECT 'ok'",
            })


if __name__ == "__main__":
    unittest.main()
