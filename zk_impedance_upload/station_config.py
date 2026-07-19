from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import PureWindowsPath
import re
from typing import Protocol

from zk_impedance_upload.config import AppConfig, ScanConfig, ScanTargetConfig, StationDbConfig
from zk_impedance_upload.exceptions import ConfigError


_FLOW_PATTERN = re.compile(r"^A\d{3}$", re.IGNORECASE)
_TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


@dataclass(frozen=True)
class EffectiveScanConfig:
    scan: ScanConfig
    requested_source: str
    effective_source: str
    fallback_reason: str | None = None

    @property
    def target_count(self) -> int:
        return len([target for target in self.scan.targets or [] if target.enabled])


class StationTargetRepository(Protocol):
    def load_targets(self, db_config: StationDbConfig) -> list[ScanTargetConfig]:
        ...


class SqlServerStationTargetRepository:
    def load_targets(self, db_config: StationDbConfig) -> list[ScanTargetConfig]:
        if db_config.driver != "sqlserver":
            raise ConfigError(f"station_config.db.driver 仅支持 sqlserver，当前为: {db_config.driver}")
        _validate_db_config(db_config)
        table_name = _validated_table_name(db_config.table)

        try:
            import pyodbc
        except ImportError as exc:  # pragma: no cover - depends on deployment environment
            raise ConfigError("启用 SQL Server 配置需要安装 pyodbc，请先执行 pip install pyodbc") from exc

        connection = pyodbc.connect(
            _build_connection_string(db_config),
            timeout=db_config.connect_timeout_seconds,
        )
        try:
            cursor = connection.cursor()
            try:
                cursor.timeout = db_config.query_timeout_seconds
            except AttributeError:  # pragma: no cover - pyodbc compatibility
                pass
            rows = cursor.execute(
                f"""
                SELECT flow, directory_path
                FROM {table_name}
                WHERE enabled = 1
                ORDER BY sort_order ASC, id ASC
                """
            ).fetchall()
        finally:
            connection.close()

        targets: list[ScanTargetConfig] = []
        for row in rows:
            targets.append(
                ScanTargetConfig(
                    flow=str(row.flow),
                    dir=str(row.directory_path),
                    enabled=True,
                )
            )
        return targets


def build_effective_scan_config(
    app_config: AppConfig,
    repository: StationTargetRepository | None = None,
) -> EffectiveScanConfig:
    station_config = app_config.station_config
    if station_config.source == "json":
        return EffectiveScanConfig(
            scan=_with_validated_targets(app_config.scan),
            requested_source="json",
            effective_source="json",
        )

    repo = repository or SqlServerStationTargetRepository()
    if station_config.source == "db":
        targets = _load_db_targets_or_raise(station_config.db, repo)
        if not targets:
            raise ConfigError("数据库未返回任何启用的工站目录配置")
        return EffectiveScanConfig(
            scan=_scan_with_targets(app_config.scan, targets),
            requested_source="db",
            effective_source="db",
        )

    if station_config.source == "db_then_json":
        try:
            targets = _load_db_targets_or_raise(station_config.db, repo)
            if targets:
                return EffectiveScanConfig(
                    scan=_scan_with_targets(app_config.scan, targets),
                    requested_source="db_then_json",
                    effective_source="db",
                )
            fallback_reason = "database returned no enabled targets"
        except ConfigError as exc:
            if station_config.on_db_error != "fallback_to_json":
                raise
            fallback_reason = str(exc)
        return EffectiveScanConfig(
            scan=_with_validated_targets(app_config.scan),
            requested_source="db_then_json",
            effective_source="json",
            fallback_reason=fallback_reason,
        )

    raise ConfigError(f"不支持的 station_config.source: {station_config.source}")


def _load_db_targets_or_raise(
    db_config: StationDbConfig,
    repository: StationTargetRepository,
) -> list[ScanTargetConfig]:
    _validate_db_config(db_config)
    targets = repository.load_targets(db_config)
    return _validate_targets(targets)


def _scan_with_targets(scan_config: ScanConfig, targets: list[ScanTargetConfig]) -> ScanConfig:
    return replace(scan_config, target_dirs=[], targets=_validate_targets(targets))


def _with_validated_targets(scan_config: ScanConfig) -> ScanConfig:
    if scan_config.targets:
        return replace(scan_config, targets=_validate_targets(scan_config.targets))
    return scan_config


def _validate_targets(targets: list[ScanTargetConfig]) -> list[ScanTargetConfig]:
    normalized_targets: list[ScanTargetConfig] = []
    seen_dirs: set[str] = set()
    for index, target in enumerate(targets):
        flow = target.flow.strip().upper()
        if not flow:
            raise ConfigError(f"station target[{index}].flow is required for enabled upload")
        if not _FLOW_PATTERN.match(flow):
            raise ConfigError(f"station target[{index}].flow must be a station code like A032")

        target_dir = _normalize_directory(target.dir)
        if not target_dir:
            raise ConfigError(f"station target[{index}].dir is required")
        if _is_absolute_windows_path(target_dir):
            raise ConfigError(f"station target[{index}].dir must be relative to share.root")

        lookup_key = target_dir.lower()
        if lookup_key in seen_dirs:
            raise ConfigError(f"Duplicate station directory config: {target_dir}")
        seen_dirs.add(lookup_key)
        normalized_targets.append(
            ScanTargetConfig(
                flow=flow,
                dir=target_dir,
                enabled=target.enabled,
            )
        )
    return normalized_targets


def _validate_db_config(db_config: StationDbConfig) -> None:
    if not db_config.enabled:
        raise ConfigError("station_config.db.enabled must be true when using database station config")
    if db_config.driver != "sqlserver":
        raise ConfigError(f"station_config.db.driver 仅支持 sqlserver，当前为: {db_config.driver}")
    for key, value in {
        "host": db_config.host,
        "database": db_config.database,
        "username": db_config.username,
        "password": db_config.password,
    }.items():
        if not value.strip():
            raise ConfigError(f"station_config.db.{key} is required when using database station config")
    _validated_table_name(db_config.table)


def _validated_table_name(table_name: str) -> str:
    value = table_name.strip()
    if not _TABLE_NAME_PATTERN.match(value):
        raise ConfigError("station_config.db.table 只能包含字母、数字、下划线，并可使用 schema.table 格式")
    return ".".join(f"[{part}]" for part in value.split("."))


def _build_connection_string(db_config: StationDbConfig) -> str:
    return (
        f"DRIVER={{{db_config.odbc_driver}}};"
        f"SERVER={db_config.host},{db_config.port};"
        f"DATABASE={db_config.database};"
        f"UID={db_config.username};"
        f"PWD={db_config.password};"
        "TrustServerCertificate=yes;"
    )


def _normalize_directory(value: str) -> str:
    return value.strip().replace("/", "\\").rstrip("\\")


def _is_absolute_windows_path(value: str) -> bool:
    path = PureWindowsPath(value)
    return path.is_absolute() or bool(path.drive)
