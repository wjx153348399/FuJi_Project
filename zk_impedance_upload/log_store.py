from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from zk_impedance_upload.exceptions import LogError


class LogStore:
    def __init__(self, log_dir: str | Path) -> None:
        self.log_dir = Path(log_dir)
        self._ready_checked = False

    def ensure_ready(self) -> None:
        if self._ready_checked:
            return
        if self.log_dir.exists() and not self.log_dir.is_dir():
            raise LogError(f"日志路径不是目录: {self.log_dir}")

        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            probe_path = self.log_dir / ".write_test"
            probe_path.write_text("ok", encoding="utf-8")
            probe_path.unlink()
            self._ready_checked = True
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

    def read_recent_logs(
        self,
        *,
        log_type: str = "all",
        limit: int = 200,
        keyword: str = "",
        status: str = "all",
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for log_path in self._iter_log_files(log_type):
            source = "upload" if log_path.name.startswith("upload_log_") else "watch"
            log_date = _extract_log_date(log_path)
            for entry in _iter_jsonl_reverse(log_path):
                normalized = _normalize_log_entry(entry, source, log_date)
                if not _matches_status(normalized, status):
                    continue
                if keyword and keyword.lower() not in json.dumps(normalized, ensure_ascii=False).lower():
                    continue
                entries.append(normalized)
                if len(entries) >= limit:
                    return entries
        return entries

    def build_status_snapshot(self, recent_entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        recent_entries = recent_entries if recent_entries is not None else self.read_recent_logs(limit=1000)
        today = date.today().isoformat()
        today_entries = [entry for entry in recent_entries if entry["log_date"] == today]
        upload_entries = [entry for entry in today_entries if entry["log_type"] == "upload"]
        watch_entries = [entry for entry in today_entries if entry["log_type"] == "watch"]
        return {
            "latest_upload": next((entry for entry in recent_entries if entry["log_type"] == "upload"), None),
            "latest_watch": next((entry for entry in recent_entries if entry["log_type"] == "watch"), None),
            "latest_error": next((entry for entry in recent_entries if entry["level"] == "error"), None),
            "today_success": len([entry for entry in upload_entries if entry["status"] == "success"]),
            "today_failed": len([entry for entry in upload_entries if entry["status"] == "failed"]),
            "today_skipped": len([entry for entry in upload_entries if entry["status"] == "skipped"]),
        }

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

    def _iter_log_files(self, log_type: str) -> list[Path]:
        patterns: list[str]
        if log_type == "upload":
            patterns = ["upload_log_*.jsonl"]
        elif log_type == "watch":
            patterns = ["watch_log_*.jsonl"]
        else:
            patterns = ["upload_log_*.jsonl", "watch_log_*.jsonl"]
        files: list[Path] = []
        for pattern in patterns:
            files.extend(self.log_dir.glob(pattern))
        return sorted(files, key=lambda item: item.name, reverse=True)


def _iter_jsonl_reverse(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    for line in _iter_text_lines_reverse(path):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield value


def _iter_text_lines_reverse(path: Path, chunk_size: int = 64 * 1024) -> Iterable[str]:
    with path.open("rb") as file:
        file.seek(0, 2)
        position = file.tell()
        buffer = b""
        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            file.seek(position)
            data = file.read(read_size)
            parts = (data + buffer).split(b"\n")
            buffer = parts[0]
            for raw_line in reversed(parts[1:]):
                yield raw_line.decode("utf-8", errors="replace")
        if buffer:
            yield buffer.decode("utf-8", errors="replace")


def _normalize_log_entry(entry: dict[str, Any], source: str, log_date: str) -> dict[str, Any]:
    action = str(entry.get("action") or entry.get("event_type") or "")
    status = _status_from_action(action)
    message = str(entry.get("error") or entry.get("message") or entry.get("response_text") or "")
    return {
        "log_type": source,
        "log_date": log_date,
        "level": "error" if status == "failed" or "error" in action else "info",
        "status": status,
        "time": str(entry.get("log_time") or entry.get("file_mtime") or ""),
        "action": action,
        "filename": str(entry.get("filename") or Path(str(entry.get("path") or entry.get("full_path") or "")).name),
        "path": str(entry.get("full_path") or entry.get("path") or ""),
        "flow": str(entry.get("flow") or ""),
        "http_status": entry.get("http_status"),
        "retry_count": entry.get("retry_count"),
        "message": message,
        "raw": entry,
    }


def _status_from_action(action: str) -> str:
    if "success" in action:
        return "success"
    if "failed" in action or "error" in action:
        return "failed"
    if "skipped" in action or "skip" in action:
        return "skipped"
    if "pending" in action:
        return "pending"
    return "info"


def _matches_status(entry: dict[str, Any], status: str) -> bool:
    return status in {"", "all"} or entry["status"] == status or entry["level"] == status


def _extract_log_date(path: Path) -> str:
    stem = path.stem
    for prefix in ("upload_log_", "watch_log_"):
        if stem.startswith(prefix):
            return stem.removeprefix(prefix)
    return ""
