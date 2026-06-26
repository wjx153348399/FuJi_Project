import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from zk_impedance_upload.config import ScanConfig
from zk_impedance_upload.date_window import build_date_window
from zk_impedance_upload.scanner import ScanResult, scan_files


class ScannerTest(unittest.TestCase):
    def test_scans_target_dirs_and_filters_excel_files_by_date_window(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target_dir = root / "ผลิตภัณฑ์สำเร็จรูปCP-阻抗"
            nested_dir = target_dir / "OUTER"
            nested_dir.mkdir(parents=True)
            valid_file = nested_dir / "阻抗报表.XLSX"
            today_file = nested_dir / "今天.xlsx"
            text_file = nested_dir / "note.txt"
            temp_excel = nested_dir / "~$临时.xlsx"
            for file_path in [valid_file, today_file, text_file, temp_excel]:
                file_path.write_text("x", encoding="utf-8")
            _set_mtime(valid_file, "2026-06-13 10:00:00")
            _set_mtime(today_file, "2026-06-14 10:00:00")
            _set_mtime(text_file, "2026-06-13 10:00:00")
            _set_mtime(temp_excel, "2026-06-13 10:00:00")

            window = build_date_window(
                now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                day_offset=1,
            )
            result = scan_files(
                root=root,
                scan_config=ScanConfig(
                    target_dirs=["ผลิตภัณฑ์สำเร็จรูปCP-阻抗"],
                    extensions=[".xls", ".xlsx"],
                    exclude_prefixes=["~$"],
                    exclude_dirs=["LOG", "log", "日志", "备份", "backup"],
                    recursive=True,
                ),
                date_window=window,
            )

        self.assertEqual([item.path.name for item in result.candidates], ["阻抗报表.XLSX"])
        self.assertEqual(result.missing_dirs, [])
        self.assertEqual(result.failed_dirs, [])

    def test_skips_excluded_directories(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target_dir = root / "ผลิตภัณฑ์กึ่งสำเร็จรูป图形后(半成品)"
            log_dir = target_dir / "LOG"
            log_dir.mkdir(parents=True)
            skipped_file = log_dir / "should_skip.xlsx"
            skipped_file.write_text("x", encoding="utf-8")
            _set_mtime(skipped_file, "2026-06-13 10:00:00")

            result = scan_files(
                root=root,
                scan_config=ScanConfig(
                    target_dirs=["ผลิตภัณฑ์กึ่งสำเร็จรูป图形后(半成品)"],
                    exclude_dirs=["LOG"],
                    recursive=True,
                ),
                date_window=build_date_window(
                    now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
                ),
            )

        self.assertEqual(result.candidates, [])

    def test_records_missing_target_directories(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = scan_files(
                root=Path(tmp_dir),
                scan_config=ScanConfig(target_dirs=["missing-dir"]),
                date_window=build_date_window(
                    now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
                ),
            )

        self.assertEqual(len(result.missing_dirs), 1)
        self.assertEqual(result.missing_dirs[0].name, "missing-dir")

    def test_non_recursive_scan_does_not_enter_child_directories(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target_dir = root / "target"
            child_dir = target_dir / "child"
            child_dir.mkdir(parents=True)
            nested_file = child_dir / "nested.xlsx"
            nested_file.write_text("x", encoding="utf-8")
            _set_mtime(nested_file, "2026-06-13 10:00:00")

            result = scan_files(
                root=root,
                scan_config=ScanConfig(target_dirs=["target"], recursive=False),
                date_window=build_date_window(
                    now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
                ),
            )

        self.assertEqual(result.candidates, [])

    def test_scan_result_has_clear_default_lists(self):
        result = ScanResult()

        self.assertEqual(result.candidates, [])
        self.assertEqual(result.missing_dirs, [])
        self.assertEqual(result.failed_dirs, [])


def _set_mtime(path: Path, timestamp: str) -> None:
    dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    epoch_seconds = dt.timestamp()
    path.touch()
    import os

    os.utime(path, (epoch_seconds, epoch_seconds))


if __name__ == "__main__":
    unittest.main()
