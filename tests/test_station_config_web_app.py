from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from station_config_web.app import _directory_save_warning, _notice_message
from station_config_web.config import AuthConfig, ServerConfig, ShareConfig, WebConfig, WebDbConfig


class StationConfigWebAppTest(unittest.TestCase):
    def test_notice_message_maps_known_save_results(self):
        self.assertEqual(_notice_message("created"), "新增配置保存成功")
        self.assertEqual(_notice_message("updated"), "配置修改保存成功")
        self.assertEqual(_notice_message("enabled"), "配置启用成功")
        self.assertEqual(_notice_message("disabled"), "配置停用成功")

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


def _config(share_root: str) -> WebConfig:
    return WebConfig(
        server=ServerConfig(),
        db=WebDbConfig(host="127.0.0.1", database="QMS", username="sa", password="secret"),
        share=ShareConfig(root=share_root),
        auth=AuthConfig(username="admin", password="secret"),
    )


if __name__ == "__main__":
    unittest.main()
