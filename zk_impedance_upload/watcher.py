from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import time
from typing import Callable

from zk_impedance_upload.config import AppConfig, ScanConfig
from zk_impedance_upload.date_window import SHANGHAI_TZ
from zk_impedance_upload.log_store import LogStore
from zk_impedance_upload.share_auth import ensure_share_access


@dataclass(frozen=True)
class WatchEntry:
    path: Path
    is_dir: bool
    size: int
    mtime_ns: int

    @property
    def key(self) -> str:
        return str(self.path).replace("/", "\\").lower()

    @property
    def rename_signature(self) -> tuple[bool, int, int]:
        return (self.is_dir, self.size, self.mtime_ns)


@dataclass
class WatchSnapshot:
    entries: dict[str, WatchEntry] = field(default_factory=dict)
    missing_dirs: list[Path] = field(default_factory=list)
    failed_dirs: list[Path] = field(default_factory=list)


@dataclass(frozen=True)
class WatchEvent:
    event_type: str
    path: Path
    is_dir: bool
    is_excel: bool
    previous_path: Path | None = None


class EventDebouncer:
    def __init__(self, debounce_seconds: int) -> None:
        self.debounce_seconds = debounce_seconds
        self._last_emitted: dict[tuple[str, str, str], float] = {}

    def filter(self, events: list[WatchEvent], now_monotonic: float | None = None) -> list[WatchEvent]:
        current = time.monotonic() if now_monotonic is None else now_monotonic
        kept: list[WatchEvent] = []
        for event in events:
            key = (
                event.event_type,
                _normalize_key(event.path),
                _normalize_key(event.previous_path) if event.previous_path else "",
            )
            last_emitted = self._last_emitted.get(key)
            if last_emitted is not None and current - last_emitted < self.debounce_seconds:
                continue
            self._last_emitted[key] = current
            kept.append(event)
        return kept


def collect_watch_snapshot(root: str | Path, scan_config: ScanConfig) -> WatchSnapshot:
    root_path = Path(root)
    snapshot = WatchSnapshot()

    for target_path in _iter_watch_targets(root_path, scan_config):
        if not target_path.exists():
            snapshot.missing_dirs.append(target_path)
            continue
        if not target_path.is_dir():
            snapshot.failed_dirs.append(target_path)
            continue
        _walk_directory(target_path, scan_config, snapshot)

    return snapshot


def diff_watch_snapshots(previous: WatchSnapshot, current: WatchSnapshot) -> list[WatchEvent]:
    previous_keys = set(previous.entries)
    current_keys = set(current.entries)

    created_keys = current_keys - previous_keys
    deleted_keys = previous_keys - current_keys
    common_keys = previous_keys & current_keys

    renamed_events, consumed_created, consumed_deleted = _build_renamed_events(
        previous.entries,
        current.entries,
        created_keys,
        deleted_keys,
    )

    events: list[WatchEvent] = list(renamed_events)

    for key in sorted(created_keys - consumed_created):
        entry = current.entries[key]
        events.append(
            WatchEvent(
                event_type="watch_created",
                path=entry.path,
                is_dir=entry.is_dir,
                is_excel=_is_excel_path(entry.path),
            )
        )

    for key in sorted(deleted_keys - consumed_deleted):
        entry = previous.entries[key]
        events.append(
            WatchEvent(
                event_type="watch_deleted",
                path=entry.path,
                is_dir=entry.is_dir,
                is_excel=_is_excel_path(entry.path),
            )
        )

    for key in sorted(common_keys):
        old_entry = previous.entries[key]
        new_entry = current.entries[key]
        if old_entry.is_dir or new_entry.is_dir:
            continue
        if (old_entry.size, old_entry.mtime_ns) != (new_entry.size, new_entry.mtime_ns):
            events.append(
                WatchEvent(
                    event_type="watch_modified",
                    path=new_entry.path,
                    is_dir=False,
                    is_excel=_is_excel_path(new_entry.path),
                )
            )

    return events


def format_watch_log_entry(event: WatchEvent, log_time: str) -> dict[str, object]:
    return {
        "event_type": event.event_type,
        "path": str(event.path),
        "previous_path": str(event.previous_path) if event.previous_path else None,
        "is_dir": event.is_dir,
        "is_excel": event.is_excel,
        "log_time": log_time,
    }


def build_watch_summary(log_store: LogStore, log_date: str, summary_timestamp: str) -> Path:
    log_path = log_store.log_dir / f"watch_log_{log_date}.jsonl"
    stats: dict[str, int] = {
        "watch_created": 0,
        "watch_modified": 0,
        "watch_deleted": 0,
        "watch_renamed": 0,
        "watch_notice": 0,
        "watch_error": 0,
        "excel_event_count": 0,
    }
    entries: list[dict[str, object]] = []

    if log_path.exists():
        with log_path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if not isinstance(entry, dict):
                    continue
                entries.append(entry)
                event_type = entry.get("event_type")
                if isinstance(event_type, str) and event_type in stats:
                    stats[event_type] += 1
                if entry.get("is_excel") is True:
                    stats["excel_event_count"] += 1

    summary = {
        "summary_type": "watch_daily",
        "event_date": log_date,
        "generated_at": summary_timestamp,
        "stats": stats,
        "event_count": len(entries),
    }
    return log_store.write_watch_summary(summary_timestamp, summary)


def run_watch_service(
    config: AppConfig,
    *,
    max_iterations: int | None = None,
    sleep_func: Callable[[float], None] | None = None,
    now_func: Callable[[], datetime] | None = None,
    share_access_func: Callable[[AppConfig], None] | None = None,
    progress_func: Callable[[str], None] | None = None,
) -> int:
    sleep = sleep_func or time.sleep
    get_now = now_func or _current_time
    progress = progress_func or _no_progress
    progress("开始监听任务")
    progress("正在检查共享盘访问...")
    (share_access_func or ensure_share_access)(config)
    progress("共享盘访问检查完成")
    log_store = LogStore(config.log.dir)
    progress("正在检查日志目录...")
    log_store.ensure_ready()
    progress("日志目录检查完成")
    progress("正在采集初始监听快照...")
    previous = collect_watch_snapshot(config.share.root, config.scan)
    progress(
        "初始监听快照完成: "
        f"entries={len(previous.entries)}, "
        f"missing_dir={len(previous.missing_dirs)}, "
        f"failed_dir={len(previous.failed_dirs)}"
    )
    debouncer = EventDebouncer(config.watch.debounce_seconds)
    iteration = 0

    _log_snapshot_state(log_store, previous, get_now())
    progress(f"监听已启动: poll_interval={config.watch.poll_interval_seconds}s")
    while max_iterations is None or iteration < max_iterations:
        sleep(config.watch.poll_interval_seconds)
        try:
            current = collect_watch_snapshot(config.share.root, config.scan)
            current_time = get_now()
            _log_snapshot_state(log_store, current, current_time)
            events = debouncer.filter(diff_watch_snapshots(previous, current))
            progress(
                "监听轮询: "
                f"iteration={iteration + 1}, "
                f"entries={len(current.entries)}, "
                f"events={len(events)}, "
                f"missing_dir={len(current.missing_dirs)}, "
                f"failed_dir={len(current.failed_dirs)}"
            )
            for event in events:
                log_store.append_watch_log(
                    current_time.date().isoformat(),
                    format_watch_log_entry(event, _format_log_time(current_time)),
                )
                progress(f"监听事件: {event.event_type} {event.path}")
            previous = current
        except Exception as exc:  # pragma: no cover - recovery branch
            current_time = get_now()
            progress(f"监听异常: {exc}")
            log_store.append_watch_log(
                current_time.date().isoformat(),
                {
                    "event_type": "watch_error",
                    "path": str(Path(config.share.root)),
                    "previous_path": None,
                    "is_dir": True,
                    "is_excel": False,
                    "log_time": _format_log_time(current_time),
                    "message": str(exc),
                },
            )
        iteration += 1
    return 0


def _no_progress(_: str) -> None:
    return None


def _iter_watch_targets(root_path: Path, scan_config: ScanConfig) -> list[Path]:
    if scan_config.target_dirs:
        return [root_path / target_dir for target_dir in scan_config.target_dirs]
    return [root_path]


def _walk_directory(directory: Path, scan_config: ScanConfig, snapshot: WatchSnapshot) -> None:
    try:
        entries = list(directory.iterdir())
    except OSError:
        snapshot.failed_dirs.append(directory)
        return

    snapshot.entries[_normalize_key(directory)] = _build_entry(directory)
    for entry in entries:
        if entry.is_dir():
            if _is_excluded_dir(entry, scan_config):
                continue
            snapshot.entries[_normalize_key(entry)] = _build_entry(entry)
            if scan_config.recursive:
                _walk_directory(entry, scan_config, snapshot)
            continue

        snapshot.entries[_normalize_key(entry)] = _build_entry(entry)


def _build_entry(path: Path) -> WatchEntry:
    stat = path.stat()
    return WatchEntry(
        path=path,
        is_dir=path.is_dir(),
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
    )


def _build_renamed_events(
    previous_entries: dict[str, WatchEntry],
    current_entries: dict[str, WatchEntry],
    created_keys: set[str],
    deleted_keys: set[str],
) -> tuple[list[WatchEvent], set[str], set[str]]:
    created_by_signature: dict[tuple[bool, int, int], list[str]] = {}
    deleted_by_signature: dict[tuple[bool, int, int], list[str]] = {}

    for key in created_keys:
        created_by_signature.setdefault(current_entries[key].rename_signature, []).append(key)
    for key in deleted_keys:
        deleted_by_signature.setdefault(previous_entries[key].rename_signature, []).append(key)

    renamed_events: list[WatchEvent] = []
    consumed_created: set[str] = set()
    consumed_deleted: set[str] = set()
    for signature, deleted_group in deleted_by_signature.items():
        created_group = created_by_signature.get(signature, [])
        pair_count = min(len(deleted_group), len(created_group))
        if pair_count == 0:
            continue
        for index in range(pair_count):
            deleted_key = sorted(deleted_group)[index]
            created_key = sorted(created_group)[index]
            deleted_entry = previous_entries[deleted_key]
            created_entry = current_entries[created_key]
            renamed_events.append(
                WatchEvent(
                    event_type="watch_renamed",
                    path=created_entry.path,
                    previous_path=deleted_entry.path,
                    is_dir=created_entry.is_dir,
                    is_excel=_is_excel_path(created_entry.path),
                )
            )
            consumed_created.add(created_key)
            consumed_deleted.add(deleted_key)
    return renamed_events, consumed_created, consumed_deleted


def _is_excluded_dir(path: Path, scan_config: ScanConfig) -> bool:
    return path.name in set(scan_config.exclude_dirs or [])


def _is_excel_path(path: Path) -> bool:
    return path.suffix.lower() in {".xls", ".xlsx"}


def _normalize_key(path: Path | None) -> str:
    if path is None:
        return ""
    return str(path).replace("/", "\\").lower()


def _current_time() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def _format_log_time(value: datetime) -> str:
    return value.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _log_snapshot_state(log_store: LogStore, snapshot: WatchSnapshot, current_time: datetime) -> None:
    log_date = current_time.date().isoformat()
    log_time = _format_log_time(current_time)
    for missing_dir in snapshot.missing_dirs:
        log_store.append_watch_log(
            log_date,
            {
                "event_type": "watch_notice",
                "path": str(missing_dir),
                "previous_path": None,
                "is_dir": True,
                "is_excel": False,
                "log_time": log_time,
                "message": "监听目录不存在",
            },
        )
    for failed_dir in snapshot.failed_dirs:
        log_store.append_watch_log(
            log_date,
            {
                "event_type": "watch_notice",
                "path": str(failed_dir),
                "previous_path": None,
                "is_dir": True,
                "is_excel": False,
                "log_time": log_time,
                "message": "监听目录访问失败",
            },
        )
