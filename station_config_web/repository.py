from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from station_config_web.config import WebConfig, WebDbConfig
from zk_impedance_upload.exceptions import ConfigError


_TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


@dataclass(frozen=True)
class StationDirectoryRow:
    id: int
    flow: str
    station_name: str | None
    directory_path: str
    enabled: bool
    sort_order: int
    remark: str | None
    created_by: str | None
    created_at: str
    updated_by: str | None
    updated_at: str
    full_path: str
    path_checked: bool
    path_exists: bool
    path_is_dir: bool
    path_checked_at: str | None
    path_check_message: str | None
    flow_state: str
    flow_label: str
    upload_field_state: str
    upload_field_label: str


@dataclass(frozen=True)
class StationDirectoryInput:
    flow: str
    station_name: str | None
    directory_path: str
    enabled: bool
    sort_order: int
    remark: str | None
    updated_by: str | None = "web"


@dataclass(frozen=True)
class DirectoryPathStatus:
    directory_path: str
    full_path: str
    exists: bool
    is_dir: bool
    message: str


class StationDirectoryRepository:
    def __init__(self, config: WebConfig) -> None:
        self.config = config

    def list_configs(self, status: str = "all", keyword: str = "") -> list[StationDirectoryRow]:
        where_clauses: list[str] = []
        params: list[object] = []
        if status == "enabled":
            where_clauses.append("enabled = 1")
        elif status == "disabled":
            where_clauses.append("enabled = 0")
        elif status == "pending_flow":
            where_clauses.append("(flow IS NULL OR LTRIM(RTRIM(flow)) = '')")
        elif status != "all":
            raise ConfigError("status must be one of: all, enabled, disabled, pending_flow")

        keyword = keyword.strip()
        if keyword:
            where_clauses.append(
                "(flow LIKE ? OR station_name LIKE ? OR directory_path LIKE ? OR remark LIKE ?)"
            )
            pattern = f"%{keyword}%"
            params.extend([pattern, pattern, pattern, pattern])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        table_name = _validated_table_name(self.config.db.table)
        sql = f"""
            SELECT
              id,
              flow,
              station_name,
              directory_path,
              enabled,
              sort_order,
              remark,
              created_by,
              CONVERT(varchar(19), created_at, 120) AS created_at,
              updated_by,
              CONVERT(varchar(19), updated_at, 120) AS updated_at,
              path_checked,
              path_exists,
              path_is_dir,
              CONVERT(varchar(19), path_checked_at, 120) AS path_checked_at,
              path_check_message
            FROM {table_name}
            {where_sql}
            ORDER BY enabled DESC, sort_order ASC, id ASC
        """
        with _connect(self.config.db) as connection:
            rows = connection.cursor().execute(sql, *params).fetchall()
        return [self._build_row(row) for row in rows]

    def get_config(self, config_id: int) -> StationDirectoryRow | None:
        table_name = _validated_table_name(self.config.db.table)
        sql = f"""
            SELECT
              id,
              flow,
              station_name,
              directory_path,
              enabled,
              sort_order,
              remark,
              created_by,
              CONVERT(varchar(19), created_at, 120) AS created_at,
              updated_by,
              CONVERT(varchar(19), updated_at, 120) AS updated_at,
              path_checked,
              path_exists,
              path_is_dir,
              CONVERT(varchar(19), path_checked_at, 120) AS path_checked_at,
              path_check_message
            FROM {table_name}
            WHERE id = ?
        """
        with _connect(self.config.db) as connection:
            row = connection.cursor().execute(sql, int(config_id)).fetchone()
        return self._build_row(row) if row else None

    def create_config(self, data: StationDirectoryInput) -> None:
        clean_data = validate_station_directory_input(data)
        self.ensure_directory_path_unique(clean_data.directory_path)
        table_name = _validated_table_name(self.config.db.table)
        sql = f"""
            INSERT INTO {table_name}
              (flow, station_name, directory_path, enabled, sort_order, remark, created_by, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        with _connect(self.config.db) as connection:
            connection.cursor().execute(
                sql,
                clean_data.flow,
                clean_data.station_name,
                clean_data.directory_path,
                1 if clean_data.enabled else 0,
                clean_data.sort_order,
                clean_data.remark,
                clean_data.updated_by,
                clean_data.updated_by,
            )
            connection.commit()

    def update_config(self, config_id: int, data: StationDirectoryInput) -> None:
        clean_data = validate_station_directory_input(data)
        self.ensure_directory_path_unique(clean_data.directory_path, exclude_id=config_id)
        table_name = _validated_table_name(self.config.db.table)
        sql = f"""
            UPDATE {table_name}
            SET
              flow = ?,
              station_name = ?,
              directory_path = ?,
              enabled = ?,
              sort_order = ?,
              remark = ?,
              updated_by = ?
            WHERE id = ?
        """
        with _connect(self.config.db) as connection:
            cursor = connection.cursor()
            cursor.execute(
                sql,
                clean_data.flow,
                clean_data.station_name,
                clean_data.directory_path,
                1 if clean_data.enabled else 0,
                clean_data.sort_order,
                clean_data.remark,
                clean_data.updated_by,
                int(config_id),
            )
            if getattr(cursor, "rowcount", 1) == 0:
                raise ConfigError(f"配置不存在: {config_id}")
            connection.commit()

    def set_enabled(self, config_id: int, enabled: bool, updated_by: str | None = "web") -> None:
        table_name = _validated_table_name(self.config.db.table)
        sql = f"UPDATE {table_name} SET enabled = ?, updated_by = ? WHERE id = ?"
        with _connect(self.config.db) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, 1 if enabled else 0, _clean_optional_text(updated_by), int(config_id))
            if getattr(cursor, "rowcount", 1) == 0:
                raise ConfigError(f"配置不存在: {config_id}")
            connection.commit()

    def ensure_directory_path_unique(self, directory_path: str, exclude_id: int | None = None) -> None:
        table_name = _validated_table_name(self.config.db.table)
        params: list[Any] = [directory_path]
        exclude_sql = ""
        if exclude_id is not None:
            exclude_sql = " AND id <> ?"
            params.append(int(exclude_id))
        sql = f"SELECT TOP 1 id FROM {table_name} WHERE directory_path = ?{exclude_sql}"
        with _connect(self.config.db) as connection:
            row = connection.cursor().execute(sql, *params).fetchone()
        if row:
            raise ConfigError(f"目录路径已存在，不能重复配置: {directory_path}")

    def check_directory(self, directory_path: str) -> DirectoryPathStatus:
        clean_path = validate_relative_directory_path(directory_path)
        full_path = Path(self.config.share.root) / clean_path
        exists = full_path.exists()
        is_dir = full_path.is_dir() if exists else False
        if is_dir:
            message = f"目录存在: {full_path}"
        elif exists:
            message = f"路径存在但不是目录: {full_path}"
        else:
            message = f"目录不存在: {full_path}"
        return DirectoryPathStatus(
            directory_path=clean_path,
            full_path=str(full_path),
            exists=exists,
            is_dir=is_dir,
            message=message,
        )

    def check_and_record_directory(self, directory_path: str) -> DirectoryPathStatus:
        status = self.check_directory(directory_path)
        table_name = _validated_table_name(self.config.db.table)
        sql = f"""
            UPDATE {table_name}
            SET
              path_checked = 1,
              path_exists = ?,
              path_is_dir = ?,
              path_checked_at = GETDATE(),
              path_check_message = ?
            WHERE directory_path = ?
        """
        with _connect(self.config.db) as connection:
            cursor = connection.cursor()
            cursor.execute(
                sql,
                1 if status.exists else 0,
                1 if status.is_dir else 0,
                status.message,
                status.directory_path,
            )
            if getattr(cursor, "rowcount", 1) == 0:
                raise ConfigError(f"目录配置不存在，无法保存检测结果: {status.directory_path}")
            connection.commit()
        return status

    def _build_row(self, row: object) -> StationDirectoryRow:
        full_path = Path(self.config.share.root) / row.directory_path
        return StationDirectoryRow(
            id=int(row.id),
            flow=str(row.flow),
            station_name=row.station_name,
            directory_path=str(row.directory_path),
            enabled=bool(row.enabled),
            sort_order=int(row.sort_order),
            remark=row.remark,
            created_by=row.created_by,
            created_at=str(row.created_at),
            updated_by=row.updated_by,
            updated_at=str(row.updated_at),
            full_path=str(full_path),
            path_checked=bool(row.path_checked),
            path_exists=bool(row.path_exists),
            path_is_dir=bool(row.path_is_dir),
            path_checked_at=str(row.path_checked_at) if row.path_checked_at else None,
            path_check_message=row.path_check_message,
            flow_state=_flow_state(str(row.flow)),
            flow_label=_flow_label(str(row.flow)),
            upload_field_state=_upload_field_state(str(row.flow)),
            upload_field_label=_upload_field_label(str(row.flow)),
        )


def validate_station_directory_input(data: StationDirectoryInput) -> StationDirectoryInput:
    directory_path = validate_relative_directory_path(data.directory_path)
    flow = data.flow.strip()
    station_name = _clean_optional_text(data.station_name)
    remark = _clean_optional_text(data.remark)
    updated_by = _clean_optional_text(data.updated_by) or "web"
    return StationDirectoryInput(
        flow=flow,
        station_name=station_name,
        directory_path=directory_path,
        enabled=bool(data.enabled),
        sort_order=int(data.sort_order),
        remark=remark,
        updated_by=updated_by,
    )


def validate_relative_directory_path(directory_path: str) -> str:
    value = directory_path.strip().replace("/", "\\")
    if not value:
        raise ConfigError("目录路径不能为空")
    if value.startswith("\\\\"):
        raise ConfigError("目录路径请填写共享盘根目录下的相对路径，不要填写完整 UNC 路径")
    if re.match(r"^[A-Za-z]:\\", value):
        raise ConfigError("目录路径请填写共享盘根目录下的相对路径，不要填写本机盘符路径")
    if "\x00" in value:
        raise ConfigError("目录路径包含非法字符")
    parts = [part for part in value.split("\\") if part]
    if any(part == ".." for part in parts):
        raise ConfigError("目录路径不能包含 ..")
    return "\\".join(parts)


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    clean_value = value.strip()
    return clean_value or None


def _flow_state(flow: str) -> str:
    value = flow.strip()
    if not value:
        return "pending"
    if value.upper() in {"AFC", "AFX", "JXN", "LXD", "OUTER", "ZGL"}:
        return "suspect"
    return "ready"


def _flow_label(flow: str) -> str:
    value = flow.strip()
    if not value:
        return "待确认"
    if _flow_state(value) == "suspect":
        return f"{value}（疑似显示名）"
    return value


def _upload_field_state(flow: str) -> str:
    return "without_flow" if not flow.strip() else "with_flow"


def _upload_field_label(flow: str) -> str:
    return "不传 flow" if not flow.strip() else "传 flow"


def _connect(db_config: WebDbConfig):
    try:
        import pyodbc
    except ImportError as exc:  # pragma: no cover - depends on deployment environment
        raise ConfigError("Web 工具需要安装 pyodbc，请先执行 pip install pyodbc") from exc

    return pyodbc.connect(
        _build_connection_string(db_config),
        timeout=db_config.connect_timeout_seconds,
    )


def _build_connection_string(db_config: WebDbConfig) -> str:
    return (
        f"DRIVER={{{db_config.driver}}};"
        f"SERVER={db_config.host},{db_config.port};"
        f"DATABASE={db_config.database};"
        f"UID={db_config.username};"
        f"PWD={db_config.password};"
        "TrustServerCertificate=yes;"
    )


def _validated_table_name(table_name: str) -> str:
    value = table_name.strip()
    if not _TABLE_NAME_PATTERN.match(value):
        raise ConfigError("db.table 只能包含字母、数字、下划线，并可使用 schema.table 格式")
    return ".".join(f"[{part}]" for part in value.split("."))
