from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from station_config_web.app import create_app
from station_config_web.app import _ensure_web_log_share_access
from station_config_web.app import _directory_save_warning, _notice_message, _save_notice_key
from station_config_web.config import AuthConfig, LogConfig, ServerConfig, ShareConfig, WebConfig, WebDbConfig
from zk_impedance_upload.exceptions import ConfigError


class StationConfigWebAppTest(unittest.TestCase):
    def test_notice_message_maps_known_save_results(self):
        self.assertIn("新增配置保存成功", _notice_message("created"))
        self.assertIn("自动加载新配置", _notice_message("created"))
        self.assertIn("flow 待确认", _notice_message("created_blank_flow"))
        self.assertIn("配置修改保存成功", _notice_message("updated"))
        self.assertIn("自动加载新配置", _notice_message("updated"))
        self.assertIn("当前停用", _notice_message("updated_disabled_blank_flow"))
        self.assertIn("配置启用成功", _notice_message("enabled"))
        self.assertIn("配置停用成功", _notice_message("disabled"))

    def test_save_notice_key_reports_blank_flow_enabled_state(self):
        self.assertEqual(_save_notice_key({"flow": "", "enabled": "1"}, "created"), "created_blank_flow")
        self.assertEqual(
            _save_notice_key({"flow": "", "enabled": "0"}, "updated"),
            "updated_disabled_blank_flow",
        )
        self.assertEqual(_save_notice_key({"flow": "A557", "enabled": "1"}, "created"), "created")

    def test_notice_message_ignores_unknown_values(self):
        self.assertEqual(_notice_message("bad"), "")
        self.assertEqual(_notice_message(""), "")

    def test_directory_save_warning_allows_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "target").mkdir()

            warning = _directory_save_warning(_config(tmp_dir), {"directory_path": "target"})

        self.assertEqual(warning, "")

    def test_directory_save_warning_reports_missing_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            warning = _directory_save_warning(_config(tmp_dir), {"directory_path": "missing"})

        self.assertIn("目录不存在", warning)
        self.assertIn("missing", warning)

    def test_directory_save_warning_reports_file_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "not_dir").write_text("content", encoding="utf-8")

            warning = _directory_save_warning(_config(tmp_dir), {"directory_path": "not_dir"})

        self.assertIn("不是目录", warning)

    def test_dashboard_and_log_api_read_file_logs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            root.mkdir()
            log_dir.mkdir()
            (log_dir / "upload_log_2026-06-14.jsonl").write_text(
                json.dumps({"action": "upload_success", "filename": "ok.xlsx"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            config_path = Path(tmp_dir) / "web_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "db": {
                            "host": "127.0.0.1",
                            "database": "QMS",
                            "username": "sa",
                            "password": "secret",
                        },
                        "share": {"root": str(root)},
                        "log": {"dir": str(log_dir)},
                        "auth": {"password": "secret"},
                    }
                ),
                encoding="utf-8",
            )
            client = TestClient(create_app(config_path))

            root_response = client.get("/", follow_redirects=False)
            dashboard_response = client.get("/dashboard")
            station_response = client.get("/station-config")
            api_response = client.get("/api/logs/latest")

        self.assertEqual(root_response.status_code, 307)
        self.assertEqual(root_response.headers["location"], "/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(station_response.status_code, 200)
        self.assertIn("ok.xlsx", dashboard_response.text)
        self.assertEqual(api_response.json()["count"], 1)

    def test_dashboard_handles_log_directory_access_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            root.mkdir()
            config_path = Path(tmp_dir) / "web_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "db": {
                            "host": "127.0.0.1",
                            "database": "QMS",
                            "username": "sa",
                            "password": "secret",
                        },
                        "share": {"root": str(root)},
                        "log": {"dir": str(log_dir)},
                        "auth": {"password": "secret"},
                    }
                ),
                encoding="utf-8",
            )
            client = TestClient(create_app(config_path))

            with patch("zk_impedance_upload.log_store.LogStore.read_recent_logs", side_effect=OSError("bad credentials")):
                dashboard_response = client.get("/dashboard")
                api_response = client.get("/api/logs/latest")

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn("bad credentials", dashboard_response.text)
        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(api_response.json()["error"], "bad credentials")

    def test_log_api_prefers_database_logs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            root.mkdir()
            log_dir.mkdir()
            (log_dir / "upload_log_2026-06-14.jsonl").write_text(
                json.dumps({"action": "upload_success", "filename": "file-log.xlsx"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            config_path = Path(tmp_dir) / "web_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "db": {
                            "host": "127.0.0.1",
                            "database": "QMS",
                            "username": "sa",
                            "password": "secret",
                        },
                        "share": {"root": str(root)},
                        "log": {"dir": str(log_dir)},
                        "auth": {"password": "secret"},
                    }
                ),
                encoding="utf-8",
            )
            fake_store = SimpleNamespace(
                read_recent_logs=lambda **kwargs: [
                    {
                        "log_type": "upload",
                        "log_date": "2026-06-14",
                        "level": "info",
                        "status": "success",
                        "time": "2026-06-14 08:00:00",
                        "action": "upload_success",
                        "filename": "db-log.xlsx",
                        "path": "share/db-log.xlsx",
                        "flow": "",
                        "http_status": 200,
                        "retry_count": 0,
                        "message": "",
                        "raw": {},
                    }
                ],
                build_status_snapshot=lambda recent: {
                    "latest_upload": recent[0],
                    "latest_watch": None,
                    "latest_error": None,
                    "today_success": 0,
                    "today_failed": 0,
                    "today_skipped": 0,
                },
            )

            with patch("station_config_web.app._web_db_log_store", return_value=fake_store):
                client = TestClient(create_app(config_path))
                response = client.get("/api/logs/latest")

        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["items"][0]["filename"], "db-log.xlsx")

    def test_status_api_includes_service_status(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            root.mkdir()
            log_dir.mkdir()
            (log_dir / "service_status.json").write_text(
                json.dumps(
                    {
                        "state": "running",
                        "message": "watcher running",
                        "updated_at": "2026-07-07 08:00:00",
                        "watcher_restart_count": 2,
                    }
                ),
                encoding="utf-8",
            )
            config_path = Path(tmp_dir) / "web_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "db": {
                            "host": "127.0.0.1",
                            "database": "QMS",
                            "username": "sa",
                            "password": "secret",
                        },
                        "share": {"root": str(root)},
                        "log": {"dir": str(log_dir)},
                        "auth": {"password": "secret"},
                    }
                ),
                encoding="utf-8",
            )
            fake_store = SimpleNamespace(
                read_recent_logs=lambda **kwargs: [],
                build_status_snapshot=lambda recent: {
                    "latest_upload": None,
                    "latest_watch": None,
                    "latest_error": None,
                    "today_success": 0,
                    "today_failed": 0,
                    "today_skipped": 0,
                },
            )

            with patch("station_config_web.app._web_db_log_store", return_value=fake_store):
                client = TestClient(create_app(config_path))
                response = client.get("/api/status")

        self.assertEqual(response.json()["service"]["state"], "running")
        self.assertEqual(response.json()["service"]["watcher_restart_count"], 2)

    def test_log_api_falls_back_to_file_logs_when_database_fails(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            root.mkdir()
            log_dir.mkdir()
            (log_dir / "upload_log_2026-06-14.jsonl").write_text(
                json.dumps({"action": "upload_success", "filename": "file-log.xlsx"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            config_path = Path(tmp_dir) / "web_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "db": {
                            "host": "127.0.0.1",
                            "database": "QMS",
                            "username": "sa",
                            "password": "secret",
                        },
                        "share": {"root": str(root)},
                        "log": {"dir": str(log_dir)},
                        "auth": {"password": "secret"},
                    }
                ),
                encoding="utf-8",
            )
            fake_store = SimpleNamespace(read_recent_logs=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))

            with patch("station_config_web.app._web_db_log_store", return_value=fake_store):
                client = TestClient(create_app(config_path))
                response = client.get("/api/logs/latest")

        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["items"][0]["filename"], "file-log.xlsx")
        self.assertIn("数据库日志读取失败", response.json()["error"])

    def test_ensure_web_log_share_access_uses_configured_credentials(self):
        config = WebConfig(
            server=ServerConfig(),
            db=WebDbConfig(host="127.0.0.1", database="QMS", username="sa", password="secret"),
            share=ShareConfig(root=r"\\server\share\impedance", username="IT", password="FQCIT"),
            log=LogConfig(dir=r"\\server\share\ZK_LOG"),
            auth=AuthConfig(username="admin", password="secret"),
        )
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("station_config_web.app._path_exists", return_value=False):
            with patch("station_config_web.app.subprocess.run", side_effect=fake_run):
                _ensure_web_log_share_access(config)

        self.assertEqual(calls[0][0][:4], ["net", "use", r"\\server\share", "/user:IT"])
        self.assertEqual(calls[0][0][4], "FQCIT")

    def test_ensure_web_log_share_access_reports_missing_credentials(self):
        config = WebConfig(
            server=ServerConfig(),
            db=WebDbConfig(host="127.0.0.1", database="QMS", username="sa", password="secret"),
            share=ShareConfig(root=r"\\server\share\impedance"),
            log=LogConfig(dir=r"\\server\share\ZK_LOG"),
            auth=AuthConfig(username="admin", password="secret"),
        )

        with patch("station_config_web.app._path_exists", return_value=False):
            with self.assertRaisesRegex(ConfigError, "share.username/share.password"):
                _ensure_web_log_share_access(config)


def _config(share_root: str) -> WebConfig:
    return WebConfig(
        server=ServerConfig(),
        db=WebDbConfig(host="127.0.0.1", database="QMS", username="sa", password="secret"),
        share=ShareConfig(root=share_root),
        log=LogConfig(dir=str(Path(share_root) / "ZK_LOG")),
        auth=AuthConfig(username="admin", password="secret"),
    )


if __name__ == "__main__":
    unittest.main()
