import unittest
from pathlib import Path

from zk_impedance_upload.config import AppConfig, LogConfig, ScanConfig, ShareConfig, UploadConfig, WatchConfig
from zk_impedance_upload.exceptions import ConfigError
from zk_impedance_upload.share_auth import collect_share_roots, ensure_share_access, get_share_root


class ShareAuthTest(unittest.TestCase):
    def test_get_share_root_extracts_unc_share_name(self):
        self.assertEqual(
            get_share_root(r"\\10.0.8.252\File\ZK_LOG"),
            r"\\10.0.8.252\File",
        )
        self.assertEqual(
            get_share_root(r"\\10.0.8.252\ProductionFieldFile 现场公共盘\阻抗"),
            r"\\10.0.8.252\ProductionFieldFile 现场公共盘",
        )

    def test_get_share_root_returns_none_for_local_path(self):
        self.assertIsNone(get_share_root(Path(r"D:\PythonProject\ZK")))

    def test_collect_share_roots_deduplicates_scan_and_log_shares(self):
        config = _config(
            share_root=r"\\10.0.8.252\ProductionFieldFile 现场公共盘\阻抗",
            log_dir=r"\\10.0.8.252\File\ZK_LOG",
        )

        roots = collect_share_roots(config)

        self.assertEqual(
            roots,
            [
                r"\\10.0.8.252\ProductionFieldFile 现场公共盘",
                r"\\10.0.8.252\File",
            ],
        )

    def test_ensure_share_access_skips_accessible_share(self):
        calls = []
        config = _config(
            share_root=r"\\10.0.8.252\File\source",
            log_dir=r"\\10.0.8.252\File\ZK_LOG",
        )

        ensure_share_access(
            config,
            exists_func=lambda path: True,
            run_func=lambda command: calls.append(command),
        )

        self.assertEqual(calls, [])

    def test_ensure_share_access_runs_net_use_for_inaccessible_share(self):
        calls = []
        config = _config(
            share_root=r"\\10.0.8.252\File\source",
            log_dir=r"\\10.0.8.252\File\ZK_LOG",
        )

        ensure_share_access(
            config,
            exists_func=lambda path: False,
            run_func=lambda command: calls.append(command),
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:4], ["net", "use", r"\\10.0.8.252\File", "/user:IT"])
        self.assertEqual(calls[0][4], "FQCIT")

    def test_ensure_share_access_reports_net_use_failure(self):
        config = _config(
            share_root=r"\\10.0.8.252\File\source",
            log_dir=r"\\10.0.8.252\File\ZK_LOG",
        )

        with self.assertRaises(ConfigError) as context:
            ensure_share_access(
                config,
                exists_func=lambda path: False,
                run_func=lambda command: (_ for _ in ()).throw(RuntimeError("net use failed")),
            )

        self.assertIn("共享盘登录失败", str(context.exception))


def _config(share_root: str, log_dir: str) -> AppConfig:
    return AppConfig(
        share=ShareConfig(root=share_root, username="IT", password="FQCIT"),
        log=LogConfig(dir=log_dir),
        upload=UploadConfig(url="http://example.test/upload"),
        scan=ScanConfig(),
        watch=WatchConfig(),
    )


if __name__ == "__main__":
    unittest.main()
