"""Catalog routes — permission gates, report/view coupling, column aliases."""
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")

_mock_engine = MagicMock()
_mock_execute_query = MagicMock(return_value=[])
sys.modules.setdefault(
    "db",
    MagicMock(engine=_mock_engine, execute_query=_mock_execute_query, LOCAL_SCHEMA="public",
              execute_readonly_query=MagicMock()),
)

import jwt  # noqa: E402 -- import depois do setup de sys.modules acima

from kit.auth import PERMISSION_FLAGS  # noqa: E402 -- import depois do setup de sys.modules acima


def _auth(**perms):
    now = int(time.time())
    payload = {
        "sub": "1",
        "username": "testuser",
        "perms": {flag: perms.get(flag, False) for flag in PERMISSION_FLAGS},
        "iat": now,
        "exp": now + 3600,
    }
    return {"Authorization": "Bearer " + jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")}


class TestCatalogRoutes(unittest.TestCase):

    def setUp(self):
        self._engine_patcher = patch("db.engine", _mock_engine)
        self._eq_patcher = patch("db.execute_query", _mock_execute_query)
        self._engine_patcher.start()
        self._eq_patcher.start()

        from app import app  # noqa: PLC0415 -- import tardio para usar os mocks ja instalados
        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        self._engine_patcher.stop()
        self._eq_patcher.stop()

    # ------------------------------------------------------------------
    # /api/v1/tables  (login_required only, no permission flag)
    # ------------------------------------------------------------------

    @patch("routes.catalog.get_tables")
    def test_tables_no_token_is_401(self, _mock_get_tables):
        self.assertEqual(self.client.get("/api/v1/tables").status_code, 401)

    @patch("routes.catalog.get_tables", return_value=[])
    def test_tables_valid_token_all_perms_false_is_200(self, _mock_get_tables):
        self.assertEqual(self.client.get("/api/v1/tables", headers=_auth()).status_code, 200)

    def test_rename_table_requires_manage_views_permission(self):
        resp = self.client.put("/api/v1/tables/sales", json={"new_name": "sales_2026"},
                               headers=_auth(can_manage_views=False))
        self.assertEqual(resp.status_code, 403)

    @patch("routes.catalog.sync_report_name_for_view_rename")
    @patch("routes.catalog.rename_data_object")
    def test_rename_table_with_manage_views_permission(self, mock_rename, mock_sync):
        mock_rename.return_value = {"name": "sales_2026", "previous_name": "sales", "type": "table"}
        resp = self.client.put("/api/v1/tables/sales", json={"new_name": "sales_2026"},
                               headers=_auth(can_manage_views=True))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["name"], "sales_2026")
        mock_sync.assert_not_called()
        self.assertEqual([e["action"] for e in self.audit_events], ["RENAME"])

    @patch("routes.catalog.sync_report_name_for_view_rename")
    @patch("routes.catalog.rename_data_object")
    def test_rename_view_syncs_saved_report_name(self, mock_rename, mock_sync):
        mock_rename.return_value = {"name": "sales_view_2026", "previous_name": "sales_view", "type": "view"}
        mock_sync.return_value = {"id": 7, "name": "sales_view_2026", "view_name": "sales_view_2026"}
        resp = self.client.put("/api/v1/tables/sales_view", json={"new_name": "sales_view_2026"},
                               headers=_auth(can_manage_views=True))
        self.assertEqual(resp.status_code, 200)
        mock_sync.assert_called_once_with("sales_view", "sales_view_2026")

    def test_delete_table_requires_manage_views_permission(self):
        resp = self.client.delete("/api/v1/tables/sales", headers=_auth(can_manage_views=False))
        self.assertEqual(resp.status_code, 403)

    @patch("routes.catalog.delete_data_object", return_value={"name": "sales_view", "type": "view"})
    def test_delete_view_with_manage_views_permission(self, _mock_delete):
        resp = self.client.delete("/api/v1/tables/sales_view", headers=_auth(can_manage_views=True))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["type"], "view")

    # ------------------------------------------------------------------
    # /api/v1/tables/<n>/schema — aliases written by ingestion, read here
    # ------------------------------------------------------------------

    @patch("routes.catalog.get_aliases_for_table", return_value={"Nome original bem longo": "nome_original"})
    @patch("routes.catalog.get_table_schema")
    def test_schema_merges_column_aliases(self, mock_schema, mock_aliases):
        mock_schema.return_value = [{"column_name": "nome_original", "data_type": "text"},
                                    {"column_name": "outra", "data_type": "text"}]
        resp = self.client.get("/api/v1/tables/vendas/schema", headers=_auth())
        self.assertEqual(resp.status_code, 200)
        schema = resp.get_json()["schema"]
        self.assertEqual(schema[0]["alias"], "Nome original bem longo")
        self.assertIsNone(schema[1]["alias"])
        mock_aliases.assert_called_once_with("vendas")

    # ------------------------------------------------------------------
    # /api/v1/reports
    # ------------------------------------------------------------------

    def test_create_report_requires_manage_views(self):
        resp = self.client.post("/api/v1/reports", json={"name": "r", "sql_query": "SELECT 1"},
                                headers=_auth(can_query=True))
        self.assertEqual(resp.status_code, 403)

    @patch("routes.catalog.execute_readonly_query")
    @patch("routes.catalog.get_report", return_value={"id": 1, "view_name": "r", "sql_query": "DELETE FROM x"})
    def test_execute_report_refuses_non_readonly_sql(self, _mock_get, mock_exec):
        resp = self.client.get("/api/v1/reports/1/execute", headers=_auth())
        self.assertEqual(resp.status_code, 403)
        mock_exec.assert_not_called()

    @patch("routes.catalog.execute_readonly_query", return_value=[{"n": 1}])
    @patch("routes.catalog.get_report", return_value={"id": 1, "view_name": "r", "sql_query": "SELECT 1 AS n"})
    def test_execute_report(self, _mock_get, _mock_exec):
        resp = self.client.get("/api/v1/reports/1/execute", headers=_auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["results"], [{"n": 1}])


if __name__ == "__main__":
    unittest.main()
