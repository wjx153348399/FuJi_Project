import tempfile
import unittest
from pathlib import Path

from zk_impedance_upload.fingerprint import (
    build_upload_record,
    calculate_sha256,
    has_uploaded_success,
    split_history_uploaded,
)
from zk_impedance_upload.parser import ParsedFile


class FingerprintTest(unittest.TestCase):
    def test_calculates_file_sha256(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "example.xlsx"
            file_path.write_bytes(b"abc")

            file_hash = calculate_sha256(file_path)

        self.assertEqual(file_hash, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_builds_uploaded_record_from_parsed_file_and_hash(self):
        parsed = _parsed_file(Path("example.xlsx"), "EXAMPLE", 123)

        record = build_upload_record(
            parsed_file=parsed,
            file_hash="abc123",
            run_id="ZK-20260614-080000",
            uploaded_at="2026-06-14 08:01:00",
            response={"code": 200},
        )

        self.assertEqual(record["filename"], "example.xlsx")
        self.assertEqual(record["file_hash"], "abc123")
        self.assertEqual(record["fallback_key"], parsed.fallback_key)
        self.assertEqual(record["uploaded_at"], "2026-06-14 08:01:00")
        self.assertEqual(record["response"], {"code": 200})

    def test_builds_uploaded_record_without_hash_when_not_calculated(self):
        parsed = _parsed_file(Path("example.xlsx"), "EXAMPLE", 123)

        record = build_upload_record(
            parsed_file=parsed,
            file_hash=None,
            run_id="ZK-20260614-080000",
            uploaded_at="2026-06-14 08:01:00",
            response={"code": 200},
        )

        self.assertNotIn("file_hash", record)

    def test_detects_uploaded_success_by_fallback_key_without_hash(self):
        parsed = _parsed_file(Path("example.xlsx"), "EXAMPLE", 123)
        history = {
            parsed.fallback_key: {
                "filename": "example.xlsx",
            }
        }

        self.assertTrue(has_uploaded_success(parsed, history))

    def test_missing_history_entry_is_not_uploaded(self):
        parsed = _parsed_file(Path("example.xlsx"), "EXAMPLE", 123)

        self.assertFalse(has_uploaded_success(parsed, {}))

    def test_splits_pending_and_history_uploaded_files_without_hashing(self):
        uploaded = _parsed_file(Path("uploaded.xlsx"), "UPLOADED", 123)
        pending = _parsed_file(Path("pending.xlsx"), "PENDING", 456)
        history = {
            uploaded.fallback_key: {
                "filename": uploaded.filename,
            }
        }

        result = split_history_uploaded([uploaded, pending], history)

        self.assertEqual([item.filename for item in result.pending], ["pending.xlsx"])
        self.assertEqual([item.parsed_file.filename for item in result.skipped], ["uploaded.xlsx"])
        self.assertEqual(result.skipped[0].action, "history_uploaded_skipped")
        self.assertIsNone(result.skipped[0].file_hash)


def _parsed_file(path: Path, normalized_name: str, size: int) -> ParsedFile:
    fallback_key = f"FALLBACK|OUTER|{normalized_name}|{size}|2026-06-13 10:00:00"
    return ParsedFile(
        path=path,
        filename=path.name,
        directory=path.parent,
        size=size,
        modified_at="2026-06-13 10:00:00",
        region="OUTER",
        normalized_name=normalized_name,
        business_key="",
        fallback_key=fallback_key,
        dedupe_key=fallback_key,
    )


if __name__ == "__main__":
    unittest.main()
