"""functions HTTP routes — permission gates and audit events. DB fully mocked."""
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")

_mock_engine = MagicMock()
_mock_execute_query = MagicMock(return_value=[])
sys.modules.setdefault("db", MagicMock(engine=_mock_engine, execute_query=_mock_execute_query, LOCAL_SCHEMA="public"))

import jwt  # noqa: E402 -- import depois do setup de sys.modules acima

from kit.auth import PERMISSION_FLAGS  # noqa: E402 -- import depois do setup de sys.modules acima


def _token(uid=1, username="testuser", **perms):
    now = int(time.time())
    payload = {
        "sub": str(uid),
        "username": username,
        "perms": {flag: perms.get(flag, False) for flag in PERMISSION_FLAGS},
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")


PAYLOAD = {"name": "Teste", "kind": "scalar", "return_type": "text", "sql_body": "SELECT 'ok'"}


class TestFunctionRoutes(unittest.TestCase):

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

    def test_create_requires_manage_functions_permission(self):
        resp = self.client.post(
            "/api/v1/functions",
            json=PAYLOAD,
            headers={"Authorization": f"Bearer {_token(can_manage_functions=False)}"},
        )
        self.assertEqual(resp.status_code, 403)

    @patch("routes.functions.create_function")
    def test_create_passes_when_permission_present(self, mock_create):
        mock_create.return_value = {
            "id": 1,
            "name": "Teste",
            "function_name": "fn_teste",
            "kind": "scalar",
            "signature": "fn_teste() RETURNS text",
        }
        resp = self.client.post(
            "/api/v1/functions",
            json=PAYLOAD,
            headers={"Authorization": f"Bearer {_token(can_manage_functions=True)}"},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["function_name"], "fn_teste")
        self.assertEqual([e["action"] for e in self.audit_events], ["CREATE"])
        self.assertEqual(self.audit_events[0]["entity_type"], "function")

    @patch("routes.functions.list_functions", return_value=[])
    def test_list_hides_body_without_manage_permission(self, mock_list):
        resp = self.client.get("/api/v1/functions", headers={"Authorization": f"Bearer {_token()}"})
        self.assertEqual(resp.status_code, 200)
        mock_list.assert_called_once_with(include_body=False)

    @patch("routes.functions.list_functions", return_value=[])
    def test_list_includes_body_with_manage_permission(self, mock_list):
        resp = self.client.get(
            "/api/v1/functions",
            headers={"Authorization": f"Bearer {_token(can_manage_functions=True)}"},
        )
        self.assertEqual(resp.status_code, 200)
        mock_list.assert_called_once_with(include_body=True)


if __name__ == "__main__":
    unittest.main()
