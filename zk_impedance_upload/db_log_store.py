from __future__ import annotations

import json
import re
import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from zk_impedance_upload.exceptions import ConfigError
from zk_impedance_upload.log_store import _normalize_log_entry, _status_from_action


_TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


class RuntimeDbConfig(Protocol):
    host: str
    port: int
    database: str
    username: str
    password: str
    connect_timeout_seconds: int


@dataclass(frozen=True)
class RuntimeLogDbOptions:
    enabled: bool = True
    table: str = "dbo.zk_upload_runtime_log"


class DbLogStore:
    def __init__(
        self,
        db_config: RuntimeDbConfig,
        *,
        table: str = "dbo.zk_upload_runtime_log",
        driver: str | None = None,
    ) -> None:
        self.db_config = db_config
        self.table = table
        self.driver = driver
        self._source_hash_supported: bool | None = None

    def append_upload_log(self, log_date: str, entry: dict[str, Any]) -> str:
        return self._append_log(log_date, "upload", entry)

    def append_watch_log(self, log_date: str, entry: dict[str, Any]) -> str:
        return self._append_log(log_date, "watch", entry)

    def read_recent_logs(
        self,
        *,
        log_type: str = "all",
        limit: int = 200,
        keyword: str = "",
        status: str = "all",
    ) -> list[dict[str, Any]]:
        bounded_limit = min(max(limit, 1), 1000)
        table_name = _validated_table_name(self.table)
        where_clauses: list[str] = []
        params: list[Any] = []
        if log_type in {"upload", "watch"}:
            where_clauses.append("log_type = ?")
            params.append(log_type)
        elif log_type != "all":
            raise ConfigError("log_type must be one of: all, upload, watch")

        if status not in {"", "all"}:
            where_clauses.append("(status = ? OR level = ?)")
            params.extend([status, status])

        keyword = keyword.strip()
        if keyword:
            where_clauses.append(
                "(filename LIKE ? OR full_path LIKE ? OR flow LIKE ? OR action LIKE ? OR message LIKE ?)"
            )
            pattern = f"%{keyword}%"
            params.extend([pattern, pattern, pattern, pattern, pattern])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql = f"""
            SELECT TOP ({bounded_limit})
              CONVERT(varchar(19), log_time, 120) AS log_time,
              CONVERT(varchar(10), log_date, 120) AS log_date,
              log_type,
              level,
              status,
              action,
              run_id,
              filename,
              full_path,
              flow,
              http_status,
              retry_count,
              message,
              raw_json
            FROM {table_name}
            {where_sql}
            ORDER BY log_time DESC, id DESC
        """
        with self._connect() as connection:
            rows = connection.cursor().execute(sql, *params).fetchall()
        return [_row_to_log_entry(row) for row in rows]

    def build_status_snapshot(self, recent_entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        recent_entries = recent_entries if recent_entries is not None else self.read_recent_logs(limit=1000)
        today = date.today().isoformat()
        today_entries = [entry for entry in recent_entries if entry["log_date"] == today]
        upload_entries = [entry for entry in today_entries if entry["log_type"] == "upload"]
        return {
            "latest_upload": next((entry for entry in recent_entries if entry["log_type"] == "upload"), None),
            "latest_watch": next((entry for entry in recent_entries if entry["log_type"] == "watch"), None),
            "latest_error": next((entry for entry in recent_entries if entry["level"] == "error"), None),
            "today_success": len([entry for entry in upload_entries if entry["status"] == "success"]),
            "today_failed": len([entry for entry in upload_entries if entry["status"] == "failed"]),
            "today_skipped": len([entry for entry in upload_entries if entry["status"] == "skipped"]),
        }

    def _append_log(self, log_date: str, log_type: str, entry: dict[str, Any]) -> str:
        normalized = _normalize_log_entry(entry, log_type, log_date)
        table_name = _validated_table_name(self.table)
        raw_json = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        source_hash = build_source_hash(log_type, log_date, raw_json)
        with self._connect() as connection:
            if self._has_source_hash_column(connection):
                _execute_insert_with_source_hash(
                    connection,
                    table_name,
                    normalized,
                    log_date,
                    log_type,
                    _clean_text(entry.get("run_id")),
                    raw_json,
                    source_hash,
                )
            else:
                _execute_insert_without_source_hash(
                    connection,
                    table_name,
                    normalized,
                    log_date,
                    log_type,
                    _clean_text(entry.get("run_id")),
                    raw_json,
                )
            connection.commit()
        return f"db:{self.table}"

    def _connect(self):
        try:
            import pyodbc
        except ImportError as exc:  # pragma: no cover - depends on deployment environment
            raise ConfigError("数据库日志需要安装 pyodbc，请先执行 pip install pyodbc") from exc

        return pyodbc.connect(
            _build_connection_string(self.db_config, self.driver),
            timeout=self.db_config.connect_timeout_seconds,
        )

    def _has_source_hash_column(self, connection) -> bool:
        if self._source_hash_supported is not None:
            return self._source_hash_supported
        object_name = _validated_object_name(self.table)
        row = connection.cursor().execute(f"SELECT COL_LENGTH(N'{object_name}', N'source_hash') AS source_hash_length").fetchone()
        self._source_hash_supported = bool(getattr(row, "source_hash_length", None))
        return self._source_hash_supported


class RuntimeLogStore:
    def __init__(self, file_store, db_store: DbLogStore | None = None) -> None:
        self.file_store = file_store
        self.db_store = db_store
        self.log_dir = file_store.log_dir

    def ensure_ready(self) -> None:
        self.file_store.ensure_ready()

    def append_upload_log(self, log_date: str, entry: dict[str, Any]):
        path = self.file_store.append_upload_log(log_date, entry)
        self._try_append_db("upload", log_date, entry)
        return path

    def append_watch_log(self, log_date: str, entry: dict[str, Any]):
        path = self.file_store.append_watch_log(log_date, entry)
        self._try_append_db("watch", log_date, entry)
        return path

    def read_recent_logs(self, **kwargs):
        if self.db_store is not None:
            return self.db_store.read_recent_logs(**kwargs)
        return self.file_store.read_recent_logs(**kwargs)

    def build_status_snapshot(self, recent_entries=None):
        if self.db_store is not None:
            return self.db_store.build_status_snapshot(recent_entries)
        return self.file_store.build_status_snapshot(recent_entries)

    def write_summary(self, *args, **kwargs):
        return self.file_store.write_summary(*args, **kwargs)

    def write_watch_summary(self, *args, **kwargs):
        return self.file_store.write_watch_summary(*args, **kwargs)

    def load_uploaded_fingerprints(self):
        return self.file_store.load_uploaded_fingerprints()

    def save_uploaded_fingerprint(self, *args, **kwargs):
        return self.file_store.save_uploaded_fingerprint(*args, **kwargs)

    def load_uploaded_business_keys(self):
        return self.file_store.load_uploaded_business_keys()

    def save_uploaded_business_key(self, *args, **kwargs):
        return self.file_store.save_uploaded_business_key(*args, **kwargs)

    def _try_append_db(self, log_type: str, log_date: str, entry: dict[str, Any]) -> None:
        if self.db_store is None:
            return
        try:
            if log_type == "upload":
                self.db_store.append_upload_log(log_date, entry)
            else:
                self.db_store.append_watch_log(log_date, entry)
        except Exception as exc:
            fallback_entry = {
                "event_type": "runtime_log_db_write_failed",
                "path": str(entry.get("full_path") or entry.get("path") or ""),
                "previous_path": None,
                "is_dir": False,
                "is_excel": False,
                "log_time": str(entry.get("log_time") or ""),
                "message": str(exc),
            }
            self.file_store.append_watch_log(log_date, fallback_entry)


def create_runtime_log_store(config, file_store):
    runtime_log = getattr(config, "runtime_log", None)
    if runtime_log is None or not getattr(runtime_log, "db_enabled", False):
        return RuntimeLogStore(file_store)

    db_config = getattr(getattr(config, "station_config", None), "db", None)
    if db_config is None or not getattr(db_config, "enabled", False):
        return RuntimeLogStore(file_store)

    driver = getattr(db_config, "odbc_driver", None)
    return RuntimeLogStore(
        file_store,
        DbLogStore(db_config, table=runtime_log.db_table, driver=driver),
    )


def build_source_hash(log_type: str, log_date: str, raw_json: str) -> str:
    payload = f"{log_type}\n{log_date}\n{raw_json}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _execute_insert_with_source_hash(
    connection,
    table_name: str,
    normalized: dict[str, Any],
    log_date: str,
    log_type: str,
    run_id: str | None,
    raw_json: str,
    source_hash: str,
) -> None:
    connection.cursor().execute(
        f"""
        IF NOT EXISTS (SELECT 1 FROM {table_name} WHERE source_hash = ?)
        BEGIN
            INSERT INTO {table_name}
              (
                log_time, log_date, log_type, level, status, action, run_id,
                filename, full_path, flow, http_status, retry_count, message, raw_json, source_hash
              )
            VALUES
              (
                COALESCE(TRY_CONVERT(datetime2, ?, 120), SYSDATETIME()),
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
              )
        END
        """,
        source_hash,
        normalized["time"] or None,
        log_date,
        log_type,
        normalized["level"],
        normalized["status"],
        normalized["action"],
        run_id,
        normalized["filename"],
        normalized["path"],
        normalized["flow"],
        normalized["http_status"],
        normalized["retry_count"],
        normalized["message"],
        raw_json,
        source_hash,
    )


def _execute_insert_without_source_hash(
    connection,
    table_name: str,
    normalized: dict[str, Any],
    log_date: str,
    log_type: str,
    run_id: str | None,
    raw_json: str,
) -> None:
    connection.cursor().execute(
        f"""
        INSERT INTO {table_name}
          (
            log_time, log_date, log_type, level, status, action, run_id,
            filename, full_path, flow, http_status, retry_count, message, raw_json
          )
        VALUES
          (
            COALESCE(TRY_CONVERT(datetime2, ?, 120), SYSDATETIME()),
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
          )
        """,
        normalized["time"] or None,
        log_date,
        log_type,
        normalized["level"],
        normalized["status"],
        normalized["action"],
        run_id,
        normalized["filename"],
        normalized["path"],
        normalized["flow"],
        normalized["http_status"],
        normalized["retry_count"],
        normalized["message"],
        raw_json,
    )


def _row_to_log_entry(row: object) -> dict[str, Any]:
    raw = _safe_load_raw_json(row.raw_json)
    action = str(row.action or raw.get("action") or raw.get("event_type") or "")
    status = str(row.status or _status_from_action(action))
    return {
        "log_type": str(row.log_type),
        "log_date": str(row.log_date),
        "level": str(row.level or ("error" if status == "failed" else "info")),
        "status": status,
        "time": str(row.log_time or ""),
        "action": action,
        "filename": str(row.filename or Path(str(row.full_path or "")).name),
        "path": str(row.full_path or ""),
        "flow": str(row.flow or ""),
        "http_status": row.http_status,
        "retry_count": row.retry_count,
        "message": str(row.message or ""),
        "raw": raw,
    }


def _safe_load_raw_json(value: object) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_connection_string(db_config: RuntimeDbConfig, driver: str | None) -> str:
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
        raise ConfigError("runtime_log.db_table 只能包含字母、数字、下划线，并可使用 schema.table 格式")
    return ".".join(f"[{part}]" for part in value.split("."))


def _validated_object_name(table_name: str) -> str:
    value = table_name.strip()
    if not _TABLE_NAME_PATTERN.match(value):
        raise ConfigError("runtime_log.db_table 只能包含字母、数字、下划线，并可使用 schema.table 格式")
    return value
