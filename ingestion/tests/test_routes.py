"""ingestion HTTP routes. Parsing is stubbed: these tests guard routing, permissions,
audit events and temp-file handling of /map-file."""
import io
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")
os.environ.setdefault("INTERNAL_API_TOKEN", "test-internal-token")

sys.modules.setdefault("db", MagicMock(engine=MagicMock(), execute_query=MagicMock(return_value=[]),
                                       LOCAL_SCHEMA="public"))

# Stub the pandas-heavy modules: test_row_order exercises the real parsing code.
_mock_data_service = MagicMock()
_mock_data_service.OversizedColumnError = type("OversizedColumnError", (Exception,), {})
_mock_data_service.ColumnCountMismatchError = type("ColumnCountMismatchError", (Exception,), {})
_mock_data_service.ColumnNameMismatchError = type("ColumnNameMismatchError", (Exception,), {})
_mock_data_service.IncompatibleHeaderModeError = type("IncompatibleHeaderModeError", (Exception,), {})
sys.modules.setdefault("services.data_service", _mock_data_service)
sys.modules.setdefault("services.mapper_service", MagicMock())

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


class TestIngestionRoutes(unittest.TestCase):

    def setUp(self):
        from app import app  # noqa: PLC0415 -- import tardio para usar os mocks ja instalados
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_upload_requires_upload_permission(self):
        resp = self.client.post(
            "/api/v1/upload",
            data={"file": (io.BytesIO(b"a,b\n1,2\n"), "x.csv")},
            headers=_auth(can_query=True),
        )
        self.assertEqual(resp.status_code, 403)

    @patch("app.upload_excel", return_value={"message": "ok", "rows": 1, "table_name": "x"})
    def test_upload_success_is_audited(self, mock_upload):
        resp = self.client.post(
            "/api/v1/upload",
            data={"file": (io.BytesIO(b"a,b\n1,2\n"), "x.csv"), "table_name": "x"},
            headers=_auth(can_upload=True),
        )
        self.assertEqual(resp.status_code, 200)
        mock_upload.assert_called_once()
        self.assertEqual([e["action"] for e in self.audit_events], ["UPLOAD"])

    def test_upload_rejects_malformed_column_renames(self):
        resp = self.client.post(
            "/api/v1/upload",
            data={"file": (io.BytesIO(b"a\n1\n"), "x.csv"), "column_renames": "[1,2]"},
            headers=_auth(can_upload=True),
        )
        self.assertEqual(resp.status_code, 400)

    @patch("app.insert_row", return_value={"message": "Data inserted successfully"})
    def test_insert_json_row(self, mock_insert):
        resp = self.client.post(
            "/api/v1/tables/vendas/data",
            json={"data": {"a": "1"}},
            headers=_auth(can_upload=True),
        )
        self.assertEqual(resp.status_code, 200)
        mock_insert.assert_called_once_with("vendas", {"a": "1"})

    def test_insert_without_payload_is_400(self):
        resp = self.client.post("/api/v1/tables/vendas/data", json={}, headers=_auth(can_upload=True))
        self.assertEqual(resp.status_code, 400)

    @patch("app.analyze_file_structure")
    def test_map_file_never_writes_outside_its_temp_dir(self, mock_analyze):
        seen = {}

        def analyze(path):
            seen["path"] = path
            seen["existed"] = os.path.exists(path)
            return {"columns": []}

        mock_analyze.side_effect = analyze
        resp = self.client.post(
            "/api/v1/map-file",
            data={"file": (io.BytesIO(b"a\n1\n"), "../../app/evil.csv")},
            headers=_auth(can_upload=True),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(seen["existed"])
        self.assertEqual(os.path.basename(seen["path"]), "evil.csv")
        self.assertIn("map-file-", os.path.basename(os.path.dirname(seen["path"])))
        self.assertNotIn("..", seen["path"])
        self.assertFalse(os.path.exists(seen["path"]), "temp file must be removed")


if __name__ == "__main__":
    unittest.main()
