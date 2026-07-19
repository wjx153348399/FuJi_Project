import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Optional
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
from zk_impedance_upload.exceptions import ConfigError
from zk_impedance_upload.runner import run_upload_task
from zk_impedance_upload.uploader import UploadResult


class RunnerTest(unittest.TestCase):
    def test_run_upload_task_uploads_candidate_and_writes_logs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            target_dir = root / "target" / "OUTER"
            target_dir.mkdir(parents=True)
            file_path = target_dir / "example.xlsx"
            file_path.write_bytes(b"excel")
            _set_mtime(file_path, "2026-06-13 10:00:00")
            uploaded_files = []

            def fake_upload(parsed_file):
                uploaded_files.append(parsed_file.filename)
                return UploadResult(
                    success=True,
                    status_code=200,
                    response={"ok": True},
                    response_text='{"ok":true}',
                    error="",
                    retry_count=0,
                )

            result = run_upload_task(
                config=_config(root, log_dir),
                now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                upload_func=fake_upload,
            )

            upload_log = (log_dir / "upload_log_2026-06-14.jsonl").read_text(encoding="utf-8").splitlines()
            history = json.loads((log_dir / "uploaded_file_fingerprints.json").read_text(encoding="utf-8"))
            summaries = list(log_dir.glob("summary_*.json"))

        self.assertEqual(uploaded_files, ["example.xlsx"])
        self.assertEqual(result.stats["candidate_count"], 1)
        self.assertEqual(result.stats["success_count"], 1)
        self.assertEqual(result.stats["fail_count"], 0)
        self.assertEqual(result.stats["skip_count"], 0)
        self.assertEqual(json.loads(upload_log[0])["action"], "upload_success")
        self.assertEqual(len(history), 1)
        self.assertNotIn("file_hash", next(iter(history.values())))
        self.assertEqual(len(summaries), 1)

    def test_dry_run_does_not_upload_or_write_success_history(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            target_dir = root / "target" / "OUTER"
            target_dir.mkdir(parents=True)
            file_path = target_dir / "example.xlsx"
            file_path.write_bytes(b"excel")
            _set_mtime(file_path, "2026-06-13 10:00:00")
            uploaded_files = []

            result = run_upload_task(
                config=_config(root, log_dir, dry_run=True),
                now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                upload_func=lambda parsed_file: uploaded_files.append(parsed_file.filename),
            )

            upload_log = (log_dir / "upload_log_2026-06-14.jsonl").read_text(encoding="utf-8").splitlines()
            history_path = log_dir / "uploaded_file_fingerprints.json"

        self.assertEqual(uploaded_files, [])
        self.assertEqual(result.stats["pending_count"], 1)
        self.assertEqual(json.loads(upload_log[0])["action"], "dry_run_pending")
        self.assertFalse(history_path.exists())

    def test_history_uploaded_file_is_skipped_without_uploading_again(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            target_dir = root / "target" / "OUTER"
            target_dir.mkdir(parents=True)
            file_path = target_dir / "example.xlsx"
            file_path.write_bytes(b"excel")
            _set_mtime(file_path, "2026-06-13 10:00:00")

            config = _config(root, log_dir)
            now = datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            run_upload_task(config=config, now=now, upload_func=_success_upload)
            second_uploads = []
            result = run_upload_task(
                config=config,
                now=now,
                upload_func=lambda parsed_file: second_uploads.append(parsed_file.filename),
            )

        self.assertEqual(second_uploads, [])
        self.assertEqual(result.stats["success_count"], 0)
        self.assertEqual(result.stats["skip_count"], 1)

    def test_max_upload_files_limits_real_upload_count(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            target_dir = root / "target" / "OUTER"
            target_dir.mkdir(parents=True)
            first = target_dir / "first.xlsx"
            second = target_dir / "second.xlsx"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            _set_mtime(first, "2026-06-13 10:00:00")
            _set_mtime(second, "2026-06-13 10:01:00")
            uploaded_files = []

            result = run_upload_task(
                config=_config(root, log_dir, max_upload_files=1),
                now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                upload_func=lambda parsed_file: _recording_success_upload(parsed_file, uploaded_files),
            )

            upload_log = (log_dir / "upload_log_2026-06-14.jsonl").read_text(encoding="utf-8").splitlines()
            actions = [json.loads(line)["action"] for line in upload_log]

        self.assertEqual(uploaded_files, ["first.xlsx"])
        self.assertEqual(result.stats["success_count"], 1)
        self.assertEqual(result.stats["skip_count"], 1)
        self.assertIn("upload_limit_skipped", actions)

    def test_run_upload_task_generates_watch_summary_for_target_day(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            target_dir = root / "target" / "OUTER"
            target_dir.mkdir(parents=True)
            file_path = target_dir / "example.xlsx"
            file_path.write_bytes(b"excel")
            _set_mtime(file_path, "2026-06-13 10:00:00")
            log_dir.mkdir(parents=True)
            (log_dir / "watch_log_2026-06-13.jsonl").write_text(
                json.dumps(
                    {
                        "event_type": "watch_created",
                        "path": str(file_path),
                        "previous_path": None,
                        "is_dir": False,
                        "is_excel": True,
                        "log_time": "2026-06-13 09:00:00",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            run_upload_task(
                config=_config(root, log_dir, watch_enabled=True),
                now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                upload_func=_success_upload,
            )

            watch_summary = json.loads(
                (log_dir / "watch_summary_2026-06-14_08-00-00.json").read_text(encoding="utf-8")
            )

        self.assertEqual(watch_summary["event_date"], "2026-06-13")
        self.assertEqual(watch_summary["stats"]["watch_created"], 1)
        self.assertEqual(watch_summary["stats"]["excel_event_count"], 1)

    def test_run_upload_task_ensures_share_access_before_logs_and_scan(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            root.mkdir()
            calls = []

            run_upload_task(
                config=_config(root, log_dir, dry_run=True),
                now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                upload_func=_success_upload,
                share_access_func=lambda config: calls.append((config.share.root, config.log.dir)),
            )

        self.assertEqual(len(calls), 1)

    def test_run_upload_task_reports_progress_messages(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            target_dir = root / "target" / "OUTER"
            target_dir.mkdir(parents=True)
            file_path = target_dir / "example.xlsx"
            file_path.write_bytes(b"excel")
            _set_mtime(file_path, "2026-06-13 10:00:00")
            messages = []

            run_upload_task(
                config=_config(root, log_dir),
                now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                upload_func=_success_upload,
                progress_func=messages.append,
            )

        joined = "\n".join(messages)
        self.assertIn("start upload task", joined)
        self.assertIn("scanning share files", joined)
        self.assertIn("uploading 1/1", joined)
        self.assertIn("upload task summary", joined)

    def test_run_upload_task_writes_flow_and_file_path_to_logs_and_history(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            target_dir = root / "station-a" / "OUTER"
            target_dir.mkdir(parents=True)
            file_path = target_dir / "example.xlsx"
            file_path.write_bytes(b"excel")
            _set_mtime(file_path, "2026-06-13 10:00:00")

            run_upload_task(
                config=_config(root, log_dir, targets=[ScanTargetConfig(flow="A010", dir="station-a")]),
                now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                upload_func=_success_upload,
            )

            upload_entry = json.loads((log_dir / "upload_log_2026-06-14.jsonl").read_text(encoding="utf-8"))
            history = json.loads((log_dir / "uploaded_file_fingerprints.json").read_text(encoding="utf-8"))
            history_entry = next(iter(history.values()))

        self.assertEqual(upload_entry["flow"], "A010")
        self.assertEqual(upload_entry["filePath"], str(file_path))
        self.assertEqual(history_entry["flow"], "A010")
        self.assertEqual(history_entry["filePath"], str(file_path))
        self.assertTrue(history_entry["fallback_key"].startswith("FALLBACK|A010|"))

    def test_real_upload_function_receives_flow_and_file_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            target_dir = root / "station-a" / "OUTER"
            target_dir.mkdir(parents=True)
            file_path = target_dir / "example.xlsx"
            file_path.write_bytes(b"excel")
            _set_mtime(file_path, "2026-06-13 10:00:00")
            upload_calls = []

            def fake_upload_file(**kwargs):
                upload_calls.append(kwargs)
                return UploadResult(
                    success=True,
                    status_code=200,
                    response={"ok": True},
                    response_text='{"ok":true}',
                    error="",
                    retry_count=0,
                )

            with patch("zk_impedance_upload.runner.upload_file", side_effect=fake_upload_file):
                run_upload_task(
                    config=_config(
                        root,
                        log_dir,
                        targets=[ScanTargetConfig(flow="A010", dir="station-a")],
                    ),
                    now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                )

            upload_entry = json.loads((log_dir / "upload_log_2026-06-14.jsonl").read_text(encoding="utf-8"))

        self.assertEqual(upload_calls[0]["flow"], "A010")
        self.assertEqual(upload_calls[0]["filePath"], str(file_path))
        self.assertEqual(upload_entry["flow"], "A010")
        self.assertEqual(upload_entry["filePath"], str(file_path))

    def test_real_upload_function_rejects_blank_flow(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            target_dir = root / "station-a" / "OUTER"
            target_dir.mkdir(parents=True)
            file_path = target_dir / "example.xlsx"
            file_path.write_bytes(b"excel")
            _set_mtime(file_path, "2026-06-13 10:00:00")
            upload_calls = []

            def fake_upload_file(**kwargs):
                upload_calls.append(kwargs)
                return UploadResult(
                    success=True,
                    status_code=200,
                    response={"ok": True},
                    response_text='{"ok":true}',
                    error="",
                    retry_count=0,
                )

            with patch("zk_impedance_upload.runner.upload_file", side_effect=fake_upload_file):
                with self.assertRaisesRegex(ConfigError, "flow is required"):
                    run_upload_task(
                        config=_config(
                            root,
                            log_dir,
                            targets=[ScanTargetConfig(flow="", dir="station-a")],
                        ),
                        now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                    )

        self.assertEqual(upload_calls, [])

    def test_run_upload_task_rejects_blank_flow_in_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "share"
            log_dir = Path(tmp_dir) / "logs"
            target_dir = root / "station-a" / "OUTER"
            target_dir.mkdir(parents=True)
            file_path = target_dir / "example.xlsx"
            file_path.write_bytes(b"excel")
            _set_mtime(file_path, "2026-06-13 10:00:00")

            with self.assertRaisesRegex(ConfigError, "flow is required"):
                run_upload_task(
                    config=_config(
                        root,
                        log_dir,
                        targets=[ScanTargetConfig(flow="", dir="station-a")],
                        dry_run=True,
                    ),
                    now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                )


def _config(
    root: Path,
    log_dir: Path,
    dry_run: bool = False,
    watch_enabled: bool = False,
    max_upload_files: Optional[int] = None,
    targets: Optional[list[ScanTargetConfig]] = None,
) -> AppConfig:
    return AppConfig(
        share=ShareConfig(root=str(root), username="IT", password="FQCIT"),
        log=LogConfig(dir=str(log_dir)),
        upload=UploadConfig(
            url="http://example.test/upload",
            day_offset=1,
            max_upload_files=max_upload_files,
            dry_run=dry_run,
            timeout_seconds=60,
            retry_count=0,
        ),
        scan=ScanConfig(
            target_dirs=["target"],
            targets=targets,
            extensions=[".xlsx"],
            exclude_prefixes=["~$"],
            exclude_dirs=[],
        ),
        watch=WatchConfig(enabled=watch_enabled),
    )


def _success_upload(parsed_file):
    return UploadResult(
        success=True,
        status_code=200,
        response={"ok": True},
        response_text='{"ok":true}',
        error="",
        retry_count=0,
    )


def _recording_success_upload(parsed_file, uploaded_files):
    uploaded_files.append(parsed_file.filename)
    return _success_upload(parsed_file)


def _set_mtime(path: Path, timestamp: str) -> None:
    dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    import os

    os.utime(path, (dt.timestamp(), dt.timestamp()))


if __name__ == "__main__":
    unittest.main()
