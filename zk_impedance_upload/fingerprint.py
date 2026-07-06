from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zk_impedance_upload.parser import ParsedFile


@dataclass(frozen=True)
class SkippedFile:
    parsed_file: ParsedFile
    file_hash: str | None
    action: str
    reason: str


@dataclass(frozen=True)
class HistorySplitResult:
    pending: list[ParsedFile]
    skipped: list[SkippedFile]


class HashCache:
    def __init__(self) -> None:
        self._cache: dict[Path, str] = {}

    def get(self, path: Path) -> str:
        if path not in self._cache:
            self._cache[path] = calculate_sha256(path)
        return self._cache[path]


def calculate_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_upload_record(
    parsed_file: ParsedFile,
    file_hash: str | None,
    run_id: str,
    uploaded_at: str,
    response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
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
        "run_id": run_id,
        "uploaded_at": uploaded_at,
        "response": response or {},
    }
    if file_hash is not None:
        record["file_hash"] = file_hash
    return record


def has_uploaded_success(
    parsed_file: ParsedFile,
    uploaded_fingerprints: dict[str, Any],
) -> bool:
    return isinstance(uploaded_fingerprints.get(parsed_file.fallback_key), dict)


def split_history_uploaded(
    parsed_files: list[ParsedFile],
    uploaded_fingerprints: dict[str, Any],
) -> HistorySplitResult:
    pending: list[ParsedFile] = []
    skipped: list[SkippedFile] = []

    for parsed_file in parsed_files:
        if has_uploaded_success(parsed_file, uploaded_fingerprints):
            skipped.append(
                SkippedFile(
                    parsed_file=parsed_file,
                    file_hash=None,
                    action="history_uploaded_skipped",
                    reason="同一 fallback_key 已有成功上传记录",
                )
            )
        else:
            pending.append(parsed_file)

    return HistorySplitResult(pending=pending, skipped=skipped)
