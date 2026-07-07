from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from zk_impedance_upload.config import AppConfig
from zk_impedance_upload.date_window import SHANGHAI_TZ, build_date_window
from zk_impedance_upload.log_store import LogStore
from zk_impedance_upload.parser import ParsedFile
from zk_impedance_upload.scanner import scan_files
from zk_impedance_upload.share_auth import ensure_share_access
from zk_impedance_upload.station_config import StationTargetRepository, build_effective_scan_config
from zk_impedance_upload.upload_pipeline import process_upload_candidates
from zk_impedance_upload.uploader import UploadResult, upload_file
from zk_impedance_upload.watcher import build_watch_summary


UploadFunc = Callable[[ParsedFile], UploadResult]
ShareAccessFunc = Callable[[AppConfig], None]
ProgressFunc = Callable[[str], None]


@dataclass(frozen=True)
class RunResult:
    run_id: str
    summary_path: str
    upload_log_path: str | None
    stats: dict[str, int | str]


def run_upload_task(
    config: AppConfig,
    now: datetime | None = None,
    upload_func: UploadFunc | None = None,
    share_access_func: ShareAccessFunc | None = None,
    progress_func: ProgressFunc | None = None,
    station_repository: StationTargetRepository | None = None,
) -> RunResult:
    progress = progress_func or _no_progress
    run_time = (now or datetime.now(SHANGHAI_TZ)).astimezone(SHANGHAI_TZ)
    run_id = f"ZK-{run_time.strftime('%Y%m%d-%H%M%S')}"
    log_date = run_time.strftime("%Y-%m-%d")
    summary_timestamp = run_time.strftime("%Y-%m-%d_%H-%M-%S")

    progress(f"start upload task: run_id={run_id}")
    progress("checking share access...")
    (share_access_func or ensure_share_access)(config)
    progress("share access check completed")

    log_store = LogStore(config.log.dir)
    progress("checking log directory...")
    log_store.ensure_ready()
    progress("log directory check completed")

    effective_scan = build_effective_scan_config(config, station_repository)
    progress(
        "station directory config loaded: "
        f"source={effective_scan.effective_source}, "
        f"targets={effective_scan.target_count}"
    )
    if effective_scan.fallback_reason:
        progress(f"station directory config fell back to JSON: {effective_scan.fallback_reason}")

    date_window = build_date_window(now=run_time, day_offset=config.upload.day_offset)
    progress(f"target date window: {date_window.target_day}")
    _maybe_write_watch_summary(
        config=config,
        log_store=log_store,
        target_day=date_window.target_day,
        summary_timestamp=summary_timestamp,
    )

    progress("scanning share files...")
    scan_result = scan_files(config.share.root, effective_scan.scan, date_window)
    progress(
        "scan completed: "
        f"candidate={len(scan_result.candidates)}, "
        f"missing_dir={len(scan_result.missing_dirs)}, "
        f"failed_dir={len(scan_result.failed_dirs)}"
    )

    pipeline_result = process_upload_candidates(
        candidates=scan_result.candidates,
        log_store=log_store,
        log_date=log_date,
        run_id=run_id,
        run_time=run_time,
        dry_run=config.upload.dry_run,
        max_upload_files=config.upload.max_upload_files,
        upload_func=upload_func or _real_upload_func(config),
        progress_func=progress,
    )

    stats: dict[str, int | str] = {
        "task_status": "completed",
        "candidate_count": len(scan_result.candidates),
        "with_flow_count": pipeline_result.stats["with_flow_count"],
        "blank_flow_count": pipeline_result.stats["blank_flow_count"],
        "selected_count": pipeline_result.stats["selected_count"],
        "success_count": pipeline_result.stats["success_count"],
        "fail_count": pipeline_result.stats["fail_count"],
        "skip_count": pipeline_result.stats["skip_count"],
        "pending_count": pipeline_result.stats["pending_count"],
        "missing_dir_count": len(scan_result.missing_dirs),
        "failed_dir_count": len(scan_result.failed_dirs),
        "station_target_count": effective_scan.target_count,
        "station_config_source": effective_scan.requested_source,
        "effective_station_config_source": effective_scan.effective_source,
    }
    if effective_scan.fallback_reason:
        stats["station_config_fallback_reason"] = effective_scan.fallback_reason

    summary = {
        "run_id": run_id,
        "run_time": run_time.strftime("%Y-%m-%d %H:%M:%S"),
        "target_day": date_window.target_day,
        "stats": stats,
        "failed_files": pipeline_result.failed_files,
        "pending_files": [str(item.path) for item in pipeline_result.pending_files] if config.upload.dry_run else [],
    }
    summary_path = log_store.write_summary(summary_timestamp, summary)
    progress(
        "upload task summary: "
        f"success={pipeline_result.stats['success_count']}, "
        f"fail={pipeline_result.stats['fail_count']}, "
        f"skip={pipeline_result.stats['skip_count']}, "
        f"summary={summary_path}"
    )

    return RunResult(
        run_id=run_id,
        summary_path=str(summary_path),
        upload_log_path=pipeline_result.upload_log_path,
        stats=stats,
    )


def _no_progress(_: str) -> None:
    return None


def _maybe_write_watch_summary(
    config: AppConfig,
    log_store: LogStore,
    target_day: str,
    summary_timestamp: str,
) -> None:
    if not config.watch.enabled:
        return
    if config.watch.notice_mode != "log_and_daily_summary":
        return
    build_watch_summary(log_store, target_day, summary_timestamp)


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
