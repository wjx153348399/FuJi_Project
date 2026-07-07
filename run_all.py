from __future__ import annotations

import argparse
import sys
import threading
import time
from typing import Callable

from station_config_web.app import create_app
from station_config_web.config import load_web_config
from zk_impedance_upload.config import load_config
from zk_impedance_upload.exceptions import ConfigError, LogError
from zk_impedance_upload.watcher import run_watch_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_all.py",
        description="启动工站配置 Web 服务和实时监听上传服务",
    )
    parser.add_argument("--config", default="config.json", help="监听和上传配置文件路径")
    parser.add_argument("--web-config", default="web_config.json", help="Web 配置文件路径")
    parser.add_argument(
        "--startup-wait-seconds",
        type=float,
        default=1.0,
        help="Web 服务启动后等待监听服务启动的秒数",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        app_config = load_config(args.config)
        web_config = load_web_config(args.web_config)
        if not app_config.watch.enabled:
            print("监听功能未启用，请在 config.json 中设置 watch.enabled=true", file=sys.stderr)
            return 2
        web_runner = _build_web_runner(args.web_config, web_config.server.host, web_config.server.port)
        return run_combined_services(
            app_config=app_config,
            web_runner=web_runner,
            startup_wait_seconds=max(args.startup_wait_seconds, 0),
            progress_func=print,
        )
    except (ConfigError, LogError) as exc:
        print(f"启动失败: {exc}", file=sys.stderr)
        return 2


def run_combined_services(
    *,
    app_config,
    web_runner: Callable[[], None],
    startup_wait_seconds: float = 1.0,
    progress_func: Callable[[str], None] = print,
    watch_service_func: Callable[..., int] = run_watch_service,
) -> int:
    errors: list[BaseException] = []

    def _run_web() -> None:
        try:
            web_runner()
        except BaseException as exc:  # pragma: no cover - defensive runtime branch
            errors.append(exc)

    web_thread = threading.Thread(target=_run_web, name="station-config-web", daemon=True)
    web_thread.start()
    if startup_wait_seconds:
        time.sleep(startup_wait_seconds)
    if errors:
        progress_func(f"Web 服务启动失败: {errors[0]}")
        return 2

    progress_func("Web 服务已启动，开始启动监听服务")
    try:
        return watch_service_func(app_config, progress_func=progress_func)
    finally:
        progress_func("组合服务已退出")


def _build_web_runner(web_config_path: str, host: str, port: int) -> Callable[[], None]:
    def _run() -> None:
        import uvicorn

        server_config = uvicorn.Config(
            create_app(web_config_path),
            host=host,
            port=port,
            reload=False,
            log_level="info",
        )
        uvicorn.Server(server_config).run()

    return _run


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
