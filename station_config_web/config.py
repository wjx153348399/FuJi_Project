from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zk_impedance_upload.exceptions import ConfigError


@dataclass(frozen=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8088


@dataclass(frozen=True)
class WebDbConfig:
    driver: str = "ODBC Driver 17 for SQL Server"
    host: str = ""
    port: int = 1433
    database: str = ""
    username: str = ""
    password: str = ""
    table: str = "dbo.station_directory_config"
    connect_timeout_seconds: int = 5


@dataclass(frozen=True)
class ShareConfig:
    root: str
    username: str = ""
    password: str = ""


@dataclass(frozen=True)
class LogConfig:
    dir: str


@dataclass(frozen=True)
class AuthConfig:
    username: str = "admin"
    password: str = ""


@dataclass(frozen=True)
class WebConfig:
    server: ServerConfig
    db: WebDbConfig
    share: ShareConfig
    log: LogConfig
    auth: AuthConfig


def load_web_config(path: str | Path = "web_config.json") -> WebConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Web 配置文件不存在: {config_path}")

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Web 配置文件不是有效 JSON: {config_path}") from exc

    return parse_web_config(raw)


def parse_web_config(raw: dict[str, Any]) -> WebConfig:
    server = _optional_section(raw, "server")
    db = _section(raw, "db")
    share = _section(raw, "share")
    log = _optional_section(raw, "log")
    auth = _optional_section(raw, "auth")
    share_root = _required_str(share, "share.root")

    return WebConfig(
        server=ServerConfig(
            host=_optional_str(server, "host", "0.0.0.0"),
            port=_optional_positive_int(server, "port", 8088),
        ),
        db=WebDbConfig(
            driver=_optional_str(db, "driver", "ODBC Driver 17 for SQL Server"),
            host=_required_str(db, "db.host"),
            port=_optional_positive_int(db, "port", 1433),
            database=_required_str(db, "db.database"),
            username=_required_str(db, "db.username"),
            password=_required_str(db, "db.password"),
            table=_optional_str(db, "table", "dbo.station_directory_config"),
            connect_timeout_seconds=_optional_positive_int(db, "connect_timeout_seconds", 5),
        ),
        share=ShareConfig(
            root=share_root,
            username=_optional_str_allow_empty(share, "username", ""),
            password=_optional_str_allow_empty(share, "password", ""),
        ),
        log=LogConfig(dir=_optional_str_allow_empty(log, "dir", str(Path(share_root) / "ZK_LOG"))),
        auth=AuthConfig(
            username=_optional_str(auth, "username", "admin"),
            password=_required_str(auth, "auth.password"),
        ),
    )


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"配置项 {name} 必须是对象")
    return value


def _optional_section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"配置项 {name} 必须是对象")
    return value


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
        raise ConfigError(f"閰嶇疆椤?{key} 蹇呴』鏄瓧绗︿覆")
    return value


def _optional_positive_int(section: dict[str, Any], key: str, default: int) -> int:
    value = section.get(key, default)
    if not isinstance(value, int) or value <= 0:
        raise ConfigError(f"配置项 {key} 必须是大于 0 的整数")
    return value
