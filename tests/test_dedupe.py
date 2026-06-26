import tempfile
import unittest
from pathlib import Path

from zk_impedance_upload.dedupe import dedupe_batch
from zk_impedance_upload.parser import ParsedFile


class FakeHashCache:
    def __init__(self, values=None):
        self.values = values or {}
        self.calls = []

    def get(self, path):
        self.calls.append(Path(path).name)
        return self.values.get(Path(path).name, "hash")


class ExplodingHashCache:
    def get(self, path):
        raise AssertionError("hash should not be calculated for non-duplicate groups")


class DedupeTest(unittest.TestCase):
    def test_unique_files_do_not_calculate_hash(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            first_path = Path(tmp_dir) / "first.xlsx"
            second_path = Path(tmp_dir) / "second.xlsx"
            first_path.write_bytes(b"first")
            second_path.write_bytes(b"second")
            first = _parsed_file(first_path, normalized_name="FIRST", modified_at="2026-06-13 10:00:00")
            second = _parsed_file(second_path, normalized_name="SECOND", modified_at="2026-06-13 10:00:00")

            result = dedupe_batch([first, second], ExplodingHashCache())

        self.assertEqual([item.filename for item in result.selected], ["first.xlsx", "second.xlsx"])
        self.assertEqual(result.skipped, [])

    def test_hashes_only_suspected_duplicate_group_and_skips_same_hash(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            first_path = Path(tmp_dir) / "first.xlsx"
            second_path = Path(tmp_dir) / "second.xlsx"
            first_path.write_bytes(b"same")
            second_path.write_bytes(b"same")
            first = _parsed_file(first_path, normalized_name="SAME", modified_at="2026-06-13 10:00:00")
            second = _parsed_file(second_path, normalized_name="SAME", modified_at="2026-06-13 10:00:00")
            hash_cache = FakeHashCache({"first.xlsx": "same-hash", "second.xlsx": "same-hash"})

            result = dedupe_batch([first, second], hash_cache)

        self.assertEqual(len(result.selected), 1)
        self.assertEqual(result.selected[0].filename, "first.xlsx")
        self.assertEqual([item.parsed_file.filename for item in result.skipped], ["second.xlsx"])
        self.assertEqual(result.skipped[0].action, "batch_duplicate_skipped")
        self.assertEqual(hash_cache.calls, ["first.xlsx", "second.xlsx"])

    def test_keeps_all_suspected_duplicates_when_hash_is_different(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            first_path = Path(tmp_dir) / "first.xlsx"
            second_path = Path(tmp_dir) / "second.xlsx"
            first_path.write_bytes(b"first")
            second_path.write_bytes(b"second")
            first = _parsed_file(first_path, normalized_name="SAME", modified_at="2026-06-13 10:00:00")
            second = _parsed_file(second_path, normalized_name="SAME", modified_at="2026-06-13 10:00:00")
            hash_cache = FakeHashCache({"first.xlsx": "hash-1", "second.xlsx": "hash-2"})

            result = dedupe_batch([first, second], hash_cache)

        self.assertEqual([item.filename for item in result.selected], ["first.xlsx", "second.xlsx"])
        self.assertEqual(result.skipped, [])

    def test_different_mtime_is_not_suspected_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            old_path = Path(tmp_dir) / "old.xlsx"
            new_path = Path(tmp_dir) / "new.xlsx"
            old_path.write_bytes(b"same")
            new_path.write_bytes(b"same")
            old = _parsed_file(old_path, normalized_name="SAME", modified_at="2026-06-13 09:00:00")
            new = _parsed_file(new_path, normalized_name="SAME", modified_at="2026-06-13 10:00:00")

            result = dedupe_batch([old, new], ExplodingHashCache())

        self.assertEqual([item.filename for item in result.selected], ["old.xlsx", "new.xlsx"])
        self.assertEqual(result.skipped, [])


def _parsed_file(path: Path, normalized_name: str, modified_at: str) -> ParsedFile:
    size = path.stat().st_size
    fallback_key = f"FALLBACK|A10|OUTER|{normalized_name}|{size}|{modified_at}"
    return ParsedFile(
        path=path,
        filename=path.name,
        directory=path.parent,
        size=size,
        modified_at=modified_at,
        station_code="A10",
        source_dir="target",
        region="OUTER",
        normalized_name=normalized_name,
        business_key="",
        fallback_key=fallback_key,
        dedupe_key=fallback_key,
    )


if __name__ == "__main__":
    unittest.main()
