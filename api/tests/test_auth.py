"""identity: auth service and auth routes — mocked DB, no real Postgres needed."""
import os
import sys
import time
import unittest
from typing import Optional
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Environment must be set BEFORE any project module is imported.
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")
os.environ.setdefault("ADMIN_USERNAME", "")
os.environ.setdefault("ADMIN_PASSWORD", "")

# ---------------------------------------------------------------------------
# Stub out db.engine so app-level init (init_users_table / seed_admin_user)
# doesn't attempt a real Postgres connection when app.py is imported.
# ---------------------------------------------------------------------------
_mock_engine = MagicMock()
_mock_execute_query = MagicMock(return_value=[])

# Patch at the db module level before any project import touches it.
sys.modules.setdefault("db", MagicMock(engine=_mock_engine, execute_query=_mock_execute_query))

import jwt  # noqa: E402 -- import depois do setup de sys.modules acima

from services.auth_service import (  # noqa: E402 -- import depois do setup de sys.modules acima
    PERMISSION_FLAGS,
    _normalize_perms,
    authenticate,
    decode_token,
    generate_password_hash,
    issue_token,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    uid: int = 1,
    username: str = "testuser",
    perms: Optional[dict] = None,
):
    if perms is None:
        perms = {flag: False for flag in PERMISSION_FLAGS}
    return {"id": uid, "username": username, "perms": perms}


def _user_row(
    uid: int = 1,
    username: str = "testuser",
    password: str = "testpass",
    **perm_overrides,
):
    """Return a dict that mimics a _system_users DB row."""
    row = {
        "id": uid,
        "username": username,
        "password_hash": generate_password_hash(password),
        "created_at": None,
    }
    for flag in PERMISSION_FLAGS:
        row[flag] = perm_overrides.get(flag, False)
    return row


# ===========================================================================
# TestNormalizePerms
# ===========================================================================

class TestNormalizePerms(unittest.TestCase):

    def test_empty_dict(self):
        result = _normalize_perms({})
        for flag in PERMISSION_FLAGS:
            self.assertFalse(result[flag], f"{flag} should be False")
        self.assertEqual(set(result.keys()), set(PERMISSION_FLAGS))

    def test_partial(self):
        result = _normalize_perms({"can_query": True})
        self.assertTrue(result["can_query"])
        for flag in PERMISSION_FLAGS:
            if flag != "can_query":
                self.assertFalse(result[flag], f"{flag} should be False")

    def test_unknown_keys_ignored(self):
        # Should not raise; unknown key is simply dropped.
        result = _normalize_perms({"can_query": True, "can_fly": True})
        self.assertNotIn("can_fly", result)
        self.assertTrue(result["can_query"])

    def test_none_input(self):
        result = _normalize_perms(None)
        for flag in PERMISSION_FLAGS:
            self.assertFalse(result[flag])

    def test_all_flags_true(self):
        result = _normalize_perms({flag: True for flag in PERMISSION_FLAGS})
        for flag in PERMISSION_FLAGS:
            self.assertTrue(result[flag])

    def test_falsy_values_coerced(self):
        # 0, "", None should all coerce to False
        result = _normalize_perms({flag: 0 for flag in PERMISSION_FLAGS})
        for flag in PERMISSION_FLAGS:
            self.assertFalse(result[flag])


# ===========================================================================
# TestIssueAndDecodeToken
# ===========================================================================

class TestIssueAndDecodeToken(unittest.TestCase):

    def _sample_user(self):
        return _make_user(uid=42, username="alice")

    def test_round_trip(self):
        user = self._sample_user()
        token = issue_token(user)
        payload = decode_token(token)
        self.assertEqual(payload["sub"], "42")
        self.assertEqual(payload["username"], "alice")

    def test_sub_is_string(self):
        """PyJWT v2 compliance: sub must be a string, not an int."""
        token = issue_token(self._sample_user())
        payload = decode_token(token)
        self.assertIsInstance(payload["sub"], str)

    def test_perms_in_payload(self):
        user = _make_user(uid=1, perms={"can_query": True, "can_upload": False,
                                        "can_manage_views": False, "can_manage_users": False})
        token = issue_token(user)
        payload = decode_token(token)
        self.assertIn("perms", payload)
        self.assertTrue(payload["perms"]["can_query"])
        self.assertFalse(payload["perms"]["can_upload"])

    def test_expired_raises(self):
        """A token with a past exp should raise ExpiredSignatureError."""
        import time as _time
        secret = os.environ["JWT_SECRET"]
        past_payload = {
            "sub": "99",
            "username": "ghost",
            "perms": {},
            "iat": int(_time.time()) - 7200,
            "exp": int(_time.time()) - 3600,
        }
        expired_token = jwt.encode(past_payload, secret, algorithm="HS256")
        with self.assertRaises(jwt.ExpiredSignatureError):
            decode_token(expired_token)

    def test_invalid_signature_raises(self):
        token = issue_token(self._sample_user())
        # Tamper with signature
        tampered = token[:-4] + "XXXX"
        with self.assertRaises(jwt.InvalidTokenError):
            decode_token(tampered)

    def test_token_is_string(self):
        token = issue_token(self._sample_user())
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 20)


# ===========================================================================
# TestAuthenticate
# ===========================================================================

class TestAuthenticate(unittest.TestCase):

    @patch("services.auth_service.execute_query")
    def test_wrong_username_returns_none(self, mock_eq):
        mock_eq.return_value = []
        result = authenticate("nobody", "irrelevant")
        self.assertIsNone(result)

    @patch("services.auth_service.execute_query")
    def test_wrong_password_returns_none(self, mock_eq):
        mock_eq.return_value = [_user_row(password="correct")]
        result = authenticate("testuser", "wrong_password")
        self.assertIsNone(result)

    @patch("services.auth_service.execute_query")
    def test_correct_credentials(self, mock_eq):
        mock_eq.return_value = [_user_row(uid=7, username="alice", password="pass123")]
        result = authenticate("alice", "pass123")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 7)
        self.assertEqual(result["username"], "alice")
        self.assertIn("perms", result)

    @patch("services.auth_service.execute_query")
    def test_constant_time_on_missing_user(self, mock_eq):
        """Missing user must still run a bcrypt dummy hash (timing-safe)."""
        mock_eq.return_value = []
        t0 = time.monotonic()
        authenticate("nonexistent_user", "any_password")
        elapsed_ms = (time.monotonic() - t0) * 1000
        self.assertGreater(
            elapsed_ms,
            10,
            "authenticate() for a missing user should spend >10 ms on a dummy "
            "bcrypt check to prevent timing-based user enumeration.",
        )

    @patch("services.auth_service.execute_query")
    def test_returns_perms_dict(self, mock_eq):
        mock_eq.return_value = [_user_row(uid=1, username="u", password="pw",
                                          can_query=True)]
        result = authenticate("u", "pw")
        self.assertIsNotNone(result)
        self.assertTrue(result["perms"]["can_query"])
        self.assertFalse(result["perms"]["can_upload"])

    @patch("services.auth_service.execute_query")
    def test_sql_injection_in_username_handled(self, mock_eq):
        """Parameterised queries mean the mock is called once; result is None."""
        mock_eq.return_value = []
        result = authenticate("' OR '1'='1", "any")
        self.assertIsNone(result)
        mock_eq.assert_called_once()


# ===========================================================================
# TestFlaskRoutes
# ===========================================================================

class TestFlaskRoutes(unittest.TestCase):
    """Flask integration tests using the test client. DB is fully mocked."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _valid_token(cls, uid: int = 1, username: str = "testuser", **perm_overrides):
        user = _make_user(uid=uid, username=username,
                          perms={flag: perm_overrides.get(flag, False) for flag in PERMISSION_FLAGS})
        return issue_token(user)

    # ------------------------------------------------------------------
    # setUp / tearDown
    # ------------------------------------------------------------------

    def setUp(self):
        # Patch engine *before* importing app so init_users_table() doesn't fail.
        self._engine_patcher = patch("db.engine", _mock_engine)
        self._eq_patcher = patch("db.execute_query", _mock_execute_query)
        self._engine_patcher.start()
        self._eq_patcher.start()

        from app import app, limiter  # noqa: PLC0415 -- import tardio para usar os mocks ja instalados
        limiter.reset()
        app.config["TESTING"] = True
        self.app = app
        self.client = app.test_client()

    def tearDown(self):
        self._engine_patcher.stop()
        self._eq_patcher.stop()

    # ------------------------------------------------------------------
    # /api/v1/auth/login
    # ------------------------------------------------------------------

    @patch("services.auth_service.execute_query")
    def test_login_missing_fields(self, _mock_eq):
        resp = self.client.post(
            "/api/v1/auth/login",
            json={},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("services.auth_service.execute_query")
    def test_login_wrong_password(self, mock_eq):
        mock_eq.return_value = [_user_row(password="correct_pass")]
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "wrong_pass"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    @patch("services.auth_service.execute_query")
    def test_login_success(self, mock_eq):
        mock_eq.return_value = [_user_row(uid=1, username="admin", password="secret")]
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "secret"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("token", body)
        self.assertIn("user", body)

    @patch("services.auth_service.execute_query")
    def test_login_missing_username_only(self, _mock_eq):
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"password": "pw"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("services.auth_service.execute_query")
    def test_login_missing_password_only(self, _mock_eq):
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "user"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    # ------------------------------------------------------------------
    # /api/v1/auth/me
    # ------------------------------------------------------------------

    def test_me_no_token(self):
        resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(resp.status_code, 401)

    def test_me_invalid_token(self):
        resp = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer garbage.not.a.jwt"},
        )
        self.assertEqual(resp.status_code, 401)

    @patch("services.auth_service.execute_query")
    def test_me_valid_token(self, mock_eq):
        token = self._valid_token(uid=5, username="charlie")
        # get_user_by_id will call execute_query; return the user row
        mock_eq.return_value = [_user_row(uid=5, username="charlie", password="pw")]
        resp = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["username"], "charlie")

    def test_me_expired_token(self):
        secret = os.environ["JWT_SECRET"]
        import time as _time
        past_payload = {
            "sub": "1",
            "username": "ghost",
            "perms": {flag: False for flag in PERMISSION_FLAGS},
            "iat": int(_time.time()) - 7200,
            "exp": int(_time.time()) - 3600,
        }
        expired_token = jwt.encode(past_payload, secret, algorithm="HS256")
        resp = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        self.assertEqual(resp.status_code, 401)

    # ------------------------------------------------------------------
    # Rate-limit test
    # ------------------------------------------------------------------

    def test_rate_limit_login(self):
        """/auth/login allows 10 requests per minute per client IP; the 11th is 429."""
        headers = {"X-Forwarded-For": "203.0.113.7"}
        codes = [
            self.client.post("/api/v1/auth/login", json={}, headers=headers).status_code
            for _ in range(11)
        ]
        self.assertEqual(codes[:10], [400] * 10)
        self.assertEqual(codes[10], 429)

    def test_rate_limit_is_per_client_ip(self):
        """Behind the nginx, one client exhausting its quota must not lock out another."""
        for _ in range(11):
            self.client.post("/api/v1/auth/login", json={}, headers={"X-Forwarded-For": "203.0.113.8"})
        resp = self.client.post("/api/v1/auth/login", json={}, headers={"X-Forwarded-For": "203.0.113.9"})
        self.assertEqual(resp.status_code, 400)


# ===========================================================================

if __name__ == "__main__":
    unittest.main()
