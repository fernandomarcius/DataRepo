"""Unit tests for the external-connection service.

The DDL/provisioning paths require a live Postgres with tds_fdw, so we mock
db.engine and exercise validation, normalization and crypto round-trips.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")
os.environ.setdefault(
    "CONNECTIONS_ENCRYPTION_KEY",
    "test-passphrase-for-unit-tests-only-32chars",
)

_mock_engine = MagicMock()
_mock_execute_query = MagicMock(return_value=[])

sys.modules.setdefault(
    "db",
    MagicMock(engine=_mock_engine, execute_query=_mock_execute_query),
)

from services import connection_service as svc  # noqa: E402 -- import depois do setup de sys.modules acima
from services.connection_service import (  # noqa: E402 -- import depois do setup de sys.modules acima
    ConnectionValidationError,
    _decrypt,
    _encrypt,
    _local_schema,
    _normalize_payload,
    _quote_literal,
    _server_options_sql,
    _user_mapping_options_sql,
    create_connection,
    list_connection_catalog,
    safe_connection_error,
    update_connection,
)


class TestCrypto(unittest.TestCase):
    def test_encrypt_decrypt_roundtrip(self):
        ciphertext = _encrypt("hunter2!")
        self.assertNotEqual(ciphertext, "hunter2!")
        self.assertEqual(_decrypt(ciphertext), "hunter2!")

    def test_decrypt_garbage_raises(self):
        with self.assertRaises(Exception):
            _decrypt("not-a-valid-token")

    def test_safe_connection_error_redacts_passwords(self):
        msg = safe_connection_error(
            Exception("CREATE USER MAPPING OPTIONS (user 'u', password 'hunter2!') failed"),
            "hunter2!",
        )
        self.assertNotIn("hunter2!", msg)
        self.assertIn("[redacted]", msg)


class TestPayloadValidation(unittest.TestCase):
    def _base(self, **overrides):
        payload = {
            "name": "vendas",
            "display_name": "Vendas SQL Server",
            "db_type": "sqlserver",
            "host": "10.0.0.5",
            "database": "Vendas",
            "username": "leitor",
            "password": "s3nha",
        }
        payload.update(overrides)
        return payload

    def test_normalizes_sqlserver_with_defaults(self):
        result = _normalize_payload(self._base())
        self.assertEqual(result["port"], 1433)
        self.assertEqual(result["remote_schema"], "dbo")
        self.assertNotEqual(result["password_enc"], "s3nha")
        self.assertEqual(_decrypt(result["password_enc"]), "s3nha")

    def test_normalizes_postgres_with_defaults(self):
        result = _normalize_payload(self._base(db_type="postgres"))
        self.assertEqual(result["port"], 5432)
        self.assertEqual(result["remote_schema"], "public")

    def test_rejects_invalid_name(self):
        with self.assertRaises(ConnectionValidationError):
            _normalize_payload(self._base(name="Vendas BR"))
        with self.assertRaises(ConnectionValidationError):
            _normalize_payload(self._base(name="1abc"))

    def test_rejects_unknown_type(self):
        with self.assertRaises(ConnectionValidationError):
            _normalize_payload(self._base(db_type="oracle"))

    def test_rejects_invalid_port(self):
        with self.assertRaises(ConnectionValidationError):
            _normalize_payload(self._base(port=70000))
        with self.assertRaises(ConnectionValidationError):
            _normalize_payload(self._base(port="abc"))

    def test_password_inherited_from_existing_when_omitted(self):
        existing = _normalize_payload(self._base())
        partial = self._base()
        partial.pop("password")
        partial["host"] = "10.0.0.99"
        merged = _normalize_payload(partial, existing=existing)
        self.assertEqual(merged["host"], "10.0.0.99")
        self.assertEqual(_decrypt(merged["password_enc"]), "s3nha")

    def test_missing_password_without_existing_fails(self):
        partial = self._base()
        partial.pop("password")
        with self.assertRaises(ConnectionValidationError):
            _normalize_payload(partial)


class TestSqlBuilders(unittest.TestCase):
    def test_local_schema_naming(self):
        self.assertEqual(_local_schema("vendas"), "ext_vendas")

    def test_quote_literal_escapes_single_quote(self):
        self.assertEqual(_quote_literal("o'reilly"), "'o''reilly'")

    def test_sqlserver_options_sql(self):
        sql = _server_options_sql({
            "db_type": "sqlserver",
            "host": "10.0.0.5",
            "port": 1433,
            "database": "Vendas",
        })
        self.assertIn("servername '10.0.0.5'", sql)
        self.assertIn("port '1433'", sql)
        self.assertIn("database 'Vendas'", sql)

    def test_postgres_options_sql(self):
        sql = _server_options_sql({
            "db_type": "postgres",
            "host": "pg.example.com",
            "port": 5432,
            "database": "analytics",
        })
        self.assertIn("host 'pg.example.com'", sql)
        self.assertIn("dbname 'analytics'", sql)

    def test_sqlserver_user_mapping_uses_tds_option_name(self):
        sql = _user_mapping_options_sql({
            "db_type": "sqlserver",
            "username": "leitor",
        }, "s3nha")
        self.assertIn("username 'leitor'", sql)
        self.assertNotIn("user 'leitor'", sql)

    def test_postgres_user_mapping_uses_postgres_fdw_option_name(self):
        sql = _user_mapping_options_sql({
            "db_type": "postgres",
            "username": "leitor",
        }, "s3nha")
        self.assertIn("user 'leitor'", sql)


class TestConnectionCatalog(unittest.TestCase):
    def test_catalog_omits_endpoint_and_credentials(self):
        with patch.object(svc, "execute_query", return_value=[{
            "id": 7,
            "name": "vendas",
            "display_name": "Vendas",
            "db_type": "sqlserver",
            "remote_schema": "dbo",
            "last_synced_at": None,
        }]):
            catalog = list_connection_catalog()

        self.assertEqual(catalog[0]["schema_name"], "ext_vendas")
        self.assertNotIn("host", catalog[0])
        self.assertNotIn("database", catalog[0])
        self.assertNotIn("username", catalog[0])
        self.assertNotIn("options", catalog[0])


class TestProvisioningSafety(unittest.TestCase):
    def _existing(self):
        encrypted = _normalize_payload({
            "name": "vendas",
            "display_name": "Vendas SQL Server",
            "db_type": "sqlserver",
            "host": "10.0.0.5",
            "database": "Vendas",
            "username": "leitor",
            "password": "s3nha",
        })
        return {
            **encrypted,
            "id": 1,
            "options": {},
        }

    def test_create_deprovisions_if_insert_fails_after_successful_provision(self):
        with patch.object(svc, "execute_query", side_effect=[[], RuntimeError("unique violation")]), \
             patch.object(svc, "_provision", return_value=3), \
             patch.object(svc, "_deprovision") as deprovision:
            with self.assertRaises(RuntimeError):
                create_connection({
                    "name": "vendas",
                    "display_name": "Vendas SQL Server",
                    "db_type": "sqlserver",
                    "host": "10.0.0.5",
                    "database": "Vendas",
                    "username": "leitor",
                    "password": "s3nha",
                })

        deprovision.assert_called_once_with("vendas")

    def test_update_keeps_existing_objects_when_staged_provision_fails(self):
        with patch.object(svc, "execute_query", return_value=[self._existing()]), \
             patch.object(svc, "_provision", side_effect=RuntimeError("password 's3nha' failed")), \
             patch.object(svc, "_replace_provisioned_objects") as replace_objects, \
             patch.object(svc, "_deprovision") as deprovision:
            with self.assertRaises(RuntimeError):
                update_connection(1, {"host": "10.0.0.99"})

        replace_objects.assert_not_called()
        self.assertNotIn("vendas", [call.args[0] for call in deprovision.call_args_list])


if __name__ == "__main__":
    unittest.main()
