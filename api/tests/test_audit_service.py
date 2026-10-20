"""Unit tests for audit_service — mocked DB, no real Postgres needed."""
import os
import sys
import json
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Environment must be set BEFORE any project module is imported.
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")
os.environ.setdefault("ADMIN_USERNAME", "")
os.environ.setdefault("ADMIN_PASSWORD", "")

# ---------------------------------------------------------------------------
# Stub db module before importing anything that touches it.
# ---------------------------------------------------------------------------
_mock_engine = MagicMock()
_mock_execute_query = MagicMock(return_value=[])

sys.modules.setdefault(
    "db",
    MagicMock(engine=_mock_engine, execute_query=_mock_execute_query),
)

from services.audit_service import (  # noqa: E402 -- import depois do setup de sys.modules acima
    InvalidAuditEvent,
    TRUNCATE_LIMIT,
    redact,
    record_event,
    get_logs,
    get_log,
)


# ===========================================================================
# TestRedact
# ===========================================================================

class TestRedact(unittest.TestCase):

    def test_redact_strips_sensitive_keys(self):
        obj = {"username": "alice", "password": "s3cr3t", "email": "a@b.com"}
        result = redact(obj)
        self.assertEqual(result["password"], "[REDACTED]")
        self.assertEqual(result["username"], "alice")
        self.assertEqual(result["email"], "a@b.com")

    def test_redact_strips_password_hash(self):
        obj = {"password_hash": "$2b$12$abc", "id": 1}
        result = redact(obj)
        self.assertEqual(result["password_hash"], "[REDACTED]")
        self.assertEqual(result["id"], 1)

    def test_redact_strips_token(self):
        obj = {"token": "eyJhbGciOiJIUzI1NiJ9.xxx", "name": "Bob"}
        result = redact(obj)
        self.assertEqual(result["token"], "[REDACTED]")
        self.assertEqual(result["name"], "Bob")

    def test_redact_strips_secret(self):
        obj = {"secret": "my-api-secret"}
        result = redact(obj)
        self.assertEqual(result["secret"], "[REDACTED]")

    def test_redact_case_insensitive(self):
        obj = {"PASSWORD": "visible", "Token": "visible2"}
        result = redact(obj)
        self.assertEqual(result["PASSWORD"], "[REDACTED]")
        self.assertEqual(result["Token"], "[REDACTED]")

    def test_redact_handles_nested_dicts(self):
        obj = {
            "user": {
                "id": 1,
                "password": "hidden",
                "profile": {"token": "secret-tok", "bio": "hello"},
            }
        }
        result = redact(obj)
        self.assertEqual(result["user"]["password"], "[REDACTED]")
        self.assertEqual(result["user"]["profile"]["token"], "[REDACTED]")
        self.assertEqual(result["user"]["profile"]["bio"], "hello")

    def test_redact_handles_lists(self):
        obj = [
            {"password": "x", "name": "a"},
            {"token": "y", "name": "b"},
            "plain string",
            42,
        ]
        result = redact(obj)
        self.assertEqual(result[0]["password"], "[REDACTED]")
        self.assertEqual(result[0]["name"], "a")
        self.assertEqual(result[1]["token"], "[REDACTED]")
        self.assertEqual(result[2], "plain string")
        self.assertEqual(result[3], 42)

    def test_redact_primitives_unchanged(self):
        self.assertEqual(redact("hello"), "hello")
        self.assertEqual(redact(42), 42)
        self.assertIsNone(redact(None))


# ===========================================================================
# TestRecordEvent — server side of POST /internal/v1/events
# ===========================================================================

def _event(**overrides):
    event = {
        "user_id": 1,
        "username": "admin",
        "action": "CREATE",
        "entity_type": "user",
        "entity_id": "42",
        "before": None,
        "after": {"id": 42, "username": "bob"},
        "metadata": {"ip": "10.0.0.1"},
        "status": "success",
        "error": None,
        "source": "identity",
    }
    event.update(overrides)
    return event


class TestRecordEvent(unittest.TestCase):

    @patch("services.audit_service.execute_query")
    def test_record_event_inserts_record(self, mock_eq):
        mock_eq.return_value = [{"id": 10}]
        new_id = record_event(_event())

        self.assertEqual(new_id, 10)
        mock_eq.assert_called_once()
        sql, params = mock_eq.call_args[0]
        self.assertIn("INSERT INTO audit_log", sql)
        self.assertEqual(params["action"], "CREATE")
        self.assertEqual(params["entity_type"], "user")
        self.assertEqual(params["entity_id"], "42")
        self.assertEqual(params["status"], "success")
        self.assertEqual(params["user_id"], 1)
        self.assertEqual(params["username"], "admin")
        meta = json.loads(params["metadata"])
        self.assertEqual(meta["ip"], "10.0.0.1")
        self.assertEqual(meta["source_service"], "identity")

    @patch("services.audit_service.execute_query")
    def test_record_event_redacts_before_after(self, mock_eq):
        """Defence in depth: a client that forgot to redact still cannot persist secrets."""
        mock_eq.return_value = [{"id": 1}]
        record_event(_event(
            action="UPDATE",
            before={"id": 1, "password_hash": "abc"},
            after={"id": 1, "password_hash": "xyz"},
        ))
        params = mock_eq.call_args[0][1]
        self.assertEqual(json.loads(params["before_state"])["password_hash"], "[REDACTED]")
        self.assertEqual(json.loads(params["after_state"])["password_hash"], "[REDACTED]")

    @patch("services.audit_service.execute_query")
    def test_record_event_records_failed_status(self, mock_eq):
        mock_eq.return_value = [{"id": 1}]
        record_event(_event(entity_id=None, status="failed", error="unique constraint"))
        params = mock_eq.call_args[0][1]
        self.assertEqual(params["status"], "failed")
        self.assertIn("unique", params["error"])
        self.assertIsNone(params["entity_id"])

    @patch("services.audit_service.execute_query")
    def test_record_event_accepts_anonymous_event(self, mock_eq):
        """Events from outside a request (e.g. the reset e-mail thread) carry no user."""
        mock_eq.return_value = [{"id": 1}]
        record_event(_event(user_id=None, username=None, metadata=None, source=None))
        params = mock_eq.call_args[0][1]
        self.assertIsNone(params["user_id"])
        self.assertIsNone(params["username"])
        self.assertIsNone(params["metadata"])

    @patch("services.audit_service.execute_query")
    def test_record_event_truncates_large_payloads(self, mock_eq):
        mock_eq.return_value = [{"id": 1}]
        record_event(_event(after={"blob": "x" * (TRUNCATE_LIMIT + 10)}))
        params = mock_eq.call_args[0][1]
        self.assertTrue(json.loads(params["after_state"])["truncated"])
        self.assertTrue(json.loads(params["metadata"])["after_state_truncated"])

    @patch("services.audit_service.execute_query")
    def test_record_event_rejects_invalid_payloads(self, mock_eq):
        for bad in (None, [], _event(action=""), _event(entity_type=None),
                    _event(metadata="x"), _event(user_id="abc")):
            with self.assertRaises(InvalidAuditEvent, msg=repr(bad)):
                record_event(bad)
        mock_eq.assert_not_called()

    @patch("services.audit_service.execute_query", side_effect=Exception("DB is down"))
    def test_record_event_propagates_db_errors(self, _mock_eq):
        """The client retries on 5xx, so the server must not swallow DB failures."""
        with self.assertRaises(Exception):
            record_event(_event())


# ===========================================================================
# TestGetLogs
# ===========================================================================

class TestGetLogs(unittest.TestCase):

    # Tests patch services.audit_service.execute_query directly — module-level stub unused.

    @patch("services.audit_service.execute_query")
    def test_get_logs_pagination(self, mock_eq):
        count_row = [{"total": 25}]
        logs_rows = [{"id": i, "action": "CREATE"} for i in range(10)]
        mock_eq.side_effect = [count_row, logs_rows]

        result = get_logs({}, page=2, page_size=10)

        self.assertEqual(result["total"], 25)
        self.assertEqual(result["page"], 2)
        self.assertEqual(result["page_size"], 10)
        self.assertEqual(len(result["logs"]), 10)

        # Verify offset is computed correctly (page=2, size=10 → offset=10)
        second_call_params = mock_eq.call_args_list[1][0][1]
        self.assertEqual(second_call_params["offset"], 10)
        self.assertEqual(second_call_params["limit"], 10)

    @patch("services.audit_service.execute_query")
    def test_get_logs_page_size_capped_at_100(self, mock_eq):
        mock_eq.side_effect = [[{"total": 0}], []]
        get_logs({}, page=1, page_size=9999)
        second_call_params = mock_eq.call_args_list[1][0][1]
        self.assertLessEqual(second_call_params["limit"], 100)

    @patch("services.audit_service.execute_query")
    def test_get_logs_filter_entity_type(self, mock_eq):
        mock_eq.side_effect = [[{"total": 1}], [{"id": 1, "entity_type": "user"}]]
        get_logs({"entity_type": "user"})

        # Both COUNT (call 0) and SELECT (call 1) must apply the WHERE clause —
        # `entity_type` alone is in the SELECT column list, so assert the bound clause.
        for c in mock_eq.call_args_list:
            sql = c[0][0]
            params = c[0][1]
            self.assertIn("entity_type = :entity_type", sql)
            self.assertEqual(params.get("entity_type"), "user")

    @patch("services.audit_service.execute_query")
    def test_get_logs_filter_action(self, mock_eq):
        mock_eq.side_effect = [[{"total": 1}], [{"id": 1, "action": "DELETE"}]]
        get_logs({"action": "DELETE"})

        # `action` alone appears in the SELECT column list — assert the WHERE clause.
        for c in mock_eq.call_args_list:
            sql = c[0][0]
            params = c[0][1]
            self.assertIn("action = :action", sql)
            self.assertEqual(params.get("action"), "DELETE")

    @patch("services.audit_service.execute_query")
    def test_get_logs_returns_empty_on_no_results(self, mock_eq):
        mock_eq.side_effect = [[{"total": 0}], []]
        result = get_logs({})
        self.assertEqual(result["logs"], [])
        self.assertEqual(result["total"], 0)

    @patch("services.audit_service.execute_query")
    def test_get_logs_filter_date_range(self, mock_q):
        """`from`/`to` must produce ts >= / ts <= clauses with the right params."""
        mock_q.side_effect = [[{"total": 0}], []]
        get_logs({"from": "2026-01-01", "to": "2026-12-31"}, page=1, page_size=10)

        # Inspect the data query (second call). args[0]=SQL, args[1]=params.
        data_call = mock_q.call_args_list[1]
        sql = data_call[0][0]
        params = data_call[0][1]

        self.assertIn("ts >= :ts_from", sql)
        self.assertIn("ts <= :ts_to", sql)
        self.assertEqual(params.get("ts_from"), "2026-01-01")
        self.assertEqual(params.get("ts_to"), "2026-12-31")

    @patch("services.audit_service.execute_query")
    def test_get_logs_search_q(self, mock_q):
        """`q` must produce ILIKE clauses on both entity_id and username."""
        mock_q.side_effect = [[{"total": 0}], []]
        get_logs({"q": "alice"}, page=1, page_size=10)

        data_call = mock_q.call_args_list[1]
        sql = data_call[0][0]
        params = data_call[0][1]

        self.assertIn("entity_id ILIKE :q", sql)
        self.assertIn("username ILIKE :q", sql)
        # The q param must be wildcarded for substring matching.
        self.assertEqual(params.get("q"), "%alice%")


# ===========================================================================
# TestGetLog
# ===========================================================================

class TestGetLog(unittest.TestCase):

    @patch("services.audit_service.execute_query")
    def test_get_log_returns_entry(self, mock_eq):
        mock_eq.return_value = [{"id": 5, "action": "LOGIN", "entity_type": "session"}]
        result = get_log(5)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 5)

    @patch("services.audit_service.execute_query")
    def test_get_log_returns_none_when_not_found(self, mock_eq):
        mock_eq.return_value = []
        result = get_log(9999)
        self.assertIsNone(result)


# ===========================================================================

if __name__ == "__main__":
    unittest.main()
