from pathlib import Path
import unittest

from zk_impedance_upload.parser import ParsedFile
from zk_impedance_upload.upload_task_store import InMemoryUploadTaskStore


class UploadTaskStoreTest(unittest.TestCase):
    def test_in_memory_store_enqueues_claims_and_marks_success(self):
        store = InMemoryUploadTaskStore()
        parsed_file = _parsed_file("report.xlsx")

        first = store.enqueue_pending(parsed_file, run_id="ZK-RT-1")
        duplicate = store.enqueue_pending(parsed_file, run_id="ZK-RT-2")
        task = store.claim_pending()

        self.assertTrue(first.queued)
        self.assertEqual(first.task_id, 1)
        self.assertFalse(duplicate.queued)
        self.assertIsNotNone(task)
        self.assertEqual(task.filename, "report.xlsx")

        store.mark_success(task.id, response={"ok": True}, http_status=200, retry_count=0)
        records = store.list_records()

        self.assertEqual(records[0]["status"], "success")
        self.assertEqual(records[0]["response"], {"ok": True})
        self.assertIsNone(store.claim_pending())


def _parsed_file(filename: str) -> ParsedFile:
    path = Path(r"\\server\share\station-a") / filename
    return ParsedFile(
        path=path,
        filename=filename,
        directory=path.parent,
        size=10,
        modified_at="2026-07-17 08:00:00",
        flow="A10",
        filePath=str(path),
        region="OUTER",
        normalized_name="REPORT",
        business_key="",
        fallback_key=f"FALLBACK|A10|OUTER|REPORT|10|2026-07-17 08:00:00",
        dedupe_key=f"FALLBACK|A10|OUTER|REPORT|10|2026-07-17 08:00:00",
    )


if __name__ == "__main__":
    unittest.main()
