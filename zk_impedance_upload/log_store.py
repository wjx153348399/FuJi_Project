from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zk_impedance_upload.exceptions import LogError


class LogStore:
    def __init__(self, log_dir: str | Path) -> None:
        self.log_dir = Path(log_dir)

    def ensure_ready(self) -> None:
        if self.log_dir.exists() and not self.log_dir.is_dir():
            raise LogError(f"日志路径不是目录: {self.log_dir}")

        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            probe_path = self.log_dir / ".write_test"
            probe_path.write_text("ok", encoding="utf-8")
            probe_path.unlink()
        except OSError as exc:
            raise LogError(f"日志目录不可写: {self.log_dir}") from exc

    def append_upload_log(self, log_date: str, entry: dict[str, Any]) -> Path:
        self.ensure_ready()
        log_path = self.log_dir / f"upload_log_{log_date}.jsonl"
        with log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
            file.write("\n")
        return log_path

    def append_watch_log(self, log_date: str, entry: dict[str, Any]) -> Path:
        self.ensure_ready()
        log_path = self.log_dir / f"watch_log_{log_date}.jsonl"
        with log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
            file.write("\n")
        return log_path

    def write_summary(self, timestamp: str, summary: dict[str, Any]) -> Path:
        self.ensure_ready()
        summary_path = self.log_dir / f"summary_{timestamp}.json"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary_path

    def write_watch_summary(self, timestamp: str, summary: dict[str, Any]) -> Path:
        self.ensure_ready()
        summary_path = self.log_dir / f"watch_summary_{timestamp}.json"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary_path

    def load_uploaded_fingerprints(self) -> dict[str, Any]:
        path = self._fingerprints_path()
        if not path.exists():
            return {}

        try:
            content = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise LogError(f"成功上传历史不是有效 JSON: {path}") from exc

        if not isinstance(content, dict):
            raise LogError(f"成功上传历史格式错误: {path}")
        return content

    def save_uploaded_fingerprint(self, key: str, record: dict[str, Any]) -> Path:
        self.ensure_ready()
        fingerprints = self.load_uploaded_fingerprints()
        fingerprints[key] = record
        path = self._fingerprints_path()
        path.write_text(
            json.dumps(fingerprints, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def load_uploaded_business_keys(self) -> dict[str, Any]:
        path = self._business_keys_path()
        if not path.exists():
            return {}

        try:
            content = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise LogError(f"业务键历史不是有效 JSON: {path}") from exc

        if not isinstance(content, dict):
            raise LogError(f"业务键历史格式错误: {path}")
        return content

    def save_uploaded_business_key(self, key: str, record: dict[str, Any]) -> Path:
        self.ensure_ready()
        business_keys = self.load_uploaded_business_keys()
        business_keys[key] = record
        path = self._business_keys_path()
        path.write_text(
            json.dumps(business_keys, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def _fingerprints_path(self) -> Path:
        return self.log_dir / "uploaded_file_fingerprints.json"

    def _business_keys_path(self) -> Path:
        return self.log_dir / "uploaded_business_keys.json"
