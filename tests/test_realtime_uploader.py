import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from zk_impedance_upload.config import (
    AppConfig,
    LogConfig,
    ScanConfig,
    ScanTargetConfig,
    ShareConfig,
    UploadConfig,
    WatchConfig,
)
from zk_impedance_upload.realtime_uploader import RealtimeUploadService, wait_for_stable_file
from zk_impedance_upload.uploader import UploadResult
from zk_impedance_upload.log_store import LogStore
from zk_impedance_upload.watcher import WatchEvent


class RealtimeUploaderTest(unittest.TestCase):
    def test_handle_event_uploads_matching_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            target = root / "station-a" / "OUTER"
            target.mkdir(parents=True)
            file_path = target / "report.xlsx"
            file_path.write_bytes(b"excel")
            _set_mtime(file_path, "2026-06-13 10:00:00")
            uploaded = []
            service = RealtimeUploadService(
                _config(root, log_dir),
                ScanConfig(targets=[ScanTargetConfig(flow="A10", dir="station-a")], extensions=[".xlsx"]),
                LogStore(log_dir),
                upload_func=lambda parsed_file: _record_upload(parsed_file, uploaded),
                sleep_func=lambda seconds: None,
                now_func=lambda: datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )

            result = service.handle_event(
                WatchEvent("watch_created", file_path, is_dir=False, is_excel=True)
            )

            upload_lines = (log_dir / "upload_log_2026-06-14.jsonl").read_text(encoding="utf-8").splitlines()
            watch_lines = (log_dir / "watch_log_2026-06-14.jsonl").read_text(encoding="utf-8").splitlines()

        self.assertEqual(result.status, "uploaded")
        self.assertEqual(uploaded, ["report.xlsx"])
        self.assertEqual(json.loads(upload_lines[-1])["action"], "upload_success")
        self.assertEqual(json.loads(watch_lines[-1])["event_type"], "realtime_upload_success")

    def test_handle_event_skips_non_matching_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            target = root / "station-a"
            target.mkdir(parents=True)
            file_path = target / "report.txt"
            file_path.write_text("text", encoding="utf-8")
            uploaded = []
            service = RealtimeUploadService(
                _config(root, log_dir),
                ScanConfig(targets=[ScanTargetConfig(flow="A10", dir="station-a")], extensions=[".xlsx"]),
                LogStore(log_dir),
                upload_func=lambda parsed_file: _record_upload(parsed_file, uploaded),
                sleep_func=lambda seconds: None,
                now_func=lambda: datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )

            result = service.handle_event(
                WatchEvent("watch_created", file_path, is_dir=False, is_excel=False)
            )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(uploaded, [])

    def test_handle_event_uploads_today_file_even_when_daily_offset_targets_yesterday(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            target = root / "station-a" / "OUTER"
            target.mkdir(parents=True)
            file_path = target / "today.xlsx"
            file_path.write_bytes(b"excel")
            _set_mtime(file_path, "2026-06-14 10:00:00")
            uploaded = []
            service = RealtimeUploadService(
                _config(root, log_dir),
                ScanConfig(targets=[ScanTargetConfig(flow="A10", dir="station-a")], extensions=[".xlsx"]),
                LogStore(log_dir),
                upload_func=lambda parsed_file: _record_upload(parsed_file, uploaded),
                sleep_func=lambda seconds: None,
                now_func=lambda: datetime(2026, 6, 14, 11, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )

            result = service.handle_event(
                WatchEvent("watch_created", file_path, is_dir=False, is_excel=True)
            )

        self.assertEqual(result.status, "uploaded")
        self.assertEqual(uploaded, ["today.xlsx"])

    def test_wait_for_stable_file_requires_repeated_same_stat(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "report.xlsx"
            file_path.write_bytes(b"excel")

            self.assertTrue(wait_for_stable_file(file_path, attempts=2, interval_seconds=1, sleep_func=lambda seconds: None))
            self.assertFalse(wait_for_stable_file(Path(tmp_dir) / "missing.xlsx", attempts=2, interval_seconds=1))

    def test_handle_event_debounces_recently_processed_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            target = root / "station-a" / "OUTER"
            target.mkdir(parents=True)
            file_path = target / "report.xlsx"
            file_path.write_bytes(b"excel")
            _set_mtime(file_path, "2026-06-13 10:00:00")
            uploaded = []
            service = RealtimeUploadService(
                _config(root, log_dir),
                ScanConfig(targets=[ScanTargetConfig(flow="A10", dir="station-a")], extensions=[".xlsx"]),
                LogStore(log_dir),
                upload_func=lambda parsed_file: _record_upload(parsed_file, uploaded),
                sleep_func=lambda seconds: None,
                now_func=lambda: datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )
            event = WatchEvent("watch_modified", file_path, is_dir=False, is_excel=True)

            with patch("zk_impedance_upload.realtime_uploader.time.monotonic", side_effect=[10.0, 10.1, 11.0]):
                first = service.handle_event(event)
                second = service.handle_event(event)

        self.assertEqual(first.status, "uploaded")
        self.assertEqual(second.status, "skipped")
        self.assertEqual(uploaded, ["report.xlsx"])


def _config(root: Path, log_dir: Path) -> AppConfig:
    return AppConfig(
        share=ShareConfig(root=str(root), username="IT", password="FQCIT"),
        log=LogConfig(dir=str(log_dir)),
        upload=UploadConfig(url="http://example.test/upload", day_offset=1, retry_count=0),
        scan=ScanConfig(targets=[ScanTargetConfig(flow="A10", dir="station-a")]),
        watch=WatchConfig(enabled=True, stable_check_seconds=1, stable_check_attempts=2),
    )


def _record_upload(parsed_file, uploaded):
    uploaded.append(parsed_file.filename)
    return UploadResult(
        success=True,
        status_code=200,
        response={"ok": True},
        response_text='{"ok":true}',
        error="",
        retry_count=0,
    )


def _set_mtime(path: Path, timestamp: str) -> None:
    dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    import os

    os.utime(path, (dt.timestamp(), dt.timestamp()))


if __name__ == "__main__":
    unittest.main()
