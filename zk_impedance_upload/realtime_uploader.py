from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import time
from typing import TYPE_CHECKING, Callable

from zk_impedance_upload.config import AppConfig, ScanConfig
from zk_impedance_upload.date_window import SHANGHAI_TZ
from zk_impedance_upload.log_store import LogStore
from zk_impedance_upload.parser import ParsedFile
from zk_impedance_upload.scanner import CandidateFile, build_candidate_for_path
from zk_impedance_upload.upload_pipeline import process_upload_candidates
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
        sleep_func: SleepFunc | None = None,
        now_func: NowFunc | None = None,
        progress_func: ProgressFunc | None = None,
    ) -> None:
        self.config = config
        self.scan_config = scan_config
        self.log_store = log_store
        self.upload_func = upload_func or _real_upload_func(config)
        self.sleep = sleep_func or time.sleep
        self.now = now_func or _current_time
        self.progress = progress_func or _no_progress
        self._in_progress: set[str] = set()
        self._last_handled: dict[str, float] = {}

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

        return self.process_candidate(candidate, run_time)

    def process_candidate(self, candidate: CandidateFile, run_time: datetime) -> RealtimeUploadResult:
        run_id = f"ZK-RT-{run_time.strftime('%Y%m%d-%H%M%S')}"
        log_date = run_time.strftime("%Y-%m-%d")
        self.progress(f"realtime upload candidate: {candidate.path}")
        pipeline_result = process_upload_candidates(
            candidates=[candidate],
            log_store=self.log_store,
            log_date=log_date,
            run_id=run_id,
            run_time=run_time,
            dry_run=self.config.upload.dry_run,
            max_upload_files=1,
            upload_func=self.upload_func,
            progress_func=self.progress,
            progress_prefix="realtime",
        )
        if pipeline_result.stats["success_count"] > 0:
            self._write_watch_entry("realtime_upload_success", candidate.path, "upload succeeded")
            status = "uploaded"
        elif pipeline_result.stats["fail_count"] > 0:
            self._write_watch_entry("realtime_upload_failed", candidate.path, "upload failed")
            status = "failed"
        else:
            self._write_watch_entry("realtime_skipped", candidate.path, "no pending upload after checks")
            status = "skipped"
        return RealtimeUploadResult(
            status=status,
            path=str(candidate.path),
            stats=pipeline_result.stats,
        )

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


def _current_time() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def _normalize_key(path: Path) -> str:
    return str(path).replace("/", "\\").lower()


def _no_progress(_: str) -> None:
    return None
