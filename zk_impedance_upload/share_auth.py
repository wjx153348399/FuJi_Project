from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Callable, Iterable, Sequence

from zk_impedance_upload.config import AppConfig
from zk_impedance_upload.exceptions import ConfigError


ExistsFunc = Callable[[str], bool]
RunFunc = Callable[[list[str]], object]


def ensure_share_access(
    config: AppConfig,
    *,
    exists_func: ExistsFunc | None = None,
    run_func: RunFunc | None = None,
) -> None:
    exists = exists_func or _path_exists
    run = run_func or _run_command

    for share_root in collect_share_roots(config):
        if exists(share_root):
            continue
        command = ["net", "use", share_root, f"/user:{config.share.username}", config.share.password]
        try:
            result = run(command)
        except Exception as exc:
            raise ConfigError(f"共享盘登录失败: {share_root}") from exc

        return_code = getattr(result, "returncode", 0)
        if isinstance(return_code, int) and return_code != 0:
            message = _command_error_message(result)
            raise ConfigError(f"共享盘登录失败: {share_root}{message}")


def collect_share_roots(config: AppConfig) -> list[str]:
    return _unique_keep_order(
        root
        for root in (
            get_share_root(config.share.root),
            get_share_root(config.log.dir),
        )
        if root is not None
    )


def get_share_root(path: str | Path) -> str | None:
    value = str(path).replace("/", "\\")
    if not value.startswith("\\\\"):
        return None

    parts = [part for part in value.lstrip("\\").split("\\") if part]
    if len(parts) < 2:
        return None
    return f"\\\\{parts[0]}\\{parts[1]}"


def _unique_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _path_exists(path: str) -> bool:
    try:
        return Path(path).exists()
    except OSError:
        return False


def _run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        check=False,
    )


def _command_error_message(result: object) -> str:
    output_parts = [
        str(getattr(result, "stdout", "") or "").strip(),
        str(getattr(result, "stderr", "") or "").strip(),
    ]
    output = " ".join(part for part in output_parts if part)
    if not output:
        return ""
    return f": {output}"
