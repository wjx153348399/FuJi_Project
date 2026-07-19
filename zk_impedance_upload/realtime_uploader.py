from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import threading
import time
from typing import TYPE_CHECKING, Callable

from zk_impedance_upload.config import AppConfig, ScanConfig
from zk_impedance_upload.date_window import SHANGHAI_TZ
from zk_impedance_upload.fingerprint import build_upload_record, split_history_uploaded
from zk_impedance_upload.log_store import LogStore
from zk_impedance_upload.parser import ParsedFile, parse_candidate
from zk_impedance_upload.scanner import CandidateFile, build_candidate_for_path
from zk_impedance_upload.upload_task_store import (
    UploadTaskStore,
    create_upload_task_store,
    parsed_file_from_task,
)
from zk_impedance_upload.uploader import UploadResult, upload_file

if TYPE_CHECKING:
    from zk_impedance_upload.watcher import WatchEvent


UploadFunc = Callable[[ParsedFile], UploadResult]
ProgressFunc = Callable[[str], None]
SleepFunc = Callable[[float], None]
NowFunc = Callable[[], datetime]


@dataclass(frozen=True)
class RealtimeUploadResult:
    status: str
    path: str
    message: str = ""
    stats: dict[str, int] = field(default_factory=dict)


class RealtimeUploadService:
    def __init__(
        self,
        config: AppConfig,
        scan_config: ScanConfig,
        log_store: LogStore,
        *,
        upload_func: UploadFunc | None = None,
        task_store: UploadTaskStore | None = None,
        sleep_func: SleepFunc | None = None,
        now_func: NowFunc | None = None,
        progress_func: ProgressFunc | None = None,
    ) -> None:
        self.config = config
        self.scan_config = scan_config
        self.log_store = log_store
        self.upload_func = upload_func or _real_upload_func(config)
        self.task_store = task_store or create_upload_task_store(config)
        self.sleep = sleep_func or time.sleep
        self.now = now_func or _current_time
        self.progress = progress_func or _no_progress
        self._in_progress: set[str] = set()
        self._last_handled: dict[str, float] = {}
        self._worker_stop = threading.Event()
        self._worker_thread: threading.Thread | None = None

    def handle_event(self, event: "WatchEvent") -> RealtimeUploadResult:
        if event.is_dir:
            return RealtimeUploadResult(status="skipped", path=str(event.path), message="directory event")
        if event.event_type not in {"watch_created", "watch_modified", "watch_renamed"}:
            return RealtimeUploadResult(status="skipped", path=str(event.path), message="event does not trigger upload")

        key = _normalize_key(event.path)
        current_monotonic = time.monotonic()
        last_handled = self._last_handled.get(key)
        if last_handled is not None and current_monotonic - last_handled < self.config.watch.debounce_seconds:
            self._write_watch_entry("realtime_skipped", event.path, "file event debounced")
            return RealtimeUploadResult(status="skipped", path=str(event.path), message="debounced")
        if key in self._in_progress:
            self._write_watch_entry("realtime_skipped", event.path, "file is already being processed")
            return RealtimeUploadResult(status="skipped", path=str(event.path), message="already processing")

        self._in_progress.add(key)
        try:
            result = self.process_path(event.path)
            self._last_handled[key] = time.monotonic()
            return result
        finally:
            self._in_progress.discard(key)

    def process_path(self, path: str | Path) -> RealtimeUploadResult:
        file_path = Path(path)
        self._write_watch_entry("realtime_detected", file_path, "file change detected")
        stable = wait_for_stable_file(
            file_path,
            attempts=self.config.watch.stable_check_attempts,
            interval_seconds=self.config.watch.stable_check_seconds,
            sleep_func=self.sleep,
        )
        if not stable:
            self._write_watch_entry("realtime_skipped", file_path, "file is not stable")
            return RealtimeUploadResult(status="skipped", path=str(file_path), message="file is not stable")

        run_time = self.now().astimezone(SHANGHAI_TZ)
        candidate = build_candidate_for_path(
            self.config.share.root,
            self.scan_config,
            file_path,
            date_window=None,
        )
        if candidate is None:
            self._write_watch_entry("realtime_skipped", file_path, "file does not match upload rules")
            return RealtimeUploadResult(status="skipped", path=str(file_path), message="file does not match upload rules")

        return self.enqueue_candidate(candidate, run_time)

    def enqueue_candidate(self, candidate: CandidateFile, run_time: datetime) -> RealtimeUploadResult:
        run_id = f"ZK-RT-{run_time.strftime('%Y%m%d-%H%M%S')}"
        log_date = run_time.strftime("%Y-%m-%d")
        self.progress(f"realtime upload candidate: {candidate.path}")
        parsed_file = parse_candidate(candidate)
        history_result = split_history_uploaded([parsed_file], self.log_store.load_uploaded_fingerprints())
        if history_result.skipped:
            self.log_store.append_upload_log(log_date, _upload_skipped_entry(run_id, parsed_file, "file already uploaded"))
            self._write_watch_entry("realtime_skipped", candidate.path, "file already uploaded")
            return RealtimeUploadResult(status="skipped", path=str(candidate.path), message="file already uploaded")

        enqueue_result = self.task_store.enqueue_pending(parsed_file, run_id=run_id)
        if not enqueue_result.queued:
            self.log_store.append_upload_log(log_date, _upload_skipped_entry(run_id, parsed_file, enqueue_result.message))
            self._write_watch_entry("realtime_skipped", candidate.path, enqueue_result.message)
            return RealtimeUploadResult(status="skipped", path=str(candidate.path), message=enqueue_result.message)

        self.log_store.append_upload_log(log_date, _upload_pending_entry(run_id, parsed_file, enqueue_result.task_id))
        self._write_watch_entry("realtime_upload_queued", candidate.path, "upload task queued")
        return RealtimeUploadResult(
            status="queued",
            path=str(candidate.path),
            message="upload task queued",
            stats={"queued_count": 1},
        )

    def start_worker(self, *, interval_seconds: float = 1.0) -> None:
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return
        self._worker_stop.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            kwargs={"interval_seconds": interval_seconds},
            daemon=True,
        )
        self._worker_thread.start()

    def stop_worker(self) -> None:
        self._worker_stop.set()
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=5)

    def drain_pending_once(self) -> bool:
        task = self.task_store.claim_pending()
        if task is None:
            return False
        self._execute_task(task)
        return True

    def _worker_loop(self, *, interval_seconds: float) -> None:
        while not self._worker_stop.is_set():
            processed = self.drain_pending_once()
            if not processed:
                self.sleep(interval_seconds)

    def _execute_task(self, task) -> None:
        parsed_file = parsed_file_from_task(task)
        run_time = self.now().astimezone(SHANGHAI_TZ)
        log_date = run_time.strftime("%Y-%m-%d")

        if self.config.upload.dry_run:
            self.task_store.mark_skipped(task.id, reason="dry-run mode, upload not executed")
            self.log_store.append_upload_log(log_date, _upload_skipped_entry(task.run_id, parsed_file, "dry-run mode, upload not executed"))
            return

        self.progress(f"realtime worker uploading: {parsed_file.filename}, flow={parsed_file.flow}")
        result = self.upload_func(parsed_file)
        if result.success:
            record = build_upload_record(
                parsed_file=parsed_file,
                file_hash=None,
                run_id=task.run_id,
                uploaded_at=run_time.strftime("%Y-%m-%d %H:%M:%S"),
                response=result.response,
            )
            self.log_store.save_uploaded_fingerprint(parsed_file.fallback_key, record)
            if parsed_file.business_key:
                self.log_store.save_uploaded_business_key(parsed_file.business_key, record)
            self.task_store.mark_success(
                task.id,
                response=result.response,
                http_status=result.status_code,
                retry_count=result.retry_count,
            )
            self.log_store.append_upload_log(log_date, _upload_success_entry(task.run_id, parsed_file, result))
            self._write_watch_entry("realtime_upload_success", parsed_file.path, "upload succeeded")
            self.progress(f"realtime worker upload succeeded: {parsed_file.filename}")
            return

        self.task_store.mark_failed(
            task.id,
            response=result.response,
            response_text=result.response_text,
            error=result.error,
            http_status=result.status_code,
            retry_count=result.retry_count,
        )
        self.log_store.append_upload_log(log_date, _upload_failed_entry(task.run_id, parsed_file, result))
        self._write_watch_entry("realtime_upload_failed", parsed_file.path, "upload failed")
        self.progress(f"realtime worker upload failed: {parsed_file.filename} - {result.error}")

    def _write_watch_entry(self, event_type: str, path: Path, message: str) -> None:
        current_time = self.now().astimezone(SHANGHAI_TZ)
        self.log_store.append_watch_log(
            current_time.date().isoformat(),
            {
                "event_type": event_type,
                "path": str(path),
                "previous_path": None,
                "is_dir": path.is_dir(),
                "is_excel": path.suffix.lower() in {".xls", ".xlsx"},
                "log_time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "message": message,
            },
        )


def wait_for_stable_file(
    path: str | Path,
    *,
    attempts: int,
    interval_seconds: int,
    sleep_func: SleepFunc | None = None,
) -> bool:
    file_path = Path(path)
    sleep = sleep_func or time.sleep
    previous: tuple[int, int] | None = None
    stable_count = 0
    for index in range(max(attempts, 1)):
        try:
            stat = file_path.stat()
        except OSError:
            return False
        current = (stat.st_size, stat.st_mtime_ns)
        if current == previous:
            stable_count += 1
            if stable_count >= max(attempts - 1, 1):
                return True
        else:
            stable_count = 0
            previous = current
        if index < attempts - 1:
            sleep(interval_seconds)
    return attempts <= 1


def _real_upload_func(config: AppConfig) -> UploadFunc:
    def _upload(parsed_file: ParsedFile) -> UploadResult:
        return upload_file(
            file_path=parsed_file.path,
            url=config.upload.url,
            timeout_seconds=config.upload.timeout_seconds,
            retry_count=config.upload.retry_count,
            flow=parsed_file.flow,
            filePath=parsed_file.filePath,
        )

    return _upload


def _base_upload_entry(run_id: str, parsed_file: ParsedFile) -> dict[str, object]:
    return {
        "run_id": run_id,
        "filename": parsed_file.filename,
        "full_path": str(parsed_file.path),
        "directory": str(parsed_file.directory),
        "file_size": parsed_file.size,
        "file_mtime": parsed_file.modified_at,
        "flow": parsed_file.flow,
        "filePath": parsed_file.filePath,
        "region": parsed_file.region,
        "normalized_name": parsed_file.normalized_name,
        "business_key": parsed_file.business_key,
        "fallback_key": parsed_file.fallback_key,
        "dedupe_key": parsed_file.dedupe_key,
    }


def _upload_pending_entry(run_id: str, parsed_file: ParsedFile, task_id: int | None) -> dict[str, object]:
    entry = _base_upload_entry(run_id, parsed_file)
    entry.update({"action": "upload_pending", "task_id": task_id, "message": "upload task queued"})
    return entry


def _upload_skipped_entry(run_id: str, parsed_file: ParsedFile, reason: str) -> dict[str, object]:
    entry = _base_upload_entry(run_id, parsed_file)
    entry.update({"action": "upload_skipped", "message": reason})
    return entry


def _upload_success_entry(run_id: str, parsed_file: ParsedFile, result: UploadResult) -> dict[str, object]:
    entry = _base_upload_entry(run_id, parsed_file)
    entry.update(
        {
            "action": "upload_success",
            "http_status": result.status_code,
            "response": result.response,
            "retry_count": result.retry_count,
        }
    )
    return entry


def _upload_failed_entry(run_id: str, parsed_file: ParsedFile, result: UploadResult) -> dict[str, object]:
    entry = _base_upload_entry(run_id, parsed_file)
    entry.update(
        {
            "action": "upload_failed",
            "http_status": result.status_code,
            "response": result.response,
            "response_text": result.response_text,
            "error": result.error,
            "retry_count": result.retry_count,
        }
    )
    return entry


def _current_time() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def _normalize_key(path: Path) -> str:
    return str(path).replace("/", "\\").lower()


def _no_progress(_: str) -> None:
    return None
