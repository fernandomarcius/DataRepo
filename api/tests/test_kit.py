"""Testes do kit de plataforma (vendorizado junto com o kit — nao edite aqui)."""
import json
import os
import time
import unittest
from unittest.mock import MagicMock, patch

import jwt
from flask import g, jsonify

from kit import audit_client, internal
from kit.auth import (
    PERMISSION_FLAGS,
    decode_token,
    login_required,
    normalize_perms,
    require_permission,
)
from kit.identifiers import quote_identifier, validate_data_object_name
from kit.sql_guard import ReadOnlySQLError, mask_sql_literals, validate_readonly_sql
from kit.web import create_app, init_step


def _token(uid=1, username="alice", exp_offset=3600, **perms):
    now = int(time.time())
    payload = {
        "sub": str(uid),
        "username": username,
        "perms": {flag: perms.get(flag, False) for flag in PERMISSION_FLAGS},
        "iat": now,
        "exp": now + exp_offset,
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")


def _app():
    app = create_app("kit_test")

    @app.route("/open")
    @login_required
    def open_route():
        return jsonify(g.current_user), 200

    @app.route("/admin")
    @require_permission("can_manage_users")
    def admin_route():
        return jsonify({"ok": True}), 200

    @app.route("/internal/ping", methods=["POST"])
    @internal.internal_only
    def internal_route():
        return jsonify({"ok": True}), 200

    return app


class TestAuthDecorators(unittest.TestCase):
    def setUp(self):
        self.client = _app().test_client()

    def test_missing_token_is_401(self):
        self.assertEqual(self.client.get("/open").status_code, 401)

    def test_garbage_token_is_401(self):
        resp = self.client.get("/open", headers={"Authorization": "Bearer not.a.jwt"})
        self.assertEqual(resp.status_code, 401)

    def test_expired_token_is_401(self):
        resp = self.client.get("/open", headers={"Authorization": f"Bearer {_token(exp_offset=-10)}"})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json()["error"], "Token expired")

    def test_valid_token_populates_current_user(self):
        token = _token(uid=7, can_query=True)
        resp = self.client.get("/open", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["id"], 7)
        self.assertTrue(body["perms"]["can_query"])
        self.assertEqual(set(body["perms"]), set(PERMISSION_FLAGS))

    def test_missing_permission_is_403(self):
        resp = self.client.get("/admin", headers={"Authorization": f"Bearer {_token()}"})
        self.assertEqual(resp.status_code, 403)

    def test_present_permission_is_200(self):
        token = _token(can_manage_users=True)
        resp = self.client.get("/admin", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 200)

    def test_unknown_permission_flag_fails_at_import(self):
        with self.assertRaises(ValueError):
            require_permission("can_fly")

    def test_decode_rejects_other_secret(self):
        payload = {"sub": "1", "exp": int(time.time()) + 60}
        forged = jwt.encode(payload, "another-secret-that-is-at-least-32-bytes", algorithm="HS256")
        with self.assertRaises(jwt.InvalidTokenError):
            decode_token(forged)

    def test_normalize_perms_drops_unknown_flags(self):
        self.assertNotIn("can_fly", normalize_perms({"can_fly": True}))

    def test_healthz(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ok")

    def test_proxy_fix_uses_forwarded_client_ip(self):
        app = _app()

        @app.route("/ip")
        def ip_route():
            from flask import request
            return jsonify({"ip": request.remote_addr})

        resp = app.test_client().get("/ip", headers={"X-Forwarded-For": "10.1.2.3"})
        self.assertEqual(resp.get_json()["ip"], "10.1.2.3")


class TestInitStep(unittest.TestCase):
    def test_retries_then_succeeds(self):
        fn = MagicMock(side_effect=[Exception("pg_type_typname_nsp_index"), None])
        self.assertTrue(init_step("x", fn, delay_seconds=0))
        self.assertEqual(fn.call_count, 2)

    def test_gives_up_without_raising(self):
        fn = MagicMock(side_effect=Exception("db down"))
        self.assertFalse(init_step("x", fn, attempts=2, delay_seconds=0))
        self.assertEqual(fn.call_count, 2)


class TestInternalOnly(unittest.TestCase):
    def setUp(self):
        self.client = _app().test_client()

    def test_without_token_is_403(self):
        self.assertEqual(self.client.post("/internal/ping").status_code, 403)

    def test_wrong_token_is_403(self):
        resp = self.client.post("/internal/ping", headers={internal.INTERNAL_TOKEN_HEADER: "nope"})
        self.assertEqual(resp.status_code, 403)

    def test_right_token_is_200(self):
        resp = self.client.post(
            "/internal/ping",
            headers={internal.INTERNAL_TOKEN_HEADER: os.environ["INTERNAL_API_TOKEN"]},
        )
        self.assertEqual(resp.status_code, 200)

    def test_unconfigured_token_closes_endpoint(self):
        with patch.dict(os.environ, {"INTERNAL_API_TOKEN": ""}):
            resp = self.client.post("/internal/ping", headers={internal.INTERNAL_TOKEN_HEADER: ""})
        self.assertEqual(resp.status_code, 403)


class TestSqlGuard(unittest.TestCase):
    def test_select_allowed(self):
        self.assertEqual(validate_readonly_sql("SELECT 1;"), "SELECT 1")

    def test_with_allowed(self):
        self.assertTrue(validate_readonly_sql("WITH x AS (SELECT 1) SELECT * FROM x"))

    def test_ddl_rejected(self):
        for sql in ("DROP TABLE x", "SELECT 1; DELETE FROM x", "select * from x where 1=1 or delete"):
            with self.assertRaises(ReadOnlySQLError, msg=sql):
                validate_readonly_sql(sql)

    def test_keywords_inside_literals_are_ignored(self):
        self.assertTrue(validate_readonly_sql("SELECT 'drop table' AS t, \"update\" FROM x"))

    def test_mask_keeps_length(self):
        sql = "SELECT 'a;b' -- c\n FROM t /* d */"
        self.assertEqual(len(mask_sql_literals(sql)), len(sql))

    def test_empty_rejected(self):
        with self.assertRaises(ReadOnlySQLError):
            validate_readonly_sql("   ")


class TestIdentifiers(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(quote_identifier("vendas_2026"), '"vendas_2026"')

    def test_invalid(self):
        for name in ("", "Vendas", "1x", "a-b", 'x"; drop', "_system_users", "reports", "audit_log"):
            with self.assertRaises(ValueError, msg=name):
                validate_data_object_name(name)


class TestAuditClient(unittest.TestCase):
    def test_event_carries_user_request_meta_and_is_redacted(self):
        app = _app()
        with app.test_request_context("/x", headers={"User-Agent": "UA", "X-Forwarded-For": "10.9.9.9"}):
            g.current_user = {"id": 3, "username": "bob"}
            event = audit_client.build_event(
                "UPDATE", "user", 3,
                before={"username": "a", "password": "p"},
                after={"nested": [{"token": "t"}]},
                metadata={"k": "v"},
            )
        self.assertEqual(event["user_id"], 3)
        self.assertEqual(event["username"], "bob")
        self.assertEqual(event["entity_id"], "3")
        self.assertEqual(event["before"]["password"], "[REDACTED]")
        self.assertEqual(event["after"]["nested"][0]["token"], "[REDACTED]")
        self.assertEqual(event["metadata"]["user_agent"], "UA")
        self.assertEqual(event["metadata"]["k"], "v")
        json.dumps(event)  # precisa atravessar a rede

    def test_event_outside_request_context(self):
        event = audit_client.build_event("LOGIN", "session", "x", status="failed", error="boom")
        self.assertIsNone(event["user_id"])
        self.assertEqual(event["status"], "failed")
        self.assertIsNone(event["metadata"])

    def test_log_event_never_raises(self):
        with patch.object(audit_client, "build_event", side_effect=Exception("boom")):
            audit_client.log_event("CREATE", "report", "1")  # nao levanta

    def test_log_event_enqueues(self):
        captured = []
        with patch.object(audit_client._dispatcher, "submit", captured.append):
            audit_client.log_event("CREATE", "report", "1", after={"id": 1})
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["action"], "CREATE")

    def test_send_event_posts_to_internal_endpoint(self):
        with patch.object(audit_client, "call_json", MagicMock(return_value={"id": 1})) as call:
            audit_client.send_event({"action": "X"})
        method, url, payload = call.call_args[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/internal/v1/events"))
        self.assertEqual(payload, {"action": "X"})

    def test_send_event_failure_goes_to_stderr_not_exception(self):
        err = internal.InternalCallError("down")
        with patch.object(audit_client, "call_json", side_effect=err), \
                patch.object(audit_client.time, "sleep"), \
                patch.object(audit_client, "_undelivered") as undelivered:
            audit_client.send_event({"action": "X"})
        undelivered.assert_called_once()


if __name__ == "__main__":
    unittest.main()
