from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from station_config_web.config import AuthConfig, ServerConfig, ShareConfig, WebConfig, WebDbConfig
from station_config_web.repository import StationDirectoryRepository
from zk_impedance_upload.exceptions import ConfigError


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = []

    def execute(self, sql, *params):
        self.sql = sql
        self.params = list(params)
        return self

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)

    def cursor(self):
        return self.cursor_obj

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


class Row:
    id = 1
    station_code = "UNKNOWN"
    station_name = "LXD"
    directory_path = "target"
    enabled = True
    sort_order = 10
    remark = "HALF-LXD"
    created_by = "system"
    created_at = "2026-07-01 10:00:00"
    updated_by = "system"
    updated_at = "2026-07-01 10:00:00"


class StationConfigWebRepositoryTest(unittest.TestCase):
    def test_list_configs_builds_rows_with_full_path_state(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "target").mkdir()
            config = _config(tmp_dir)
            connection = FakeConnection([Row()])

            with patch("station_config_web.repository._connect", return_value=connection):
                rows = StationDirectoryRepository(config).list_configs(status="enabled", keyword="LXD")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].station_code, "UNKNOWN")
        self.assertTrue(rows[0].path_is_dir)
        self.assertIn("WHERE enabled = 1", connection.cursor_obj.sql)
        self.assertEqual(connection.cursor_obj.params, ["%LXD%", "%LXD%", "%LXD%", "%LXD%"])

    def test_list_configs_rejects_invalid_status(self):
        with self.assertRaisesRegex(ConfigError, "status"):
            StationDirectoryRepository(_config()).list_configs(status="bad")


def _config(share_root: str = ".") -> WebConfig:
    return WebConfig(
        server=ServerConfig(),
        db=WebDbConfig(host="127.0.0.1", database="QMS", username="sa", password="secret"),
        share=ShareConfig(root=share_root),
        auth=AuthConfig(username="admin", password="secret"),
    )


if __name__ == "__main__":
    unittest.main()
