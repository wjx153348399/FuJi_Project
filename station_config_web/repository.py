from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from station_config_web.config import WebConfig, WebDbConfig
from zk_impedance_upload.exceptions import ConfigError


_TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


@dataclass(frozen=True)
class StationDirectoryRow:
    id: int
    station_code: str
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
    path_exists: bool
    path_is_dir: bool


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
        elif status != "all":
            raise ConfigError("status must be one of: all, enabled, disabled")

        keyword = keyword.strip()
        if keyword:
            where_clauses.append(
                "(station_code LIKE ? OR station_name LIKE ? OR directory_path LIKE ? OR remark LIKE ?)"
            )
            pattern = f"%{keyword}%"
            params.extend([pattern, pattern, pattern, pattern])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        table_name = _validated_table_name(self.config.db.table)
        sql = f"""
            SELECT
              id,
              station_code,
              station_name,
              directory_path,
              enabled,
              sort_order,
              remark,
              created_by,
              CONVERT(varchar(19), created_at, 120) AS created_at,
              updated_by,
              CONVERT(varchar(19), updated_at, 120) AS updated_at
            FROM {table_name}
            {where_sql}
            ORDER BY enabled DESC, sort_order ASC, id ASC
        """
        with _connect(self.config.db) as connection:
            rows = connection.cursor().execute(sql, *params).fetchall()
        return [self._build_row(row) for row in rows]

    def _build_row(self, row: object) -> StationDirectoryRow:
        full_path = Path(self.config.share.root) / row.directory_path
        path_exists = full_path.exists()
        return StationDirectoryRow(
            id=int(row.id),
            station_code=str(row.station_code),
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
            path_exists=path_exists,
            path_is_dir=full_path.is_dir() if path_exists else False,
        )


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
