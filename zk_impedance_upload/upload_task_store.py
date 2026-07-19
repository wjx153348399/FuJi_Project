from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from zk_impedance_upload.config import AppConfig
from zk_impedance_upload.exceptions import ConfigError
from zk_impedance_upload.parser import ParsedFile


_TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


@dataclass(frozen=True)
class UploadTask:
    id: int
    run_id: str
    flow: str
    filePath: str
    filename: str
    full_path: str
    business_key: str
    fallback_key: str
    dedupe_key: str
    request: dict[str, Any]
    retry_count: int = 0


@dataclass(frozen=True)
class EnqueueResult:
    queued: bool
    task_id: int | None
    message: str


class UploadTaskStore(Protocol):
    def enqueue_pending(self, parsed_file: ParsedFile, *, run_id: str) -> EnqueueResult:
        ...

    def claim_pending(self) -> UploadTask | None:
        ...

    def mark_success(self, task_id: int, *, response: dict[str, Any], http_status: int | None, retry_count: int) -> None:
        ...

    def mark_failed(
        self,
        task_id: int,
        *,
        response: dict[str, Any],
        response_text: str,
        error: str,
        http_status: int | None,
        retry_count: int,
    ) -> None:
        ...

    def mark_skipped(self, task_id: int, *, reason: str) -> None:
        ...


class InMemoryUploadTaskStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_id = 1
        self._tasks: list[dict[str, Any]] = []
        self._source_hashes: set[str] = set()

    def enqueue_pending(self, parsed_file: ParsedFile, *, run_id: str) -> EnqueueResult:
        source_hash = build_task_source_hash(parsed_file)
        with self._lock:
            if source_hash in self._source_hashes:
                return EnqueueResult(False, None, "duplicate task")
            task_id = self._next_id
            self._next_id += 1
            self._source_hashes.add(source_hash)
            self._tasks.append(_task_record(task_id, parsed_file, run_id, source_hash))
            return EnqueueResult(True, task_id, "queued")

    def claim_pending(self) -> UploadTask | None:
        with self._lock:
            for task in self._tasks:
                if task["status"] == "pending":
                    task["status"] = "running"
                    return _record_to_task(task)
        return None

    def mark_success(self, task_id: int, *, response: dict[str, Any], http_status: int | None, retry_count: int) -> None:
        self._mark_done(task_id, "success", response=response, http_status=http_status, retry_count=retry_count)

    def mark_failed(
        self,
        task_id: int,
        *,
        response: dict[str, Any],
        response_text: str,
        error: str,
        http_status: int | None,
        retry_count: int,
    ) -> None:
        message = error or response_text
        self._mark_done(
            task_id,
            "failed",
            response=response,
            http_status=http_status,
            retry_count=retry_count,
            error_message=message,
        )

    def mark_skipped(self, task_id: int, *, reason: str) -> None:
        self._mark_done(task_id, "skipped", error_message=reason)

    def list_records(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(task) for task in self._tasks]

    def _mark_done(self, task_id: int, status: str, **updates: Any) -> None:
        with self._lock:
            for task in self._tasks:
                if task["id"] == task_id:
                    task["status"] = status
                    task.update(updates)
                    return


class SqlServerUploadTaskStore:
    def __init__(self, db_config: Any, *, table: str = "dbo.zk_upload_task_queue", driver: str | None = None) -> None:
        self.db_config = db_config
        self.table = table
        self.driver = driver

    def enqueue_pending(self, parsed_file: ParsedFile, *, run_id: str) -> EnqueueResult:
        table_name = _validated_table_name(self.table)
        source_hash = build_task_source_hash(parsed_file)
        record = _task_record(0, parsed_file, run_id, source_hash)
        with self._connect() as connection:
            row = connection.cursor().execute(
                f"""
                DECLARE @inserted TABLE (id BIGINT);
                IF NOT EXISTS (SELECT 1 FROM {table_name} WHERE source_hash = ?)
                BEGIN
                    INSERT INTO {table_name}
                      (
                        status, run_id, flow, filePath, filename, full_path,
                        business_key, fallback_key, dedupe_key, request_json,
                        source_hash
                      )
                    OUTPUT INSERTED.id INTO @inserted
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                END
                SELECT id FROM @inserted;
                """,
                source_hash,
                record["status"],
                record["run_id"],
                record["flow"],
                record["filePath"],
                record["filename"],
                record["full_path"],
                record["business_key"],
                record["fallback_key"],
                record["dedupe_key"],
                json.dumps(record["request"], ensure_ascii=False, separators=(",", ":")),
                source_hash,
            ).fetchone()
            connection.commit()
        if row is None:
            return EnqueueResult(False, None, "duplicate task")
        return EnqueueResult(True, int(row[0]), "queued")

    def claim_pending(self) -> UploadTask | None:
        table_name = _validated_table_name(self.table)
        with self._connect() as connection:
            row = connection.cursor().execute(
                f"""
                ;WITH next_task AS (
                    SELECT TOP (1) *
                    FROM {table_name} WITH (UPDLOCK, READPAST, ROWLOCK)
                    WHERE status = 'pending'
                    ORDER BY created_at ASC, id ASC
                )
                UPDATE next_task
                SET status = 'running', started_at = SYSDATETIME()
                OUTPUT
                    INSERTED.id,
                    INSERTED.run_id,
                    INSERTED.flow,
                    INSERTED.filePath,
                    INSERTED.filename,
                    INSERTED.full_path,
                    INSERTED.business_key,
                    INSERTED.fallback_key,
                    INSERTED.dedupe_key,
                    INSERTED.request_json,
                    INSERTED.retry_count
                """
            ).fetchone()
            connection.commit()
        if row is None:
            return None
        return _row_to_task(row)

    def mark_success(self, task_id: int, *, response: dict[str, Any], http_status: int | None, retry_count: int) -> None:
        self._mark_done(
            task_id,
            "success",
            response_json=json.dumps(response, ensure_ascii=False, separators=(",", ":")),
            error_message=None,
            http_status=http_status,
            retry_count=retry_count,
        )

    def mark_failed(
        self,
        task_id: int,
        *,
        response: dict[str, Any],
        response_text: str,
        error: str,
        http_status: int | None,
        retry_count: int,
    ) -> None:
        response_payload = response or ({"response_text": response_text} if response_text else {})
        self._mark_done(
            task_id,
            "failed",
            response_json=json.dumps(response_payload, ensure_ascii=False, separators=(",", ":")),
            error_message=error or response_text,
            http_status=http_status,
            retry_count=retry_count,
        )

    def mark_skipped(self, task_id: int, *, reason: str) -> None:
        self._mark_done(
            task_id,
            "skipped",
            response_json=None,
            error_message=reason,
            http_status=None,
            retry_count=0,
        )

    def _mark_done(
        self,
        task_id: int,
        status: str,
        *,
        response_json: str | None,
        error_message: str | None,
        http_status: int | None,
        retry_count: int,
    ) -> None:
        table_name = _validated_table_name(self.table)
        with self._connect() as connection:
            connection.cursor().execute(
                f"""
                UPDATE {table_name}
                SET status = ?,
                    response_json = ?,
                    error_message = ?,
                    http_status = ?,
                    retry_count = ?,
                    finished_at = SYSDATETIME()
                WHERE id = ?
                """,
                status,
                response_json,
                error_message,
                http_status,
                retry_count,
                task_id,
            )
            connection.commit()

    def _connect(self):
        try:
            import pyodbc
        except ImportError as exc:  # pragma: no cover - depends on deployment environment
            raise ConfigError("upload task queue requires pyodbc; run pip install pyodbc") from exc

        return pyodbc.connect(
            _build_connection_string(self.db_config, self.driver),
            timeout=self.db_config.connect_timeout_seconds,
        )


def create_upload_task_store(config: AppConfig) -> UploadTaskStore:
    db_config = getattr(getattr(config, "station_config", None), "db", None)
    if db_config is None or not getattr(db_config, "enabled", False):
        return InMemoryUploadTaskStore()
    driver = getattr(db_config, "odbc_driver", None)
    return SqlServerUploadTaskStore(db_config, driver=driver)


def build_task_source_hash(parsed_file: ParsedFile) -> str:
    payload = "\n".join(
        [
            parsed_file.flow,
            parsed_file.filePath,
            str(parsed_file.path),
            parsed_file.fallback_key,
        ]
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parsed_file_from_task(task: UploadTask) -> ParsedFile:
    return ParsedFile(
        path=Path(task.full_path),
        filename=task.filename,
        directory=Path(task.full_path).parent,
        size=int(task.request.get("file_size") or 0),
        modified_at=str(task.request.get("file_mtime") or ""),
        flow=task.flow,
        filePath=task.filePath,
        region=str(task.request.get("region") or "UNKNOWN"),
        normalized_name=str(task.request.get("normalized_name") or ""),
        business_key=task.business_key,
        fallback_key=task.fallback_key,
        dedupe_key=task.dedupe_key,
    )


def _task_record(task_id: int, parsed_file: ParsedFile, run_id: str, source_hash: str) -> dict[str, Any]:
    request = {
        "flow": parsed_file.flow,
        "filePath": parsed_file.filePath,
        "filename": parsed_file.filename,
        "full_path": str(parsed_file.path),
        "directory": str(parsed_file.directory),
        "file_size": parsed_file.size,
        "file_mtime": parsed_file.modified_at,
        "region": parsed_file.region,
        "normalized_name": parsed_file.normalized_name,
        "business_key": parsed_file.business_key,
        "fallback_key": parsed_file.fallback_key,
        "dedupe_key": parsed_file.dedupe_key,
    }
    return {
        "id": task_id,
        "status": "pending",
        "run_id": run_id,
        "flow": parsed_file.flow,
        "filePath": parsed_file.filePath,
        "filename": parsed_file.filename,
        "full_path": str(parsed_file.path),
        "business_key": parsed_file.business_key,
        "fallback_key": parsed_file.fallback_key,
        "dedupe_key": parsed_file.dedupe_key,
        "request": request,
        "source_hash": source_hash,
        "retry_count": 0,
    }


def _record_to_task(record: dict[str, Any]) -> UploadTask:
    return UploadTask(
        id=int(record["id"]),
        run_id=str(record["run_id"]),
        flow=str(record["flow"] or ""),
        filePath=str(record["filePath"] or ""),
        filename=str(record["filename"] or Path(str(record["full_path"])).name),
        full_path=str(record["full_path"]),
        business_key=str(record["business_key"] or ""),
        fallback_key=str(record["fallback_key"] or ""),
        dedupe_key=str(record["dedupe_key"] or ""),
        request=dict(record["request"] or {}),
        retry_count=int(record.get("retry_count") or 0),
    )


def _row_to_task(row: object) -> UploadTask:
    request = _safe_json_dict(row[9])
    return UploadTask(
        id=int(row[0]),
        run_id=str(row[1] or ""),
        flow=str(row[2] or ""),
        filePath=str(row[3] or ""),
        filename=str(row[4] or Path(str(row[5] or "")).name),
        full_path=str(row[5] or ""),
        business_key=str(row[6] or ""),
        fallback_key=str(row[7] or ""),
        dedupe_key=str(row[8] or ""),
        request=request,
        retry_count=int(row[10] or 0),
    )


def _safe_json_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _build_connection_string(db_config: Any, driver: str | None) -> str:
    resolved_driver = driver or getattr(db_config, "driver", "ODBC Driver 17 for SQL Server")
    return (
        f"DRIVER={{{resolved_driver}}};"
        f"SERVER={db_config.host},{db_config.port};"
        f"DATABASE={db_config.database};"
        f"UID={db_config.username};"
        f"PWD={db_config.password};"
        "TrustServerCertificate=yes;"
    )


def _validated_table_name(table_name: str) -> str:
    value = table_name.strip()
    if not _TABLE_NAME_PATTERN.match(value):
        raise ConfigError("upload task table must be table or schema.table")
    return ".".join(f"[{part}]" for part in value.split("."))
