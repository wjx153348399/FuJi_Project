from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from zk_impedance_upload.dedupe import BatchSkippedFile, dedupe_batch
from zk_impedance_upload.fingerprint import (
    HashCache,
    SkippedFile,
    build_upload_record,
    split_history_uploaded,
)
from zk_impedance_upload.log_store import LogStore
from zk_impedance_upload.parser import ParsedFile, parse_candidate
from zk_impedance_upload.scanner import CandidateFile
from zk_impedance_upload.uploader import UploadResult


UploadFunc = Callable[[ParsedFile], UploadResult]
ProgressFunc = Callable[[str], None]


@dataclass(frozen=True)
class UploadPipelineResult:
    upload_log_path: str | None
    parsed_files: list[ParsedFile]
    pending_files: list[ParsedFile]
    failed_files: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def process_upload_candidates(
    *,
    candidates: list[CandidateFile],
    log_store: LogStore,
    log_date: str,
    run_id: str,
    run_time: datetime,
    dry_run: bool,
    max_upload_files: int | None,
    upload_func: UploadFunc,
    progress_func: ProgressFunc | None = None,
    progress_prefix: str = "",
) -> UploadPipelineResult:
    progress = progress_func or _no_progress
    prefix = f"{progress_prefix} " if progress_prefix else ""
    parsed_files = [parse_candidate(candidate) for candidate in candidates]
    hash_cache = HashCache()

    progress(f"{prefix}checking batch duplicates...")
    batch_result = dedupe_batch(parsed_files, hash_cache)
    progress(
        f"{prefix}batch duplicate check completed: "
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
        f"{prefix}history upload check completed: "
        f"pending={len(history_result.pending)}, "
        f"history_skip={len(history_result.skipped)}"
    )
    for skipped in history_result.skipped:
        upload_log_path = str(log_store.append_upload_log(log_date, _history_skip_entry(run_id, skipped)))

    upload_pending, limit_skipped = _apply_upload_limit(history_result.pending, max_upload_files)
    if limit_skipped:
        progress(f"{prefix}upload limit applied: limit_skip={len(limit_skipped)}")
    for parsed_file in limit_skipped:
        upload_log_path = str(log_store.append_upload_log(log_date, _upload_limit_entry(run_id, parsed_file)))

    success_count = 0
    fail_count = 0
    pending_count = len(upload_pending) if dry_run else 0
    failed_files: list[str] = []

    if dry_run:
        progress(f"{prefix}dry-run mode: recording pending files only, pending={len(upload_pending)}")
        for parsed_file in upload_pending:
            upload_log_path = str(log_store.append_upload_log(log_date, _dry_run_entry(run_id, parsed_file)))
    else:
        total_uploads = len(upload_pending)
        progress(f"{prefix}starting real upload: total={total_uploads}")
        for index, parsed_file in enumerate(upload_pending, start=1):
            progress(
                f"{prefix}uploading {index}/{total_uploads}: {parsed_file.filename}, "
                f"flow={parsed_file.flow}"
            )
            result = upload_func(parsed_file)
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
                upload_log_path = str(log_store.append_upload_log(log_date, _upload_success_entry(run_id, parsed_file, result)))
                progress(f"{prefix}upload succeeded {index}/{total_uploads}: {parsed_file.filename}")
            else:
                fail_count += 1
                failed_files.append(str(parsed_file.path))
                upload_log_path = str(log_store.append_upload_log(log_date, _upload_failed_entry(run_id, parsed_file, result)))
                progress(f"{prefix}upload failed {index}/{total_uploads}: {parsed_file.filename} - {result.error}")

    skip_count = len(batch_result.skipped) + len(history_result.skipped) + len(limit_skipped)
    return UploadPipelineResult(
        upload_log_path=upload_log_path,
        parsed_files=parsed_files,
        pending_files=upload_pending,
        failed_files=failed_files,
        stats={
            "with_flow_count": len([item for item in parsed_files if item.flow.strip()]),
            "blank_flow_count": len([item for item in parsed_files if not item.flow.strip()]),
            "selected_count": len(batch_result.selected),
            "success_count": success_count,
            "fail_count": fail_count,
            "skip_count": skip_count,
            "pending_count": pending_count,
        },
    )


def _no_progress(_: str) -> None:
    return None


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
        "flow": parsed_file.flow,
        "filePath": parsed_file.filePath,
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
    entry.update({"action": "dry_run_pending", "message": "dry-run mode, upload not executed"})
    return entry


def _upload_limit_entry(run_id: str, parsed_file: ParsedFile) -> dict[str, object]:
    entry = _base_entry(run_id, parsed_file)
    entry.update({"action": "upload_limit_skipped", "message": "upload limit reached"})
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


def _upload_failed_entry(
    run_id: str,
    parsed_file: ParsedFile,
    result: UploadResult,
) -> dict[str, object]:
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
