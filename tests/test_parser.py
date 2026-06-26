import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from zk_impedance_upload.parser import (
    identify_region,
    normalize_filename,
    parse_candidate,
)
from zk_impedance_upload.scanner import CandidateFile


class ParserTest(unittest.TestCase):
    def test_identifies_direct_region_from_path(self):
        path = Path(r"\\server\share\阻抗\ผลิตภัณฑ์สำเร็จรูปCP-阻抗\OUTER\file.xlsx")

        self.assertEqual(identify_region(path), "OUTER")

    def test_identifies_combined_region_from_path(self):
        path = Path(r"\\server\share\阻抗\ผลิตภัณฑ์สำเร็จรูปCP-阻抗\LXD & AFX & JXN\file.xlsx")

        self.assertEqual(identify_region(path), "LXD_AFX_JXN")

    def test_identifies_nearest_region_when_combined_directory_has_child_region(self):
        path = Path(r"\\server\share\阻抗\ผลิตภัณฑ์กึ่งสำเร็จรูป图形后(半成品)\LXD & AFX\ZGL\file.xlsx")

        self.assertEqual(identify_region(path), "ZGL")

    def test_returns_unknown_when_region_is_not_in_path(self):
        path = Path(r"\\server\share\阻抗\unknown\file.xlsx")

        self.assertEqual(identify_region(path), "UNKNOWN")

    def test_normalizes_filename_without_changing_original_name(self):
        self.assertEqual(
            normalize_filename(" f26_阻抗 报表（1） (1).xlsx"),
            "F26-阻抗-报表(1)",
        )

    def test_parse_candidate_generates_stable_keys(self):
        candidate = CandidateFile(
            path=Path(r"\\server\share\阻抗\ผลิตภัณฑ์สำเร็จรูปCP-阻抗\OUTER\f26_阻抗.xlsx"),
            size=123,
            modified_at=datetime(2026, 6, 13, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        parsed = parse_candidate(candidate)

        self.assertEqual(parsed.filename, "f26_阻抗.xlsx")
        self.assertEqual(parsed.region, "OUTER")
        self.assertEqual(parsed.normalized_name, "F26-阻抗")
        self.assertEqual(parsed.business_key, "")
        self.assertEqual(parsed.fallback_key, "FALLBACK|OUTER|F26-阻抗|123|2026-06-13 10:00:00")
        self.assertEqual(parsed.dedupe_key, parsed.fallback_key)


if __name__ == "__main__":
    unittest.main()
