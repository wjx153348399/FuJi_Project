import unittest
from io import StringIO
from unittest.mock import patch

from run_watcher import main as watch_main
from run_all import build_parser as build_all_parser
from run_all import main as all_main
from run_all import run_combined_services
from zk_impedance_upload import __version__
from zk_impedance_upload.cli import build_parser, main


class ProjectStructureTest(unittest.TestCase):
    def test_package_has_version(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_cli_uses_config_json_by_default(self):
        parser = build_parser()
        args = parser.parse_args([])

        self.assertEqual(args.config, "config.json")
        self.assertFalse(args.watch)

    def test_cli_check_config_reports_missing_file(self):
        stderr = StringIO()

        with patch("sys.stderr", stderr):
            exit_code = main(["--config", "missing-config.json", "--check-config"])

        self.assertEqual(exit_code, 2)
        self.assertIn("配置文件不存在", stderr.getvalue())

    def test_cli_check_config_reports_log_directory_error(self):
        stderr = StringIO()

        with patch("zk_impedance_upload.cli.load_config") as load_config:
            with patch("zk_impedance_upload.cli.ensure_share_access"):
                with patch("zk_impedance_upload.cli.LogStore") as log_store:
                    load_config.return_value.log.dir = "bad-log-dir"
                    log_store.return_value.ensure_ready.side_effect = OSError("no access")

                    with patch("sys.stderr", stderr):
                        exit_code = main(["--config", "config.example.json", "--check-config"])

        self.assertEqual(exit_code, 2)
        self.assertIn("日志目录检查失败", stderr.getvalue())

    def test_cli_check_config_ensures_share_access_before_log_check(self):
        with patch("zk_impedance_upload.cli.load_config") as load_config:
            with patch("zk_impedance_upload.cli.ensure_share_access") as ensure_access:
                with patch("zk_impedance_upload.cli.LogStore") as log_store:
                    with patch("zk_impedance_upload.cli.build_effective_scan_config") as build_effective:
                        exit_code = main(["--config", "config.example.json", "--check-config"])

        self.assertEqual(exit_code, 0)
        ensure_access.assert_called_once_with(load_config.return_value)
        log_store.assert_called_once_with(load_config.return_value.log.dir)
        build_effective.assert_called_once_with(load_config.return_value)

    def test_cli_runs_upload_task_when_not_checking_config(self):
        stdout = StringIO()

        with patch("zk_impedance_upload.cli.load_config") as load_config:
            with patch("zk_impedance_upload.cli.run_upload_task") as run_upload_task:
                run_upload_task.return_value.stats = {"success_count": 1, "fail_count": 0, "skip_count": 0}
                with patch("sys.stdout", stdout):
                    exit_code = main(["--config", "config.example.json"])

        self.assertEqual(exit_code, 0)
        self.assertIn("上传任务完成", stdout.getvalue())
        run_upload_task.assert_called_once_with(load_config.return_value, progress_func=print)

    def test_cli_runs_watch_service_when_watch_flag_is_set(self):
        with patch("zk_impedance_upload.cli.load_config") as load_config:
            with patch("zk_impedance_upload.cli.run_watch_service") as run_watch_service:
                load_config.return_value.watch.enabled = True
                run_watch_service.return_value = 0

                exit_code = main(["--config", "config.example.json", "--watch"])

        self.assertEqual(exit_code, 0)
        run_watch_service.assert_called_once_with(load_config.return_value, progress_func=print)

    def test_cli_rejects_watch_when_config_disables_it(self):
        stderr = StringIO()

        with patch("zk_impedance_upload.cli.load_config") as load_config:
            load_config.return_value.watch.enabled = False

            with patch("sys.stderr", stderr):
                exit_code = main(["--config", "config.example.json", "--watch"])

        self.assertEqual(exit_code, 2)
        self.assertIn("监听功能未启用", stderr.getvalue())

    def test_run_watcher_forces_watch_flag(self):
        with patch("run_watcher.cli_main") as cli_main:
            cli_main.return_value = 0

            exit_code = watch_main(["--config", "config.example.json"])

        self.assertEqual(exit_code, 0)
        cli_main.assert_called_once_with(["--config", "config.example.json", "--watch"])

    def test_run_all_uses_default_config_paths(self):
        parser = build_all_parser()
        args = parser.parse_args([])

        self.assertEqual(args.config, "config.json")
        self.assertEqual(args.web_config, "web_config.json")

    def test_run_all_rejects_disabled_watch_config(self):
        stderr = StringIO()

        with patch("run_all.load_config") as load_config:
            with patch("run_all.load_web_config"):
                load_config.return_value.watch.enabled = False

                with patch("sys.stderr", stderr):
                    exit_code = all_main(["--config", "config.example.json", "--web-config", "web_config.example.json"])

        self.assertEqual(exit_code, 2)
        self.assertIn("监听功能未启用", stderr.getvalue())

    def test_run_all_starts_web_then_watch_service(self):
        calls = []

        def fake_web_runner():
            calls.append("web")

        def fake_watch_service(app_config, progress_func):
            calls.append(("watch", app_config))
            return 0

        exit_code = run_combined_services(
            app_config="config",
            web_runner=fake_web_runner,
            startup_wait_seconds=0.01,
            progress_func=lambda message: None,
            watch_service_func=fake_watch_service,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(calls, ["web", ("watch", "config")])

    def test_run_all_reports_web_start_failure(self):
        def fake_web_runner():
            raise RuntimeError("port in use")

        messages = []

        exit_code = run_combined_services(
            app_config="config",
            web_runner=fake_web_runner,
            startup_wait_seconds=0.01,
            progress_func=messages.append,
            watch_service_func=lambda app_config, progress_func: 0,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("Web 服务启动失败", messages[0])


if __name__ == "__main__":
    unittest.main()
