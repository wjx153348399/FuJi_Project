from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from zk_impedance_upload.config import ScanConfig, ScanTargetConfig
from zk_impedance_upload.date_window import DateWindow, SHANGHAI_TZ


@dataclass(frozen=True)
class CandidateFile:
    path: Path
    size: int
    modified_at: datetime
    flow: str = "UNKNOWN"
    filePath: str = ""


@dataclass
class ScanResult:
    candidates: list[CandidateFile] = field(default_factory=list)
    missing_dirs: list[Path] = field(default_factory=list)
    failed_dirs: list[Path] = field(default_factory=list)


def scan_files(root: str | Path, scan_config: ScanConfig, date_window: DateWindow) -> ScanResult:
    root_path = Path(root)
    result = ScanResult()

    for target in _effective_targets(scan_config):
        target_path = root_path / target.dir
        if not target_path.exists():
            result.missing_dirs.append(target_path)
            continue
        if not target_path.is_dir():
            result.failed_dirs.append(target_path)
            continue

        _scan_directory(target_path, scan_config, date_window, result, target)

    return result


def build_candidate_for_path(
    root: str | Path,
    scan_config: ScanConfig,
    path: str | Path,
    date_window: DateWindow | None = None,
) -> CandidateFile | None:
    root_path = Path(root)
    file_path = Path(path)
    for target in _effective_targets(scan_config):
        target_path = root_path / target.dir
        if not _is_under_directory(file_path, target_path):
            continue
        try:
            relative_path = file_path.relative_to(target_path)
        except ValueError:
            relative_path = Path()
        if any(part in set(scan_config.exclude_dirs or []) for part in relative_path.parts[:-1]):
            return None
        if not _is_candidate_file(file_path, scan_config, date_window):
            return None
        try:
            stat = file_path.stat()
        except OSError:
            return None
        return CandidateFile(
            path=file_path,
            size=stat.st_size,
            modified_at=_mtime_to_datetime(stat.st_mtime),
            flow=target.flow,
            filePath=str(file_path),
        )
    return None


def _effective_targets(scan_config: ScanConfig) -> list[ScanTargetConfig]:
    configured_targets = [target for target in scan_config.targets or [] if target.enabled]
    if configured_targets:
        return configured_targets
    target_dirs = scan_config.target_dirs or []
    if target_dirs:
        return [
            ScanTargetConfig(flow="UNKNOWN", dir=target_dir, enabled=True)
            for target_dir in target_dirs
        ]
    return [ScanTargetConfig(flow="UNKNOWN", dir=".", enabled=True)]


def _scan_directory(
    directory: Path,
    scan_config: ScanConfig,
    date_window: DateWindow,
    result: ScanResult,
    target: ScanTargetConfig,
) -> None:
    try:
        entries = list(directory.iterdir())
    except OSError:
        result.failed_dirs.append(directory)
        return

    for entry in entries:
        if entry.is_dir():
            if _is_excluded_dir(entry, scan_config):
                continue
            if scan_config.recursive:
                _scan_directory(entry, scan_config, date_window, result, target)
            continue

        if _is_candidate_file(entry, scan_config, date_window):
            stat = entry.stat()
            result.candidates.append(
                CandidateFile(
                    path=entry,
                    size=stat.st_size,
                    modified_at=_mtime_to_datetime(stat.st_mtime),
                    flow=target.flow,
                    filePath=str(entry),
                )
            )


def _is_candidate_file(path: Path, scan_config: ScanConfig, date_window: DateWindow | None) -> bool:
    if not path.is_file():
        return False
    if any(path.name.startswith(prefix) for prefix in scan_config.exclude_prefixes or []):
        return False
    if path.suffix.lower() not in {ext.lower() for ext in scan_config.extensions or []}:
        return False

    try:
        modified_at = _mtime_to_datetime(path.stat().st_mtime)
    except OSError:
        return False
    if date_window is None:
        return True
    return date_window.contains(modified_at)


def _is_excluded_dir(path: Path, scan_config: ScanConfig) -> bool:
    return path.name in set(scan_config.exclude_dirs or [])


def _mtime_to_datetime(mtime: float) -> datetime:
    return datetime.fromtimestamp(mtime, tz=ZoneInfo("Asia/Shanghai")).astimezone(SHANGHAI_TZ)


def _is_under_directory(path: Path, directory: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(directory.resolve(strict=False))
        return True
    except ValueError:
        return False
