import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from zk_impedance_upload.config import AppConfig, LogConfig, ScanConfig, ShareConfig, UploadConfig, WatchConfig
from zk_impedance_upload.log_store import LogStore
from zk_impedance_upload.watcher import (
    EventDebouncer,
    WatchEvent,
    build_watch_summary,
    collect_watch_snapshot,
    diff_watch_snapshots,
    format_watch_log_entry,
    run_watch_service,
)


class WatcherTest(unittest.TestCase):
    def test_collect_watch_snapshot_skips_excluded_directories(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target_dir = root / "target"
            work_dir = target_dir / "AFX"
            log_dir = target_dir / "LOG"
            work_dir.mkdir(parents=True)
            log_dir.mkdir(parents=True)
            excel_file = work_dir / "report.xlsx"
            skipped_file = log_dir / "skip.xlsx"
            excel_file.write_text("ok", encoding="utf-8")
            skipped_file.write_text("skip", encoding="utf-8")

            snapshot = collect_watch_snapshot(
                root,
                ScanConfig(target_dirs=["target"], exclude_dirs=["LOG"], recursive=True),
            )

        entry_names = {entry.path.name for entry in snapshot.entries.values()}
        self.assertIn("report.xlsx", entry_names)
        self.assertNotIn("skip.xlsx", entry_names)
        self.assertEqual(snapshot.missing_dirs, [])
        self.assertEqual(snapshot.failed_dirs, [])

    def test_diff_watch_snapshots_detects_created_modified_deleted_and_renamed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target_dir = root / "target"
            target_dir.mkdir()
            created_file = target_dir / "created.xlsx"
            modified_file = target_dir / "modified.xlsx"
            deleted_file = target_dir / "deleted.xlsx"
            renamed_before = target_dir / "rename_before.xlsx"
            created_file.write_text("created", encoding="utf-8")
            modified_file.write_text("before", encoding="utf-8")
            deleted_file.write_text("deleted", encoding="utf-8")
            renamed_before.write_text("same", encoding="utf-8")
            previous = collect_watch_snapshot(root, ScanConfig(target_dirs=["target"], recursive=True))

            modified_file.write_text("after-change", encoding="utf-8")
            deleted_file.unlink()
            renamed_after = target_dir / "rename_after.xlsx"
            renamed_before.rename(renamed_after)
            created_file.unlink()
            fresh_file = target_dir / "fresh.xlsx"
            fresh_file.write_text("fresh", encoding="utf-8")

            current = collect_watch_snapshot(root, ScanConfig(target_dirs=["target"], recursive=True))
            events = diff_watch_snapshots(previous, current)

        event_types = {event.event_type for event in events}
        self.assertIn("watch_created", event_types)
        self.assertIn("watch_modified", event_types)
        self.assertIn("watch_deleted", event_types)
        self.assertIn("watch_renamed", event_types)

        renamed_event = next(event for event in events if event.event_type == "watch_renamed")
        self.assertEqual(renamed_event.previous_path.name, "rename_before.xlsx")
        self.assertEqual(renamed_event.path.name, "rename_after.xlsx")

    def test_event_debouncer_suppresses_duplicate_event_within_window(self):
        event = WatchEvent(
            event_type="watch_modified",
            path=Path(r"\\10.0.8.252\share\report.xlsx"),
            is_dir=False,
            is_excel=True,
        )
        debouncer = EventDebouncer(debounce_seconds=5)

        first_batch = debouncer.filter([event], now_monotonic=10.0)
        second_batch = debouncer.filter([event], now_monotonic=12.0)
        third_batch = debouncer.filter([event], now_monotonic=16.0)

        self.assertEqual(len(first_batch), 1)
        self.assertEqual(second_batch, [])
        self.assertEqual(len(third_batch), 1)

    def test_format_watch_log_entry_contains_expected_fields(self):
        event = WatchEvent(
            event_type="watch_renamed",
            path=Path(r"\\10.0.8.252\share\after.xlsx"),
            previous_path=Path(r"\\10.0.8.252\share\before.xlsx"),
            is_dir=False,
            is_excel=True,
        )

        entry = format_watch_log_entry(event, "2026-06-14 08:00:00")

        self.assertEqual(entry["event_type"], "watch_renamed")
        self.assertEqual(entry["previous_path"], r"\\10.0.8.252\share\before.xlsx")
        self.assertTrue(entry["is_excel"])

    def test_run_watch_service_writes_detected_events_to_watch_log(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            target_dir = root / "target"
            target_dir.mkdir(parents=True)
            watched_file = target_dir / "report.xlsx"
            watched_file.write_text("before", encoding="utf-8")
            log_dir = Path(tmp_dir) / "logs"
            config = _build_app_config(root, log_dir)

            def fake_sleep(_: float) -> None:
                watched_file.write_text("after-change", encoding="utf-8")

            exit_code = run_watch_service(
                config,
                max_iterations=1,
                sleep_func=fake_sleep,
                now_func=lambda: datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )

            log_path = log_dir / "watch_log_2026-06-14.jsonl"
            lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            events = [eval_line["event_type"] for eval_line in map(_loads_json_line, lines)]

        self.assertEqual(exit_code, 0)
        self.assertIn("watch_modified", events)

    def test_run_watch_service_ensures_share_access_before_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            target_dir = root / "target"
            target_dir.mkdir(parents=True)
            log_dir = Path(tmp_dir) / "logs"
            config = _build_app_config(root, log_dir)
            calls = []

            run_watch_service(
                config,
                max_iterations=0,
                sleep_func=lambda seconds: None,
                now_func=lambda: datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                share_access_func=lambda config: calls.append((config.share.root, config.log.dir)),
            )

        self.assertEqual(len(calls), 1)

    def test_run_watch_service_reports_progress_messages(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            target_dir = root / "target"
            target_dir.mkdir(parents=True)
            watched_file = target_dir / "report.xlsx"
            watched_file.write_text("before", encoding="utf-8")
            log_dir = Path(tmp_dir) / "logs"
            config = _build_app_config(root, log_dir)
            messages = []

            def fake_sleep(_: float) -> None:
                watched_file.write_text("after-change", encoding="utf-8")

            run_watch_service(
                config,
                max_iterations=1,
                sleep_func=fake_sleep,
                now_func=lambda: datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                progress_func=messages.append,
            )

        joined = "\n".join(messages)
        self.assertIn("开始监听任务", joined)
        self.assertIn("初始监听快照完成", joined)
        self.assertIn("监听已启动", joined)
        self.assertIn("监听轮询", joined)
        self.assertIn("监听事件", joined)

    def test_build_watch_summary_counts_logged_events(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = LogStore(tmp_dir)
            store.append_watch_log(
                "2026-06-14",
                {
                    "event_type": "watch_created",
                    "path": "a.xlsx",
                    "previous_path": None,
                    "is_dir": False,
                    "is_excel": True,
                    "log_time": "2026-06-14 08:00:00",
                },
            )
            store.append_watch_log(
                "2026-06-14",
                {
                    "event_type": "watch_notice",
                    "path": "missing-dir",
                    "previous_path": None,
                    "is_dir": True,
                    "is_excel": False,
                    "log_time": "2026-06-14 08:00:01",
                },
            )

            summary_path = build_watch_summary(store, "2026-06-14", "2026-06-14_08-10-00")
            summary = _loads_json_line(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(summary["stats"]["watch_created"], 1)
        self.assertEqual(summary["stats"]["watch_notice"], 1)
        self.assertEqual(summary["stats"]["excel_event_count"], 1)


def _build_app_config(root: Path, log_dir: Path) -> AppConfig:
    return AppConfig(
        share=ShareConfig(root=str(root), username="IT", password="FQCIT"),
        log=LogConfig(dir=str(log_dir)),
        upload=UploadConfig(url="http://example.test/upload"),
        scan=ScanConfig(target_dirs=["target"], recursive=True),
        watch=WatchConfig(enabled=True, poll_interval_seconds=1, debounce_seconds=1),
    )


def _loads_json_line(content: str) -> dict:
    import json

    return json.loads(content)


if __name__ == "__main__":
    unittest.main()
