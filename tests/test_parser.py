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
        path = Path(r"\\server\share\impedance\target\OUTER\file.xlsx")

        self.assertEqual(identify_region(path), "OUTER")

    def test_identifies_combined_region_from_path(self):
        path = Path(r"\\server\share\impedance\target\LXD & AFX & JXN\file.xlsx")

        self.assertEqual(identify_region(path), "LXD_AFX_JXN")

    def test_identifies_nearest_region_when_combined_directory_has_child_region(self):
        path = Path(r"\\server\share\impedance\target\LXD & AFX\ZGL\file.xlsx")

        self.assertEqual(identify_region(path), "ZGL")

    def test_returns_unknown_when_region_is_not_in_path(self):
        path = Path(r"\\server\share\impedance\unknown\file.xlsx")

        self.assertEqual(identify_region(path), "UNKNOWN")

    def test_normalizes_filename_without_changing_original_name(self):
        self.assertEqual(
            normalize_filename(" f26_impedance report(1).xlsx"),
            "F26-IMPEDANCE-REPORT",
        )

    def test_parse_candidate_generates_stable_keys_with_flow(self):
        candidate = CandidateFile(
            path=Path(r"\\server\share\impedance\target\OUTER\f26_impedance.xlsx"),
            size=123,
            modified_at=datetime(2026, 6, 13, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            flow="A10",
            filePath=r"\\server\share\impedance\target\OUTER\f26_impedance.xlsx",
        )

        parsed = parse_candidate(candidate)

        self.assertEqual(parsed.filename, "f26_impedance.xlsx")
        self.assertEqual(parsed.region, "OUTER")
        self.assertEqual(parsed.flow, "A10")
        self.assertEqual(parsed.filePath, r"\\server\share\impedance\target\OUTER\f26_impedance.xlsx")
        self.assertEqual(parsed.normalized_name, "F26-IMPEDANCE")
        self.assertEqual(parsed.business_key, "")
        self.assertEqual(parsed.fallback_key, "FALLBACK|A10|OUTER|F26-IMPEDANCE|123|2026-06-13 10:00:00")
        self.assertEqual(parsed.dedupe_key, parsed.fallback_key)

    def test_parse_candidate_keeps_configured_flow_even_when_filename_has_code(self):
        candidate = CandidateFile(
            path=Path(r"\\server\share\impedance\target\OUTER\2-AA01-6176-00_Batch_1.xlsx"),
            size=123,
            modified_at=datetime(2026, 7, 5, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            flow="A557",
            filePath=r"\\server\share\impedance\target\OUTER\2-AA01-6176-00_Batch_1.xlsx",
        )

        parsed = parse_candidate(candidate)

        self.assertEqual(parsed.region, "OUTER")
        self.assertEqual(parsed.flow, "A557")
        self.assertEqual(
            parsed.fallback_key,
            "FALLBACK|A557|OUTER|2-AA01-6176-00-BATCH-1|123|2026-07-05 10:00:00",
        )

    def test_parse_candidate_uses_file_path_in_fallback_key_when_flow_is_blank(self):
        file_path = r"\\server\share\impedance\target\OUTER\2-AA01-6176-00_Batch_1.xlsx"
        candidate = CandidateFile(
            path=Path(file_path),
            size=123,
            modified_at=datetime(2026, 7, 5, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            flow="",
            filePath=file_path,
        )

        parsed = parse_candidate(candidate)

        self.assertEqual(parsed.flow, "")
        self.assertEqual(
            parsed.fallback_key,
            f"FALLBACK|{file_path}|OUTER|2-AA01-6176-00-BATCH-1|123|2026-07-05 10:00:00",
        )


if __name__ == "__main__":
    unittest.main()
