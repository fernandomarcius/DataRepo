"""query HTTP route — permission gate and read-only guard. DB fully mocked."""
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")

sys.modules.setdefault(
    "db",
    MagicMock(engine=MagicMock(), execute_query=MagicMock(return_value=[]), execute_readonly_query=MagicMock()),
)

import jwt  # noqa: E402 -- import depois do setup de sys.modules acima

from kit.auth import PERMISSION_FLAGS  # noqa: E402 -- import depois do setup de sys.modules acima


def _token(**perms):
    now = int(time.time())
    payload = {
        "sub": "1",
        "username": "testuser",
        "perms": {flag: perms.get(flag, False) for flag in PERMISSION_FLAGS},
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")


class TestQueryRoute(unittest.TestCase):

    def setUp(self):
        from app import app  # noqa: PLC0415 -- import tardio para usar os mocks ja instalados
        app.config["TESTING"] = True
        self.client = app.test_client()

    def _post(self, sql, **perms):
        return self.client.post(
            "/api/v1/query",
            json={"sql": sql},
            headers={"Authorization": f"Bearer {_token(**perms)}"},
        )

    def test_requires_login(self):
        self.assertEqual(self.client.post("/api/v1/query", json={"sql": "SELECT 1"}).status_code, 401)

    def test_permission_required_returns_403_when_missing(self):
        self.assertEqual(self._post("SELECT 1", can_query=False).status_code, 403)

    @patch("routes.query.execute_readonly_query")
    def test_permission_required_passes_when_present(self, mock_q):
        mock_q.return_value = [{"result": 1}]
        resp = self._post("SELECT 1;", can_query=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["results"], [{"result": 1}])
        mock_q.assert_called_once_with("SELECT 1")

    @patch("routes.query.execute_readonly_query")
    def test_write_sql_is_403_and_never_executed(self, mock_q):
        resp = self._post("DELETE FROM vendas", can_query=True)
        self.assertEqual(resp.status_code, 403)
        mock_q.assert_not_called()

    def test_missing_sql_is_400(self):
        self.assertEqual(self._post("", can_query=True).status_code, 400)

    @patch("routes.query.execute_readonly_query", side_effect=Exception("relation does not exist"))
    def test_database_error_is_500(self, _mock_q):
        resp = self._post("SELECT * FROM nada", can_query=True)
        self.assertEqual(resp.status_code, 500)
        self.assertIn("does not exist", resp.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
