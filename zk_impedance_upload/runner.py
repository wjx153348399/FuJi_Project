from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from zk_impedance_upload.config import AppConfig
from zk_impedance_upload.date_window import SHANGHAI_TZ, build_date_window
from zk_impedance_upload.dedupe import BatchSkippedFile, dedupe_batch
from zk_impedance_upload.fingerprint import (
    HashCache,
    SkippedFile,
    build_upload_record,
    split_history_uploaded,
)
from zk_impedance_upload.log_store import LogStore
from zk_impedance_upload.parser import ParsedFile, parse_candidate
from zk_impedance_upload.scanner import scan_files
from zk_impedance_upload.share_auth import ensure_share_access
from zk_impedance_upload.station_config import StationTargetRepository, build_effective_scan_config
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
    progress(f"开始上传任务: run_id={run_id}")
    progress("正在检查共享盘访问...")
    (share_access_func or ensure_share_access)(config)
    progress("共享盘访问检查完成")
    log_store = LogStore(config.log.dir)
    progress("正在检查日志目录...")
    log_store.ensure_ready()
    progress("日志目录检查完成")
    effective_scan = build_effective_scan_config(config, station_repository)
    progress(
        "工站目录配置加载完成: "
        f"source={effective_scan.effective_source}, "
        f"targets={effective_scan.target_count}"
    )
    if effective_scan.fallback_reason:
        progress(f"工站目录配置已回退到 JSON: {effective_scan.fallback_reason}")

    date_window = build_date_window(now=run_time, day_offset=config.upload.day_offset)
    progress(f"目标日期窗口: {date_window.target_day}")
    _maybe_write_watch_summary(
        config=config,
        log_store=log_store,
        target_day=date_window.target_day,
        summary_timestamp=summary_timestamp,
    )
    progress("正在扫描共享盘文件...")
    scan_result = scan_files(config.share.root, effective_scan.scan, date_window)
    progress(
        "扫描完成: "
        f"candidate={len(scan_result.candidates)}, "
        f"missing_dir={len(scan_result.missing_dirs)}, "
        f"failed_dir={len(scan_result.failed_dirs)}"
    )
    parsed_files = [parse_candidate(candidate) for candidate in scan_result.candidates]

    hash_cache = HashCache()

    progress("正在执行批内去重...")
    batch_result = dedupe_batch(parsed_files, hash_cache)
    progress(
        "批内去重完成: "
        f"selected={len(batch_result.selected)}, "
        f"batch_skip={len(batch_result.skipped)}"
    )

    upload_log_path = None
    for skipped in batch_result.skipped:
        upload_log_path = str(log_store.append_upload_log(log_date, _batch_skip_entry(run_id, skipped)))

    history_result = split_history_uploaded(
        batch_result.selected,
        log_store.load_uploaded_fingerprints(),
    )
    progress(
        "历史上传检查完成: "
        f"pending={len(history_result.pending)}, "
        f"history_skip={len(history_result.skipped)}"
    )
    for skipped in history_result.skipped:
        upload_log_path = str(log_store.append_upload_log(log_date, _history_skip_entry(run_id, skipped)))

    upload_pending, limit_skipped = _apply_upload_limit(history_result.pending, config.upload.max_upload_files)
    if limit_skipped:
        progress(f"单次上传数量限制生效: limit_skip={len(limit_skipped)}")
    for parsed_file in limit_skipped:
        upload_log_path = str(log_store.append_upload_log(log_date, _upload_limit_entry(run_id, parsed_file)))

    success_count = 0
    fail_count = 0
    pending_count = len(upload_pending) if config.upload.dry_run else 0

    if config.upload.dry_run:
        progress(f"dry-run 模式: 仅记录待上传文件，不调用接口，pending={len(upload_pending)}")
        for parsed_file in upload_pending:
            upload_log_path = str(log_store.append_upload_log(log_date, _dry_run_entry(run_id, parsed_file)))
    else:
        effective_upload = upload_func or _real_upload_func(config)
        total_uploads = len(upload_pending)
        progress(f"开始真实上传: total={total_uploads}")
        for index, parsed_file in enumerate(upload_pending, start=1):
            progress(f"正在上传 {index}/{total_uploads}: {parsed_file.filename}")
            result = effective_upload(parsed_file)
            if result.success:
                success_count += 1
                record = build_upload_record(
                    parsed_file=parsed_file,
                    file_hash=None,
                    run_id=run_id,
                    uploaded_at=run_time.strftime("%Y-%m-%d %H:%M:%S"),
                    response=result.response,
                )
                log_store.save_uploaded_fingerprint(parsed_file.fallback_key, record)
                if parsed_file.business_key:
                    log_store.save_uploaded_business_key(parsed_file.business_key, record)
                upload_log_path = str(
                    log_store.append_upload_log(log_date, _upload_success_entry(run_id, parsed_file, result))
                )
                progress(f"上传成功 {index}/{total_uploads}: {parsed_file.filename}")
            else:
                fail_count += 1
                upload_log_path = str(log_store.append_upload_log(log_date, _upload_failed_entry(run_id, parsed_file, result)))
                progress(f"上传失败 {index}/{total_uploads}: {parsed_file.filename} - {result.error}")

    skip_count = len(batch_result.skipped) + len(history_result.skipped) + len(limit_skipped)
    stats: dict[str, int | str] = {
        "task_status": "completed",
        "candidate_count": len(scan_result.candidates),
        "selected_count": len(batch_result.selected),
        "success_count": success_count,
        "fail_count": fail_count,
        "skip_count": skip_count,
        "pending_count": pending_count,
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
        "failed_files": [],
        "pending_files": [str(item.path) for item in upload_pending] if config.upload.dry_run else [],
    }
    summary_path = log_store.write_summary(summary_timestamp, summary)
    progress(
        "上传任务汇总: "
        f"success={success_count}, fail={fail_count}, skip={skip_count}, "
        f"summary={summary_path}"
    )

    return RunResult(
        run_id=run_id,
        summary_path=str(summary_path),
        upload_log_path=upload_log_path,
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
            station_code=parsed_file.station_code,
            send_station_code=config.upload.send_station_code,
            station_field_name=config.upload.station_field_name,
        )

    return _upload


def _apply_upload_limit(
    pending_files: list[ParsedFile],
    max_upload_files: int | None,
) -> tuple[list[ParsedFile], list[ParsedFile]]:
    if max_upload_files is None:
        return pending_files, []
    if max_upload_files < 0:
        return pending_files, []
    return pending_files[:max_upload_files], pending_files[max_upload_files:]


def _base_entry(run_id: str, parsed_file: ParsedFile) -> dict[str, object]:
    return {
        "run_id": run_id,
        "filename": parsed_file.filename,
        "full_path": str(parsed_file.path),
        "directory": str(parsed_file.directory),
        "file_size": parsed_file.size,
        "file_mtime": parsed_file.modified_at,
        "station_code": parsed_file.station_code,
        "source_dir": parsed_file.source_dir,
        "region": parsed_file.region,
        "normalized_name": parsed_file.normalized_name,
        "business_key": parsed_file.business_key,
        "fallback_key": parsed_file.fallback_key,
        "dedupe_key": parsed_file.dedupe_key,
    }


def _batch_skip_entry(run_id: str, skipped: BatchSkippedFile) -> dict[str, object]:
    entry = _base_entry(run_id, skipped.parsed_file)
    entry.update({"action": skipped.action, "file_hash": skipped.file_hash, "message": skipped.reason})
    return entry


def _history_skip_entry(run_id: str, skipped: SkippedFile) -> dict[str, object]:
    entry = _base_entry(run_id, skipped.parsed_file)
    entry.update({"action": skipped.action, "message": skipped.reason})
    if skipped.file_hash is not None:
        entry["file_hash"] = skipped.file_hash
    return entry


def _dry_run_entry(run_id: str, parsed_file: ParsedFile) -> dict[str, object]:
    entry = _base_entry(run_id, parsed_file)
    entry.update({"action": "dry_run_pending", "message": "dry-run 模式未上传"})
    return entry


def _upload_limit_entry(run_id: str, parsed_file: ParsedFile) -> dict[str, object]:
    entry = _base_entry(run_id, parsed_file)
    entry.update({"action": "upload_limit_skipped", "message": "达到单次上传数量限制"})
    return entry


def _upload_success_entry(
    run_id: str,
    parsed_file: ParsedFile,
    result: UploadResult,
) -> dict[str, object]:
    entry = _base_entry(run_id, parsed_file)
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
    entry = _base_entry(run_id, parsed_file)
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
