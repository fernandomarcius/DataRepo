"""
User management emits audit events.

Before the split these tests asserted the INSERT INTO audit_log that app.py ran
inline. identity no longer owns audit_log: it hands the event to the audit
service (kit/audit_client.py). What these tests guard is the same thing — the
create/update/delete cycle produces the right event, with before/after state —
checked at the boundary where the event leaves this service.
All DB interactions are mocked — no real Postgres needed.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")
os.environ.setdefault("ADMIN_USERNAME", "")
os.environ.setdefault("ADMIN_PASSWORD", "")

_mock_engine = MagicMock()
_mock_execute_query = MagicMock(return_value=[])

sys.modules.setdefault(
    "db",
    MagicMock(engine=_mock_engine, execute_query=_mock_execute_query),
)

from werkzeug.security import generate_password_hash  # noqa: E402 -- import depois do setup de sys.modules acima
from services.auth_service import (  # noqa: E402 -- import depois do setup de sys.modules acima
    PERMISSION_FLAGS,
    issue_token,
)


def _make_user(uid=1, username="admin", **perm_overrides):
    perms = {flag: perm_overrides.get(flag, False) for flag in PERMISSION_FLAGS}
    return {"id": uid, "username": username, "perms": perms}


def _user_row(uid=1, username="admin", password="pw", **perm_overrides):
    # Use pbkdf2 explicitly — scrypt is unavailable on Python 3.9/macOS stock
    row = {
        "id": uid,
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "created_at": None,
        "can_view_audit": True,
    }
    for flag in PERMISSION_FLAGS:
        row[flag] = perm_overrides.get(flag, True)
    return row


def _admin_token():
    return issue_token(_make_user(uid=1, username="admin", can_manage_users=True, can_view_audit=True))


class TestUserAuditEvents(unittest.TestCase):

    def setUp(self):
        self._engine_patcher = patch("db.engine", _mock_engine)
        self._eq_patcher = patch("db.execute_query", _mock_execute_query)
        self._engine_patcher.start()
        self._eq_patcher.start()

        from app import app  # noqa: PLC0415 -- import tardio para usar os mocks ja instalados
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.auth_header = {"Authorization": f"Bearer {_admin_token()}"}

    def tearDown(self):
        self._engine_patcher.stop()
        self._eq_patcher.stop()

    def _events(self, action):
        return [e for e in self.audit_events if e["action"] == action]

    @patch("services.auth_service.execute_query")
    def test_create_user_logs_audit_event(self, mock_auth_eq):
        mock_auth_eq.return_value = [_user_row(uid=99, username="newuser")]

        resp = self.client.post(
            "/api/v1/users",
            json={"username": "newuser", "password": "pw123"},
            headers=self.auth_header,
        )
        self.assertEqual(resp.status_code, 201)

        events = self._events("CREATE")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["entity_type"], "user")
        self.assertEqual(events[0]["entity_id"], "99")
        # The acting admin comes from the JWT, captured on the request thread.
        self.assertEqual(events[0]["user_id"], 1)
        self.assertEqual(events[0]["username"], "admin")

    @patch("services.auth_service.execute_query")
    def test_update_user_logs_audit_event(self, mock_auth_eq):
        existing = _user_row(uid=5, username="alice")
        updated = _user_row(uid=5, username="alice_updated")
        mock_auth_eq.side_effect = [
            [existing],   # first get_user_by_id (target check)
            [existing],   # second get_user_by_id (before capture)
            [updated],    # update_user RETURNING
        ]

        resp = self.client.put(
            "/api/v1/users/5",
            json={"username": "alice_updated"},
            headers=self.auth_header,
        )
        self.assertEqual(resp.status_code, 200)

        events = self._events("UPDATE")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["entity_type"], "user")
        self.assertEqual(events[0]["entity_id"], "5")
        self.assertEqual(events[0]["before"]["username"], "alice")
        self.assertEqual(events[0]["after"]["username"], "alice_updated")

    @patch("routes.identity.create_user", side_effect=Exception("duplicate key value violates unique constraint"))
    def test_failed_create_user_logs_failed_audit_entry(self, _mock_create):
        resp = self.client.post(
            "/api/v1/users",
            json={"username": "dupe", "password": "pw"},
            headers=self.auth_header,
        )
        self.assertEqual(resp.status_code, 409)

        events = self._events("CREATE")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "failed")
        self.assertEqual(events[0]["entity_type"], "user")
        self.assertIn("duplicate", events[0]["error"])

    @patch("services.auth_service.execute_query")
    def test_delete_user_logs_audit_event(self, mock_auth_eq):
        existing = _user_row(uid=7, username="bob", can_manage_users=False)
        mock_auth_eq.side_effect = [
            [existing],   # target check
            [existing],   # before capture
            [{"id": 7}],  # delete_user RETURNING
        ]

        resp = self.client.delete("/api/v1/users/7", headers=self.auth_header)
        self.assertEqual(resp.status_code, 200)

        events = self._events("DELETE")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["entity_id"], "7")
        self.assertEqual(events[0]["before"]["username"], "bob")

    @patch("services.auth_service.execute_query")
    def test_failed_login_is_audited_without_password(self, mock_auth_eq):
        mock_auth_eq.return_value = []
        resp = self.client.post("/api/v1/auth/login", json={"username": "x", "password": "secret-pw"})
        self.assertEqual(resp.status_code, 401)

        events = self._events("LOGIN")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "failed")
        self.assertNotIn("secret-pw", repr(events[0]))


if __name__ == "__main__":
    unittest.main()
