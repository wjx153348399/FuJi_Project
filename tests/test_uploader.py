import tempfile
import unittest
from pathlib import Path

from requests import RequestException

from zk_impedance_upload.uploader import UploadResult, upload_file


class FakeResponse:
    def __init__(self, status_code=200, text='{"ok":true}', json_data=None):
        self.status_code = status_code
        self.text = text
        self.json_data = json_data

    def json(self):
        if self.json_data is not None:
            return self.json_data
        return {"ok": True}


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def post(self, url, files, data=None, timeout=None):
        file_name, file_obj = files["file"]
        self.calls.append(
            {
                "url": url,
                "file_name": file_name,
                "file_bytes": file_obj.read(),
                "data": data or {},
                "timeout": timeout,
            }
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class UploaderTest(unittest.TestCase):
    def test_uploads_file_as_multipart_form_data(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "阻抗.xlsx"
            file_path.write_bytes(b"excel")
            session = FakeSession([FakeResponse(200, '{"ok":true}')])

            result = upload_file(
                file_path=file_path,
                url="http://example.test/upload",
                timeout_seconds=60,
                retry_count=0,
                station_code="A10",
                session=session,
            )

        self.assertTrue(result.success)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.response, {"ok": True})
        self.assertEqual(result.retry_count, 0)
        self.assertEqual(session.calls[0]["file_name"], "阻抗.xlsx")
        self.assertEqual(session.calls[0]["file_bytes"], b"excel")
        self.assertEqual(session.calls[0]["data"], {"station_code": "A10"})
        self.assertEqual(session.calls[0]["timeout"], 60)

    def test_retries_request_exception_then_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "example.xlsx"
            file_path.write_bytes(b"excel")
            session = FakeSession([RequestException("timeout"), FakeResponse(200)])

            result = upload_file(
                file_path=file_path,
                url="http://example.test/upload",
                timeout_seconds=30,
                retry_count=1,
                session=session,
            )

        self.assertTrue(result.success)
        self.assertEqual(result.retry_count, 1)
        self.assertEqual(len(session.calls), 2)

    def test_returns_failure_for_non_success_status(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "example.xlsx"
            file_path.write_bytes(b"excel")
            session = FakeSession([FakeResponse(500, "server error")])

            result = upload_file(
                file_path=file_path,
                url="http://example.test/upload",
                timeout_seconds=30,
                retry_count=0,
                session=session,
            )

        self.assertFalse(result.success)
        self.assertEqual(result.status_code, 500)
        self.assertEqual(result.response_text, "server error")
        self.assertIn("HTTP 500", result.error)

    def test_returns_failure_for_success_status_with_business_failure(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "example.xlsx"
            file_path.write_bytes(b"excel")
            session = FakeSession(
                [
                    FakeResponse(
                        200,
                        '{"success":false,"message":"parse failed"}',
                        {"success": False, "message": "parse failed"},
                    )
                ]
            )

            result = upload_file(
                file_path=file_path,
                url="http://example.test/upload",
                timeout_seconds=30,
                retry_count=0,
                session=session,
            )

        self.assertFalse(result.success)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.response["success"], False)
        self.assertIn("parse failed", result.error)

    def test_returns_failure_after_retries_are_exhausted(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "example.xlsx"
            file_path.write_bytes(b"excel")
            session = FakeSession([RequestException("down"), RequestException("still down")])

            result = upload_file(
                file_path=file_path,
                url="http://example.test/upload",
                timeout_seconds=30,
                retry_count=1,
                session=session,
            )

        self.assertFalse(result.success)
        self.assertIsNone(result.status_code)
        self.assertEqual(result.retry_count, 1)
        self.assertIn("still down", result.error)

    def test_upload_result_has_serializable_defaults(self):
        result = UploadResult(success=False, status_code=None, response={}, response_text="", error="failed", retry_count=0)

        self.assertEqual(result.response, {})


if __name__ == "__main__":
    unittest.main()
