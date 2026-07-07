from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from zk_impedance_upload.date_window import SHANGHAI_TZ


STATUS_FILE_NAME = "service_status.json"


def write_service_status(log_dir: str | Path, status: dict[str, Any]) -> Path:
    path = service_status_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": _now_text(),
        **status,
    }
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    return path


def read_service_status(log_dir: str | Path) -> dict[str, Any]:
    path = service_status_path(log_dir)
    if not path.exists():
        return {
            "state": "unknown",
            "message": "service status file not found",
            "updated_at": "",
            "watcher_restart_count": 0,
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "state": "error",
            "message": str(exc),
            "updated_at": "",
            "watcher_restart_count": 0,
        }
    if not isinstance(value, dict):
        return {
            "state": "error",
            "message": "service status file format error",
            "updated_at": "",
            "watcher_restart_count": 0,
        }
    return value


def service_status_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / STATUS_FILE_NAME


def _now_text() -> str:
    return datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")
