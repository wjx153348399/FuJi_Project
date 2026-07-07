from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zk_impedance_upload.exceptions import ConfigError


@dataclass(frozen=True)
class ShareConfig:
    root: str
    username: str
    password: str


@dataclass(frozen=True)
class LogConfig:
    dir: str


@dataclass(frozen=True)
class UploadConfig:
    url: str
    schedule_time: str = "08:00"
    day_offset: int = 1
    max_upload_files: int | None = None
    dry_run: bool = False
    timeout_seconds: int = 300
    retry_count: int = 2


@dataclass(frozen=True)
class ScanTargetConfig:
    flow: str
    dir: str
    enabled: bool = True


@dataclass(frozen=True)
class ScanConfig:
    recursive: bool = True
    extensions: list[str] | None = None
    exclude_prefixes: list[str] | None = None
    exclude_dirs: list[str] | None = None
    target_dirs: list[str] | None = None
    targets: list[ScanTargetConfig] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "extensions", self.extensions or [".xls", ".xlsx"])
        object.__setattr__(self, "exclude_prefixes", self.exclude_prefixes or ["~$"])
        object.__setattr__(self, "exclude_dirs", self.exclude_dirs or [])
        object.__setattr__(self, "target_dirs", self.target_dirs or [])
        object.__setattr__(self, "targets", self.targets or [])


@dataclass(frozen=True)
class StationDbConfig:
    enabled: bool = False
    driver: str = "sqlserver"
    odbc_driver: str = "ODBC Driver 17 for SQL Server"
    host: str = ""
    port: int = 1433
    database: str = ""
    username: str = ""
    password: str = ""
    table: str = "station_directory_config"
    connect_timeout_seconds: int = 5
    query_timeout_seconds: int = 10


@dataclass(frozen=True)
class StationConfig:
    source: str = "json"
    on_db_error: str = "raise"
    db: StationDbConfig = field(default_factory=StationDbConfig)


@dataclass(frozen=True)
class WatchConfig:
    enabled: bool = False
    notice_mode: str = "log_and_daily_summary"
    poll_interval_seconds: int = 5
    debounce_seconds: int = 5
    stable_check_seconds: int = 2
    stable_check_attempts: int = 3
    queue_max_workers: int = 1


@dataclass(frozen=True)
class AppConfig:
    share: ShareConfig
    log: LogConfig
    upload: UploadConfig
    scan: ScanConfig
    watch: WatchConfig
    station_config: StationConfig = field(default_factory=StationConfig)


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"配置文件不存在: {config_path}")

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"配置文件不是有效 JSON: {config_path}") from exc

    return parse_config(raw)


def parse_config(raw: dict[str, Any]) -> AppConfig:
    share = _section(raw, "share")
    log = _section(raw, "log")
    upload = _section(raw, "upload")
    scan = _section(raw, "scan")
    watch = raw.get("watch", {})
    if not isinstance(watch, dict):
        raise ConfigError("配置项 watch 必须是对象")
    station_config = raw.get("station_config", {})
    if not isinstance(station_config, dict):
        raise ConfigError("配置项 station_config 必须是对象")

    return AppConfig(
        share=ShareConfig(
            root=_required_str(share, "share.root"),
            username=_required_str(share, "share.username"),
            password=_required_str(share, "share.password"),
        ),
        log=LogConfig(dir=_required_str(log, "log.dir")),
        upload=UploadConfig(
            url=_required_str(upload, "upload.url"),
            schedule_time=_optional_str(upload, "schedule_time", "08:00"),
            day_offset=_optional_int(upload, "day_offset", 1),
            max_upload_files=_optional_nullable_int(upload, "max_upload_files"),
            dry_run=_optional_bool(upload, "dry_run", False),
            timeout_seconds=_optional_int(upload, "timeout_seconds", 300),
            retry_count=_optional_int(upload, "retry_count", 2),
        ),
        scan=ScanConfig(
            recursive=_optional_bool(scan, "recursive", True),
            extensions=_optional_str_list(scan, "extensions", [".xls", ".xlsx"]),
            exclude_prefixes=_optional_str_list(scan, "exclude_prefixes", ["~$"]),
            exclude_dirs=_optional_str_list(scan, "exclude_dirs", []),
            target_dirs=_optional_str_list(scan, "target_dirs", []),
            targets=_optional_scan_targets(scan),
        ),
        watch=WatchConfig(
            enabled=_optional_bool(watch, "enabled", False),
            notice_mode=_optional_str(watch, "notice_mode", "log_and_daily_summary"),
            poll_interval_seconds=_optional_positive_int(watch, "poll_interval_seconds", 5),
            debounce_seconds=_optional_positive_int(watch, "debounce_seconds", 5),
            stable_check_seconds=_optional_positive_int(watch, "stable_check_seconds", 2),
            stable_check_attempts=_optional_positive_int(watch, "stable_check_attempts", 3),
            queue_max_workers=_optional_positive_int(watch, "queue_max_workers", 1),
        ),
        station_config=_parse_station_config(station_config),
    )


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"配置项 {name} 必须是对象")
    return value


def _optional_scan_targets(section: dict[str, Any]) -> list[ScanTargetConfig]:
    value = section.get("targets", [])
    if not isinstance(value, list):
        raise ConfigError("scan.targets must be a list")

    targets: list[ScanTargetConfig] = []
    seen_dirs: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ConfigError(f"scan.targets[{index}] must be an object")

        flow = item.get("flow", "")
        if not isinstance(flow, str):
            raise ConfigError(f"scan.targets[{index}].flow must be a string")

        target_dir = item.get("dir")
        if not isinstance(target_dir, str) or not target_dir.strip():
            raise ConfigError(f"scan.targets[{index}].dir is required")

        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ConfigError(f"scan.targets[{index}].enabled must be a boolean")

        normalized_dir = target_dir.strip().replace("/", "\\").rstrip("\\")
        lookup_key = normalized_dir.lower()
        if lookup_key in seen_dirs:
            raise ConfigError(f"scan.targets contains duplicate dir: {normalized_dir}")
        seen_dirs.add(lookup_key)

        targets.append(
            ScanTargetConfig(
                flow=flow.strip(),
                dir=normalized_dir,
                enabled=enabled,
            )
        )

    return targets


def _parse_station_config(section: dict[str, Any]) -> StationConfig:
    source = _optional_str(section, "source", "json")
    if source not in {"json", "db", "db_then_json"}:
        raise ConfigError("station_config.source must be one of: json, db, db_then_json")

    on_db_error = _optional_str(section, "on_db_error", "raise")
    if on_db_error not in {"raise", "fallback_to_json"}:
        raise ConfigError("station_config.on_db_error must be one of: raise, fallback_to_json")

    db = section.get("db", {})
    if not isinstance(db, dict):
        raise ConfigError("配置项 station_config.db 必须是对象")

    return StationConfig(
        source=source,
        on_db_error=on_db_error,
        db=StationDbConfig(
            enabled=_optional_bool(db, "enabled", False),
            driver=_optional_str(db, "driver", "sqlserver"),
            odbc_driver=_optional_str(db, "odbc_driver", "ODBC Driver 17 for SQL Server"),
            host=_optional_str_allow_empty(db, "host", ""),
            port=_optional_positive_int(db, "port", 1433),
            database=_optional_str_allow_empty(db, "database", ""),
            username=_optional_str_allow_empty(db, "username", ""),
            password=_optional_str_allow_empty(db, "password", ""),
            table=_optional_str(db, "table", "station_directory_config"),
            connect_timeout_seconds=_optional_positive_int(db, "connect_timeout_seconds", 5),
            query_timeout_seconds=_optional_positive_int(db, "query_timeout_seconds", 10),
        ),
    )


def _required_str(section: dict[str, Any], dotted_name: str) -> str:
    key = dotted_name.rsplit(".", 1)[-1]
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"缺少必填配置项: {dotted_name}")
    return value


def _optional_str(section: dict[str, Any], key: str, default: str) -> str:
    value = section.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"配置项 {key} 必须是非空字符串")
    return value


def _optional_str_allow_empty(section: dict[str, Any], key: str, default: str) -> str:
    value = section.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"配置项 {key} 必须是字符串")
    return value


def _optional_int(section: dict[str, Any], key: str, default: int) -> int:
    value = section.get(key, default)
    if not isinstance(value, int):
        raise ConfigError(f"配置项 {key} 必须是整数")
    return value


def _optional_positive_int(section: dict[str, Any], key: str, default: int) -> int:
    value = _optional_int(section, key, default)
    if value <= 0:
        raise ConfigError(f"配置项 {key} 必须大于 0")
    return value


def _optional_nullable_int(section: dict[str, Any], key: str) -> int | None:
    value = section.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ConfigError(f"配置项 {key} 必须是整数或 null")
    return value


def _optional_bool(section: dict[str, Any], key: str, default: bool) -> bool:
    value = section.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"配置项 {key} 必须是布尔值")
    return value


def _optional_str_list(section: dict[str, Any], key: str, default: list[str]) -> list[str]:
    value = section.get(key, default)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"配置项 {key} 必须是字符串数组")
    return value
