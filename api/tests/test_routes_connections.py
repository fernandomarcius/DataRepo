"""connections HTTP routes — permission split between managers and query users."""
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")
os.environ.setdefault("CONNECTIONS_ENCRYPTION_KEY", "unit-test-passphrase-with-at-least-32-chars")

_mock_engine = MagicMock()
_mock_execute_query = MagicMock(return_value=[])
sys.modules.setdefault("db", MagicMock(engine=_mock_engine, execute_query=_mock_execute_query))

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


class TestConnectionRoutes(unittest.TestCase):

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

    @patch("routes.connections.list_connection_catalog", return_value=[{"id": 1}])
    @patch("routes.connections.list_connections", return_value=[{"id": 1, "host": "h"}])
    def test_manager_gets_full_list(self, mock_full, mock_catalog):
        resp = self.client.get("/api/v1/connections", headers=_auth(can_manage_connections=True))
        self.assertEqual(resp.status_code, 200)
        mock_full.assert_called_once()
        mock_catalog.assert_not_called()

    @patch("routes.connections.list_connection_catalog", return_value=[{"id": 1}])
    @patch("routes.connections.list_connections")
    def test_query_user_gets_catalog_only(self, mock_full, mock_catalog):
        resp = self.client.get("/api/v1/connections", headers=_auth(can_query=True))
        self.assertEqual(resp.status_code, 200)
        mock_full.assert_not_called()
        mock_catalog.assert_called_once()

    def test_user_without_either_permission_is_403(self):
        resp = self.client.get("/api/v1/connections", headers=_auth())
        self.assertEqual(resp.status_code, 403)

    def test_create_requires_manage_permission(self):
        resp = self.client.post("/api/v1/connections", json={"name": "x"}, headers=_auth(can_query=True))
        self.assertEqual(resp.status_code, 403)

    @patch("routes.connections.create_connection", side_effect=Exception("could not connect: password=hunter2"))
    def test_create_failure_never_leaks_password(self, _mock_create):
        resp = self.client.post(
            "/api/v1/connections",
            json={"name": "erp", "password": "hunter2"},
            headers=_auth(can_manage_connections=True),
        )
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn("hunter2", resp.get_data(as_text=True))
        self.assertEqual(len(self.audit_events), 1)
        self.assertNotIn("hunter2", repr(self.audit_events[0]))


if __name__ == "__main__":
    unittest.main()
