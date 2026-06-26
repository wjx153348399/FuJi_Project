import json
import tempfile
import unittest
from pathlib import Path

from zk_impedance_upload.exceptions import LogError
from zk_impedance_upload.log_store import LogStore


class LogStoreTest(unittest.TestCase):
    def test_appends_upload_log_as_utf8_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = LogStore(tmp_dir)
            entry = {
                "filename": "阻抗.xlsx",
                "full_path": "\\\\10.0.8.252\\ProductionFieldFile 现场公共盘\\阻抗\\阻抗.xlsx",
                "status": "scan",
            }

            log_path = store.append_upload_log("2026-06-14", entry)

            lines = log_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(log_path.name, "upload_log_2026-06-14.jsonl")
        self.assertEqual(json.loads(lines[0]), entry)

    def test_writes_summary_json_with_stable_name(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = LogStore(tmp_dir)
            summary = {
                "run_id": "ZK-20260614-080000",
                "run_time": "2026-06-14 08:00:00",
                "target_day": "2026-06-13",
                "stats": {"task_status": "completed"},
            }

            summary_path = store.write_summary("2026-06-14_08-00-00", summary)
            saved = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(summary_path.name, "summary_2026-06-14_08-00-00.json")
        self.assertEqual(saved["run_id"], "ZK-20260614-080000")

    def test_appends_watch_log_as_utf8_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = LogStore(tmp_dir)
            entry = {
                "event_type": "watch_created",
                "path": "\\\\10.0.8.252\\ProductionFieldFile 现场公共盘\\阻抗\\AFX\\阻抗.xlsx",
                "is_excel": True,
            }

            log_path = store.append_watch_log("2026-06-14", entry)
            lines = log_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(log_path.name, "watch_log_2026-06-14.jsonl")
        self.assertEqual(json.loads(lines[0]), entry)

    def test_writes_watch_summary_json_with_stable_name(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = LogStore(tmp_dir)
            summary = {
                "summary_type": "watch_daily",
                "event_date": "2026-06-14",
                "stats": {"watch_created": 2, "watch_modified": 1},
            }

            summary_path = store.write_watch_summary("2026-06-14_08-00-00", summary)
            saved = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(summary_path.name, "watch_summary_2026-06-14_08-00-00.json")
        self.assertEqual(saved["summary_type"], "watch_daily")

    def test_reads_and_updates_uploaded_fingerprints(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = LogStore(tmp_dir)
            record = {
                "filename": "example.xlsx",
                "file_hash": "abc123",
                "uploaded_at": "2026-06-14 08:01:00",
            }

            store.save_uploaded_fingerprint("FALLBACK|OUTER|EXAMPLE|abc123", record)
            fingerprints = store.load_uploaded_fingerprints()

        self.assertEqual(fingerprints["FALLBACK|OUTER|EXAMPLE|abc123"], record)

    def test_reads_and_updates_uploaded_business_keys(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = LogStore(tmp_dir)
            record = {
                "filename": "example.xlsx",
                "business_key": "OUTER|品名|F26-001",
                "uploaded_at": "2026-06-14 08:01:00",
            }

            store.save_uploaded_business_key("OUTER|品名|F26-001", record)
            business_keys = store.load_uploaded_business_keys()

        self.assertEqual(business_keys["OUTER|品名|F26-001"], record)

    def test_rejects_file_path_as_log_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "not-a-dir"
            file_path.write_text("x", encoding="utf-8")

            with self.assertRaisesRegex(LogError, "日志路径不是目录"):
                LogStore(file_path).ensure_ready()


if __name__ == "__main__":
    unittest.main()
