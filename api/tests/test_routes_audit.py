"""audit HTTP routes: public query endpoints and the internal ingest endpoint."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")
os.environ.setdefault("INTERNAL_API_TOKEN", "test-internal-token")

_mock_engine = MagicMock()
_mock_execute_query = MagicMock(return_value=[])
sys.modules.setdefault("db", MagicMock(engine=_mock_engine, execute_query=_mock_execute_query))

import time  # noqa: E402 -- import depois do setup de sys.modules acima

import jwt  # noqa: E402 -- import depois do setup de sys.modules acima

from kit.auth import PERMISSION_FLAGS  # noqa: E402 -- import depois do setup de sys.modules acima
from kit.internal import INTERNAL_TOKEN_HEADER  # noqa: E402 -- import depois do setup de sys.modules acima


def _token(uid=1, username="admin", **perms):
    now = int(time.time())
    payload = {
        "sub": str(uid),
        "username": username,
        "perms": {flag: perms.get(flag, False) for flag in PERMISSION_FLAGS},
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")


class TestAuditRoutes(unittest.TestCase):

    def setUp(self):
        self._engine_patcher = patch("db.engine", _mock_engine)
        self._eq_patcher = patch("db.execute_query", _mock_execute_query)
        self._engine_patcher.start()
        self._eq_patcher.start()

        from app import app  # noqa: PLC0415 -- import tardio para usar os mocks ja instalados
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.internal = {INTERNAL_TOKEN_HEADER: os.environ["INTERNAL_API_TOKEN"]}

    def tearDown(self):
        self._engine_patcher.stop()
        self._eq_patcher.stop()

    # ------------------------------------------------------------------
    # GET /api/v1/audit-logs
    # ------------------------------------------------------------------

    def test_audit_logs_requires_login(self):
        self.assertEqual(self.client.get("/api/v1/audit-logs").status_code, 401)

    def test_audit_logs_requires_permission(self):
        token = _token(uid=2, username="noaudit", can_view_audit=False)
        resp = self.client.get("/api/v1/audit-logs", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 403)

    @patch("services.audit_service.execute_query")
    def test_audit_logs_returns_200(self, mock_eq):
        mock_eq.side_effect = [[{"total": 0}], []]
        resp = self.client.get(
            "/api/v1/audit-logs",
            headers={"Authorization": f"Bearer {_token(can_view_audit=True)}"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("logs", body)
        self.assertIn("total", body)

    def test_audit_logs_rejects_non_integer_user_id(self):
        resp = self.client.get(
            "/api/v1/audit-logs?user_id=abc",
            headers={"Authorization": f"Bearer {_token(can_view_audit=True)}"},
        )
        self.assertEqual(resp.status_code, 400)

    @patch("services.audit_service.execute_query")
    def test_audit_log_single_404(self, mock_eq):
        mock_eq.return_value = []
        resp = self.client.get(
            "/api/v1/audit-logs/99999",
            headers={"Authorization": f"Bearer {_token(can_view_audit=True)}"},
        )
        self.assertEqual(resp.status_code, 404)

    @patch("services.audit_service.execute_query")
    def test_audit_log_single_200(self, mock_eq):
        mock_eq.return_value = [{"id": 1, "action": "LOGIN", "entity_type": "session", "entity_id": "admin"}]
        resp = self.client.get(
            "/api/v1/audit-logs/1",
            headers={"Authorization": f"Bearer {_token(can_view_audit=True)}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["action"], "LOGIN")

    # ------------------------------------------------------------------
    # POST /internal/v1/events
    # ------------------------------------------------------------------

    def test_ingest_without_internal_token_is_403(self):
        resp = self.client.post("/internal/v1/events", json={"action": "X", "entity_type": "y"})
        self.assertEqual(resp.status_code, 403)

    def test_ingest_rejects_user_jwt_in_place_of_internal_token(self):
        """A logged-in user must not be able to forge audit entries."""
        resp = self.client.post(
            "/internal/v1/events",
            json={"action": "X", "entity_type": "y"},
            headers={"Authorization": f"Bearer {_token(can_view_audit=True, can_manage_users=True)}"},
        )
        self.assertEqual(resp.status_code, 403)

    @patch("services.audit_service.execute_query")
    def test_ingest_persists_event(self, mock_eq):
        mock_eq.return_value = [{"id": 55}]
        resp = self.client.post(
            "/internal/v1/events",
            json={"action": "CREATE", "entity_type": "report", "entity_id": "3", "user_id": 1,
                  "username": "admin", "after": {"id": 3}, "source": "catalog"},
            headers=self.internal,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["id"], 55)
        params = mock_eq.call_args[0][1]
        self.assertEqual(params["entity_type"], "report")
        self.assertEqual(params["username"], "admin")

    @patch("services.audit_service.execute_query")
    def test_ingest_invalid_event_is_400(self, mock_eq):
        resp = self.client.post("/internal/v1/events", json={"entity_type": "x"}, headers=self.internal)
        self.assertEqual(resp.status_code, 400)
        mock_eq.assert_not_called()

    @patch("services.audit_service.execute_query", side_effect=Exception("DB is down"))
    def test_ingest_db_failure_is_500_so_client_retries(self, _mock_eq):
        resp = self.client.post(
            "/internal/v1/events",
            json={"action": "CREATE", "entity_type": "report"},
            headers=self.internal,
        )
        self.assertEqual(resp.status_code, 500)


if __name__ == "__main__":
    unittest.main()
