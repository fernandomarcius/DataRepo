"""Password reset / change password tests — mocked DB and SMTP, no real services."""
import hashlib
import os
import smtplib
import sys
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Environment must be set BEFORE any project module is imported.
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")
os.environ.setdefault("ADMIN_USERNAME", "")
os.environ.setdefault("ADMIN_PASSWORD", "")
os.environ.setdefault("SMTP_SERVER", "smtp.test.local")
os.environ.setdefault("SMTP_USER", "naoresponder@test.local")
os.environ.setdefault("SMTP_PASSWORD", "smtp-test-password")

_mock_engine = MagicMock()
_mock_execute_query = MagicMock(return_value=[])

sys.modules.setdefault("db", MagicMock(engine=_mock_engine, execute_query=_mock_execute_query))

from services.auth_service import validate_new_password  # noqa: E402 -- import depois do setup de sys.modules acima
from services.email_service import EmailSendError, send_email  # noqa: E402 -- idem, precisa do shim de db
from services.password_reset_service import (  # noqa: E402 -- idem, precisa do shim de db
    _hash_token,
    consume_reset_token,
    create_reset_token,
    looks_like_email,
    reset_password,
)


# ===========================================================================
# Service-level unit tests
# ===========================================================================


class TestTokenHelpers(unittest.TestCase):
    def test_looks_like_email_accepts_addresses(self):
        for value in ("a@b.co", "fulano.silva@example.com", "x_y+z@sub.dominio.org"):
            self.assertTrue(looks_like_email(value), value)

    def test_looks_like_email_rejects_non_addresses(self):
        for value in ("admin", "a@b", "a b@c.com", "", None, "@b.co", "a@ b.co"):
            self.assertFalse(looks_like_email(value), value)

    def test_hash_token_is_deterministic_sha256_hex(self):
        digest = _hash_token("some-token")
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, hashlib.sha256(b"some-token").hexdigest())
        self.assertEqual(digest, _hash_token("some-token"))
        self.assertNotEqual(digest, _hash_token("other-token"))

    def test_validate_new_password_bounds(self):
        with self.assertRaises(ValueError):
            validate_new_password("1234567")
        with self.assertRaises(ValueError):
            validate_new_password("x" * 129)
        validate_new_password("12345678")  # must not raise


def _identity_text(sql):
    """Stand-in for sqlalchemy.text so assertions can read the raw SQL string."""
    return sql


class TestCreateResetToken(unittest.TestCase):
    @patch("services.password_reset_service.text", _identity_text)
    @patch("services.password_reset_service.engine")
    def test_invalidates_previous_then_inserts_hash(self, mock_engine):
        conn = mock_engine.connect.return_value.__enter__.return_value

        token = create_reset_token(7, "10.0.0.1")

        self.assertGreaterEqual(len(token), 40)
        self.assertEqual(conn.execute.call_count, 2)

        first_sql = str(conn.execute.call_args_list[0].args[0])
        second_sql = str(conn.execute.call_args_list[1].args[0])
        self.assertIn("UPDATE _system_password_resets", first_sql)
        self.assertIn("used_at IS NULL", first_sql)
        self.assertIn("INSERT INTO _system_password_resets", second_sql)
        self.assertIn("make_interval", second_sql)

        params = conn.execute.call_args_list[1].args[1]
        self.assertEqual(params["th"], _hash_token(token))
        self.assertEqual(params["uid"], 7)
        self.assertEqual(params["ip"], "10.0.0.1")
        conn.commit.assert_called_once()

    @patch("services.password_reset_service.text", _identity_text)
    @patch("services.password_reset_service.engine")
    def test_token_is_not_stored_in_clear(self, mock_engine):
        conn = mock_engine.connect.return_value.__enter__.return_value
        token = create_reset_token(1, None)
        for call in conn.execute.call_args_list:
            self.assertNotIn(token, str(call.args))


class TestConsumeResetToken(unittest.TestCase):
    @patch("services.password_reset_service.execute_query")
    def test_valid_token_returns_user_id(self, mock_eq):
        mock_eq.return_value = [{"user_id": 7}]
        self.assertEqual(consume_reset_token("a" * 43), 7)

        sql = mock_eq.call_args.args[0]
        self.assertIn("used_at IS NULL", sql)
        self.assertIn("expires_at > now()", sql)
        self.assertIn("RETURNING user_id", sql)

    @patch("services.password_reset_service.execute_query")
    def test_unknown_or_expired_token_returns_none(self, mock_eq):
        mock_eq.return_value = []
        self.assertIsNone(consume_reset_token("a" * 43))

    @patch("services.password_reset_service.execute_query")
    def test_malformed_token_never_touches_db(self, mock_eq):
        for value in (None, "", "short", "has spaces here", "tok!@#$"):
            self.assertIsNone(consume_reset_token(value))
        mock_eq.assert_not_called()


class TestResetPasswordService(unittest.TestCase):
    @patch("services.password_reset_service.update_user")
    @patch("services.password_reset_service.consume_reset_token")
    def test_short_password_rejected_before_burning_token(self, mock_consume, mock_update):
        with self.assertRaises(ValueError):
            reset_password("a" * 43, "short")
        mock_consume.assert_not_called()
        mock_update.assert_not_called()

    @patch("services.password_reset_service.update_user")
    @patch("services.password_reset_service.consume_reset_token", return_value=None)
    def test_invalid_token_does_not_update_password(self, _mock_consume, mock_update):
        self.assertIsNone(reset_password("a" * 43, "newpassword123"))
        mock_update.assert_not_called()

    @patch("services.password_reset_service.update_user")
    @patch("services.password_reset_service.consume_reset_token", return_value=7)
    def test_success_updates_password_and_returns_user_id(self, _mock_consume, mock_update):
        self.assertEqual(reset_password("a" * 43, "newpassword123"), 7)
        mock_update.assert_called_once_with(7, password="newpassword123")


class TestSendEmail(unittest.TestCase):
    @patch("services.email_service.smtplib.SMTP")
    def test_uses_starttls_and_authenticates(self, mock_smtp):
        smtp = mock_smtp.return_value.__enter__.return_value

        send_email("alvo@test.local", "Assunto", "corpo", "<p>corpo</p>")

        self.assertEqual(mock_smtp.call_args.args[0], "smtp.test.local")
        self.assertEqual(mock_smtp.call_args.args[1], 587)
        self.assertIsNotNone(smtp.starttls.call_args.kwargs.get("context"))
        smtp.login.assert_called_once_with("naoresponder@test.local", "smtp-test-password")

        msg = smtp.send_message.call_args.args[0]
        self.assertEqual(msg["To"], "alvo@test.local")
        self.assertEqual(msg["Subject"], "Assunto")
        self.assertEqual(msg["From"], "naoresponder@test.local")

    @patch("services.email_service.smtplib.SMTP")
    def test_missing_credentials_raise_runtime_error(self, _mock_smtp):
        with patch.dict(os.environ, {"SMTP_PASSWORD": ""}):
            with self.assertRaises(RuntimeError):
                send_email("alvo@test.local", "Assunto", "corpo")

    @patch("services.email_service.smtplib.SMTP")
    def test_smtp_failure_is_wrapped(self, mock_smtp):
        mock_smtp.side_effect = smtplib.SMTPAuthenticationError(535, b"denied")
        with self.assertRaises(EmailSendError):
            send_email("alvo@test.local", "Assunto", "corpo")


# ===========================================================================
# Route tests
# ===========================================================================


class TestPasswordRoutes(unittest.TestCase):
    def setUp(self):
        self._engine_patcher = patch("db.engine", _mock_engine)
        self._eq_patcher = patch("db.execute_query", _mock_execute_query)
        self._engine_patcher.start()
        self._eq_patcher.start()

        from app import app, limiter  # noqa: PLC0415 -- import tardio para usar os mocks ja instalados
        app.config["TESTING"] = True
        # O limiter guarda contadores em memoria durante todo o processo de teste;
        # sem zerar, os casos de forgot-password estouram o limite de 5/min entre si.
        limiter.reset()
        self.app = app
        self.client = app.test_client()

    def tearDown(self):
        self._engine_patcher.stop()
        self._eq_patcher.stop()

    def _token_for(self, uid=7, username="user@test.local"):
        from services.auth_service import (  # noqa: PLC0415 -- import tardio, usa os mocks ja instalados
            PERMISSION_FLAGS,
            issue_token,
        )
        return issue_token({
            "id": uid,
            "username": username,
            "perms": {flag: False for flag in PERMISSION_FLAGS},
        })

    # ------------------------------------------------------------------
    # /auth/forgot-password
    # ------------------------------------------------------------------

    def test_forgot_missing_username(self):
        resp = self.client.post("/api/v1/auth/forgot-password", json={})
        self.assertEqual(resp.status_code, 400)

    @patch("routes.identity._send_reset_email_async")
    @patch("routes.identity.get_user_by_username", return_value=None)
    def test_forgot_unknown_user_is_generic_and_sends_nothing(self, _mock_get, mock_send):
        resp = self.client.post(
            "/api/v1/auth/forgot-password", json={"username": "ninguem@test.local"}
        )
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_not_called()

    @patch("routes.identity._send_reset_email_async")
    @patch("routes.identity.get_user_by_username")
    def test_forgot_non_email_username_never_queries_user(self, mock_get, mock_send):
        resp = self.client.post("/api/v1/auth/forgot-password", json={"username": "admin"})
        self.assertEqual(resp.status_code, 200)
        mock_get.assert_not_called()
        mock_send.assert_not_called()

    @patch("routes.identity._send_reset_email_async")
    @patch("routes.identity.create_reset_token", return_value="tok123")
    @patch("routes.identity.get_user_by_username", return_value={"id": 7, "username": "user@test.local"})
    def test_forgot_known_user_sends_link(self, _mock_get, _mock_token, mock_send):
        resp = self.client.post(
            "/api/v1/auth/forgot-password", json={"username": "user@test.local"}
        )
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_once()
        link = mock_send.call_args.args[1]
        self.assertTrue(link.endswith("/reset-password/tok123"), link)

    @patch("routes.identity._send_reset_email_async")
    @patch("routes.identity.create_reset_token", return_value="tok123")
    @patch("routes.identity.get_user_by_username")
    def test_forgot_response_body_identical_in_every_case(self, mock_get, _mock_token, _mock_send):
        mock_get.return_value = {"id": 7, "username": "user@test.local"}
        known = self.client.post(
            "/api/v1/auth/forgot-password", json={"username": "user@test.local"}
        ).get_json()

        mock_get.return_value = None
        unknown = self.client.post(
            "/api/v1/auth/forgot-password", json={"username": "ninguem@test.local"}
        ).get_json()

        not_email = self.client.post(
            "/api/v1/auth/forgot-password", json={"username": "admin"}
        ).get_json()

        self.assertEqual(known, unknown)
        self.assertEqual(known, not_email)

    @patch("routes.identity._send_reset_email_async")
    @patch("routes.identity.create_reset_token", return_value="tok123")
    @patch("routes.identity.get_user_by_username", return_value={"id": 7, "username": "user@test.local"})
    def test_forgot_link_prefers_app_base_url(self, _mock_get, _mock_token, mock_send):
        with patch.dict(os.environ, {"APP_BASE_URL": "https://data.example/"}):
            self.client.post("/api/v1/auth/forgot-password", json={"username": "user@test.local"})
        self.assertEqual(mock_send.call_args.args[1], "https://data.example/reset-password/tok123")

    @patch("routes.identity._send_reset_email_async")
    @patch("routes.identity.create_reset_token", return_value="tok123")
    @patch("routes.identity.get_user_by_username", return_value={"id": 7, "username": "user@test.local"})
    def test_forgot_link_honours_forwarded_proto(self, _mock_get, _mock_token, mock_send):
        with patch.dict(os.environ, {"APP_BASE_URL": ""}):
            self.client.post(
                "/api/v1/auth/forgot-password",
                json={"username": "user@test.local"},
                headers={"X-Forwarded-Proto": "https"},
            )
        self.assertTrue(mock_send.call_args.args[1].startswith("https://"))

    # ------------------------------------------------------------------
    # /auth/reset-password
    # ------------------------------------------------------------------

    def test_reset_missing_fields(self):
        resp = self.client.post("/api/v1/auth/reset-password", json={"token": "abc"})
        self.assertEqual(resp.status_code, 400)

    @patch("routes.identity.reset_password", return_value=None)
    def test_reset_invalid_token_returns_400_not_401(self, _mock_reset):
        resp = self.client.post(
            "/api/v1/auth/reset-password", json={"token": "a" * 43, "password": "newpassword123"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"], "Invalid or expired token")

    @patch("routes.identity.reset_password", side_effect=ValueError("Password must be at least 8 characters"))
    def test_reset_short_password(self, _mock_reset):
        resp = self.client.post(
            "/api/v1/auth/reset-password", json={"token": "a" * 43, "password": "short"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("at least 8", resp.get_json()["error"])

    @patch("routes.identity.log_event")
    @patch("routes.identity.get_user_by_id", return_value={"id": 7, "username": "user@test.local", "perms": {}})
    @patch("routes.identity.reset_password", return_value=7)
    def test_reset_success_logs_event(self, _mock_reset, _mock_get, mock_log):
        resp = self.client.post(
            "/api/v1/auth/reset-password", json={"token": "a" * 43, "password": "newpassword123"}
        )
        self.assertEqual(resp.status_code, 200)
        mock_log.assert_called_with(
            "PASSWORD_RESET", "user", "7", status="success", metadata={"ip": "127.0.0.1"}
        )

    # ------------------------------------------------------------------
    # /auth/change-password
    # ------------------------------------------------------------------

    def test_change_requires_authentication(self):
        resp = self.client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "old", "new_password": "newpassword123"},
        )
        self.assertEqual(resp.status_code, 401)

    @patch("routes.identity.update_user")
    @patch("routes.identity.authenticate", return_value=None)
    def test_change_wrong_current_password(self, _mock_auth, mock_update):
        resp = self.client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "wrong", "new_password": "newpassword123"},
            headers={"Authorization": f"Bearer {self._token_for()}"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"], "Current password is incorrect")
        mock_update.assert_not_called()

    @patch("routes.identity.update_user")
    @patch("routes.identity.authenticate", return_value=None)
    def test_change_short_new_password_rejected_before_auth(self, mock_auth, mock_update):
        resp = self.client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "old", "new_password": "short"},
            headers={"Authorization": f"Bearer {self._token_for()}"},
        )
        self.assertEqual(resp.status_code, 400)
        mock_auth.assert_not_called()
        mock_update.assert_not_called()

    @patch("routes.identity.update_user")
    @patch("routes.identity.authenticate", return_value={"id": 7, "username": "user@test.local", "perms": {}})
    def test_change_success_uses_token_identity_not_body(self, mock_auth, mock_update):
        resp = self.client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "oldpassword",
                "new_password": "newpassword123",
                "username": "outro@test.local",
            },
            headers={"Authorization": f"Bearer {self._token_for(uid=7, username='user@test.local')}"},
        )
        self.assertEqual(resp.status_code, 200)
        mock_auth.assert_called_once_with("user@test.local", "oldpassword")
        mock_update.assert_called_once_with(7, password="newpassword123")


if __name__ == "__main__":
    unittest.main()
