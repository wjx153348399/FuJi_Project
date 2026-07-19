import json
import tempfile
import unittest
from pathlib import Path

from zk_impedance_upload.config import load_config
from zk_impedance_upload.exceptions import ConfigError


class ConfigTest(unittest.TestCase):
    def test_loads_utf8_config_into_sections(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "share": {
                            "root": "\\\\10.0.8.252\\ProductionFieldFile 现场公共盘\\阻抗",
                            "username": "IT",
                            "password": "FQCIT",
                        },
                        "log": {"dir": "\\\\10.0.8.252\\File\\ZK_LOG"},
                        "upload": {
                            "url": "http://10.0.8.217:8108/service-qms/file/importImpedanceData",
                            "schedule_time": "08:00",
                            "day_offset": 1,
                            "max_upload_files": None,
                            "dry_run": False,
                            "timeout_seconds": 60,
                            "retry_count": 2,
                        },
                        "scan": {
                            "recursive": True,
                            "extensions": [".xls", ".xlsx"],
                            "exclude_prefixes": ["~$"],
                            "exclude_dirs": ["LOG", "log", "日志", "备份", "backup"],
                            "target_dirs": [
                                "ผลิตภัณฑ์กึ่งสำเร็จรูป图形后(半成品)",
                                "ผลิตภัณฑ์สำเร็จรูปCP-阻抗",
                            ],
                        },
                        "watch": {
                            "enabled": False,
                            "mode": "polling",
                            "notice_mode": "log_and_daily_summary",
                            "poll_interval_seconds": 5,
                            "debounce_seconds": 5,
                            "config_reload_interval_seconds": 7,
                            "stable_check_seconds": 2,
                            "stable_check_attempts": 3,
                            "queue_max_workers": 1,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.share.root, "\\\\10.0.8.252\\ProductionFieldFile 现场公共盘\\阻抗")
        self.assertEqual(config.log.dir, "\\\\10.0.8.252\\File\\ZK_LOG")
        self.assertEqual(config.upload.day_offset, 1)
        self.assertEqual(config.scan.extensions, [".xls", ".xlsx"])
        self.assertIn("ผลิตภัณฑ์สำเร็จรูปCP-阻抗", config.scan.target_dirs)
        self.assertFalse(config.watch.enabled)
        self.assertEqual(config.watch.mode, "polling")
        self.assertEqual(config.watch.poll_interval_seconds, 5)
        self.assertEqual(config.watch.debounce_seconds, 5)
        self.assertEqual(config.watch.config_reload_interval_seconds, 7)
        self.assertEqual(config.watch.stable_check_seconds, 2)
        self.assertEqual(config.watch.stable_check_attempts, 3)
        self.assertEqual(config.watch.queue_max_workers, 1)
        self.assertEqual(config.station_config.source, "json")
        self.assertEqual(config.station_config.db.driver, "sqlserver")
        self.assertEqual(config.station_config.db.port, 1433)
        self.assertTrue(config.runtime_log.db_enabled)
        self.assertEqual(config.runtime_log.db_table, "dbo.zk_upload_runtime_log")

    def test_missing_required_config_field_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "share": {"root": "\\\\server\\share", "username": "IT"},
                        "log": {"dir": "\\\\server\\log"},
                        "upload": {"url": "http://example.test/upload"},
                        "scan": {"target_dirs": []},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "share.password"):
                load_config(config_path)

    def test_missing_config_file_raises_clear_error(self):
        with self.assertRaisesRegex(ConfigError, "配置文件不存在"):
            load_config("missing-config.json")

    def test_loads_config_with_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "share": {"root": "\\\\server\\share", "username": "IT", "password": "FQCIT"},
                        "log": {"dir": "\\\\server\\log"},
                        "upload": {"url": "http://example.test/upload"},
                        "scan": {"target_dirs": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8-sig",
            )

            config = load_config(config_path)

        self.assertEqual(config.share.username, "IT")

    def test_watch_positive_int_fields_must_be_greater_than_zero(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "share": {"root": "\\\\server\\share", "username": "IT", "password": "FQCIT"},
                        "log": {"dir": "\\\\server\\log"},
                        "upload": {"url": "http://example.test/upload"},
                        "scan": {"target_dirs": []},
                        "watch": {"poll_interval_seconds": 0},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "poll_interval_seconds"):
                load_config(config_path)

    def test_invalid_watch_mode_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "share": {"root": "\\\\server\\share", "username": "IT", "password": "FQCIT"},
                        "log": {"dir": "\\\\server\\log"},
                        "upload": {"url": "http://example.test/upload"},
                        "scan": {"target_dirs": []},
                        "watch": {"mode": "invalid"},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "watch.mode"):
                load_config(config_path)

    def test_loads_station_directory_targets(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "share": {"root": "\\\\server\\share", "username": "IT", "password": "FQCIT"},
                        "log": {"dir": "\\\\server\\log"},
                        "upload": {"url": "http://example.test/upload"},
                        "scan": {
                            "targets": [
                                {"flow": "A10", "dir": "station-a"},
                                {"flow": "A50", "dir": "station-b", "enabled": False},
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.scan.targets[0].flow, "A10")
        self.assertEqual(config.scan.targets[0].dir, "station-a")
        self.assertTrue(config.scan.targets[0].enabled)
        self.assertEqual(config.scan.targets[1].flow, "A50")
        self.assertFalse(config.scan.targets[1].enabled)

    def test_loads_station_directory_targets_with_blank_flow(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "share": {"root": "\\\\server\\share", "username": "IT", "password": "FQCIT"},
                        "log": {"dir": "\\\\server\\log"},
                        "upload": {"url": "http://example.test/upload"},
                        "scan": {"targets": [{"dir": "station-a"}, {"flow": " ", "dir": "station-b"}]},
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.scan.targets[0].flow, "")
        self.assertEqual(config.scan.targets[1].flow, "")

    def test_duplicate_station_target_dir_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "share": {"root": "\\\\server\\share", "username": "IT", "password": "FQCIT"},
                        "log": {"dir": "\\\\server\\log"},
                        "upload": {"url": "http://example.test/upload"},
                        "scan": {
                            "targets": [
                                {"flow": "A10", "dir": "station-a"},
                                {"flow": "A50", "dir": "station-a"},
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "duplicate dir"):
                load_config(config_path)

    def test_loads_sqlserver_station_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "share": {"root": "\\\\server\\share", "username": "IT", "password": "FQCIT"},
                        "log": {"dir": "\\\\server\\log"},
                        "upload": {"url": "http://example.test/upload"},
                        "scan": {"target_dirs": []},
                        "station_config": {
                            "source": "db_then_json",
                            "on_db_error": "fallback_to_json",
                            "db": {
                                "enabled": True,
                                "driver": "sqlserver",
                                "odbc_driver": "ODBC Driver 18 for SQL Server",
                                "host": "127.0.0.1",
                                "port": 1433,
                                "database": "QMS",
                                "username": "sa",
                                "password": "secret",
                                "table": "dbo.station_directory_config",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.station_config.source, "db_then_json")
        self.assertEqual(config.station_config.on_db_error, "fallback_to_json")
        self.assertTrue(config.station_config.db.enabled)
        self.assertEqual(config.station_config.db.driver, "sqlserver")
        self.assertEqual(config.station_config.db.odbc_driver, "ODBC Driver 18 for SQL Server")
        self.assertEqual(config.station_config.db.port, 1433)
        self.assertEqual(config.station_config.db.table, "dbo.station_directory_config")

    def test_invalid_station_config_source_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "share": {"root": "\\\\server\\share", "username": "IT", "password": "FQCIT"},
                        "log": {"dir": "\\\\server\\log"},
                        "upload": {"url": "http://example.test/upload"},
                        "scan": {"target_dirs": []},
                        "station_config": {"source": "database"},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "station_config.source"):
                load_config(config_path)


if __name__ == "__main__":
    unittest.main()
