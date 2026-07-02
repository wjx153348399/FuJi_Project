from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from station_config_web.config import AuthConfig, ServerConfig, ShareConfig, WebConfig, WebDbConfig
from station_config_web.repository import (
    StationDirectoryInput,
    StationDirectoryRepository,
    validate_relative_directory_path,
)
from zk_impedance_upload.exceptions import ConfigError


class FakeCursor:
    def __init__(self, rows=None, one=None, rowcount=1):
        self.rows = rows or []
        self.one = one
        self.rowcount = rowcount
        self.calls = []

    def execute(self, sql, *params):
        self.sql = sql
        self.params = list(params)
        self.calls.append((sql, list(params)))
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.one


class FakeConnection:
    def __init__(self, rows=None, one=None, rowcount=1):
        self.cursor_obj = FakeCursor(rows=rows, one=one, rowcount=rowcount)
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


class LegacyFakeCursor:
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


class LegacyFakeConnection:
    def __init__(self, rows):
        self.cursor_obj = LegacyFakeCursor(rows)

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
            connection = LegacyFakeConnection([Row()])

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

    def test_create_config_validates_and_writes_clean_values(self):
        unique_connection = FakeConnection(one=None)
        write_connection = FakeConnection()

        with patch(
            "station_config_web.repository._connect",
            side_effect=[unique_connection, write_connection],
        ):
            StationDirectoryRepository(_config()).create_config(
                StationDirectoryInput(
                    station_code=" AFC ",
                    station_name=" LXD ",
                    directory_path=r"folder/target",
                    enabled=True,
                    sort_order=20,
                    remark=" test ",
                )
            )

        self.assertIn("SELECT TOP 1 id", unique_connection.cursor_obj.sql)
        self.assertIn("INSERT INTO", write_connection.cursor_obj.sql)
        self.assertEqual(
            write_connection.cursor_obj.params,
            ["AFC", "LXD", r"folder\target", 1, 20, "test", "web", "web"],
        )
        self.assertTrue(write_connection.committed)

    def test_create_config_rejects_blank_station_code(self):
        with self.assertRaisesRegex(ConfigError, "上传工站代码"):
            StationDirectoryRepository(_config()).create_config(
                StationDirectoryInput(
                    station_code=" ",
                    station_name="LXD",
                    directory_path="target",
                    enabled=True,
                    sort_order=0,
                    remark=None,
                )
            )

    def test_create_config_rejects_duplicate_directory_path(self):
        duplicate_connection = FakeConnection(one=object())

        with patch("station_config_web.repository._connect", return_value=duplicate_connection):
            with self.assertRaisesRegex(ConfigError, "已存在"):
                StationDirectoryRepository(_config()).create_config(
                    StationDirectoryInput(
                        station_code="LXD",
                        station_name=None,
                        directory_path="target",
                        enabled=True,
                        sort_order=0,
                        remark=None,
                    )
                )

    def test_update_config_excludes_current_id_when_checking_duplicate(self):
        unique_connection = FakeConnection(one=None)
        write_connection = FakeConnection(rowcount=1)

        with patch(
            "station_config_web.repository._connect",
            side_effect=[unique_connection, write_connection],
        ):
            StationDirectoryRepository(_config()).update_config(
                8,
                StationDirectoryInput(
                    station_code="A10",
                    station_name="OUTER",
                    directory_path="outer",
                    enabled=False,
                    sort_order=30,
                    remark=None,
                ),
            )

        self.assertEqual(unique_connection.cursor_obj.params, ["outer", 8])
        self.assertIn("UPDATE", write_connection.cursor_obj.sql)
        self.assertEqual(write_connection.cursor_obj.params[-1], 8)
        self.assertTrue(write_connection.committed)

    def test_set_enabled_updates_status(self):
        connection = FakeConnection(rowcount=1)

        with patch("station_config_web.repository._connect", return_value=connection):
            StationDirectoryRepository(_config()).set_enabled(3, False, updated_by="admin")

        self.assertIn("SET enabled", connection.cursor_obj.sql)
        self.assertEqual(connection.cursor_obj.params, [0, "admin", 3])
        self.assertTrue(connection.committed)

    def test_validate_relative_directory_path_rejects_absolute_paths(self):
        with self.assertRaisesRegex(ConfigError, "UNC"):
            validate_relative_directory_path(r"\\server\share\target")
        with self.assertRaisesRegex(ConfigError, "盘符"):
            validate_relative_directory_path(r"C:\target")
        with self.assertRaisesRegex(ConfigError, r"\.\."):
            validate_relative_directory_path(r"folder\..\target")


def _config(share_root: str = ".") -> WebConfig:
    return WebConfig(
        server=ServerConfig(),
        db=WebDbConfig(host="127.0.0.1", database="QMS", username="sa", password="secret"),
        share=ShareConfig(root=share_root),
        auth=AuthConfig(username="admin", password="secret"),
    )


if __name__ == "__main__":
    unittest.main()
