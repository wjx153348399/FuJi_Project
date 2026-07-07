from __future__ import annotations

import sys
import types
import unittest
from types import SimpleNamespace

from zk_impedance_upload.db_log_store import DbLogStore


class DbLogStoreTest(unittest.TestCase):
    def test_append_upload_log_maps_runtime_fields_to_insert(self):
        calls = []

        class FakeCursor:
            def execute(self, sql, *params):
                calls.append((sql, params))
                return self

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def cursor(self):
                return FakeCursor()

            def commit(self):
                calls.append(("commit", ()))

        fake_pyodbc = types.SimpleNamespace(connect=lambda connection_string, timeout: FakeConnection())
        original_pyodbc = sys.modules.get("pyodbc")
        sys.modules["pyodbc"] = fake_pyodbc
        try:
            store = DbLogStore(
                SimpleNamespace(
                    host="127.0.0.1",
                    port=1433,
                    database="QMS",
                    username="sa",
                    password="secret",
                    connect_timeout_seconds=5,
                ),
                table="dbo.zk_upload_runtime_log",
                driver="ODBC Driver 17 for SQL Server",
            )

            result = store.append_upload_log(
                "2026-07-06",
                {
                    "action": "upload_failed",
                    "run_id": "ZK-1",
                    "filename": "bad.xlsx",
                    "full_path": r"\\server\share\bad.xlsx",
                    "flow": "",
                    "http_status": 500,
                    "retry_count": 2,
                    "error": "backend failed",
                    "log_time": "2026-07-07 08:00:00",
                },
            )
        finally:
            if original_pyodbc is None:
                sys.modules.pop("pyodbc", None)
            else:
                sys.modules["pyodbc"] = original_pyodbc

        self.assertEqual(result, "db:dbo.zk_upload_runtime_log")
        sql, params = calls[0]
        self.assertIn("[dbo].[zk_upload_runtime_log]", sql)
        self.assertEqual(params[1:8], ("2026-07-06", "upload", "error", "failed", "upload_failed", "ZK-1", "bad.xlsx"))
        self.assertEqual(params[12], "backend failed")
        self.assertEqual(calls[-1], ("commit", ()))


if __name__ == "__main__":
    unittest.main()
