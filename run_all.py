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
from zk_impedance_upload.service_status import write_service_status
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
    parser.add_argument("--watch-restart-delay-seconds", type=float, default=5.0, help="监听服务异常退出后的重启等待秒数")
    parser.add_argument("--max-watch-restarts", type=int, default=None, help="监听服务最大自动重启次数，默认不限")
    parser.add_argument("--heartbeat-seconds", type=float, default=10.0, help="服务状态心跳写入间隔秒数")
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
            watch_restart_delay_seconds=max(args.watch_restart_delay_seconds, 0),
            max_watch_restarts=args.max_watch_restarts,
            heartbeat_seconds=max(args.heartbeat_seconds, 1),
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
    watch_restart_delay_seconds: float = 5.0,
    max_watch_restarts: int | None = None,
    heartbeat_seconds: float = 10.0,
    progress_func: Callable[[str], None] = print,
    watch_service_func: Callable[..., int] = run_watch_service,
    sleep_func: Callable[[float], None] = time.sleep,
) -> int:
    errors: list[BaseException] = []
    stop_heartbeat = threading.Event()
    state: dict[str, object] = {
        "state": "starting",
        "message": "starting combined service",
        "watcher_restart_count": 0,
    }

    def _run_web() -> None:
        try:
            web_runner()
        except BaseException as exc:  # pragma: no cover - defensive runtime branch
            errors.append(exc)

    def _heartbeat() -> None:
        while not stop_heartbeat.is_set():
            _write_status(app_config.log.dir, state)
            stop_heartbeat.wait(heartbeat_seconds)

    _write_status(app_config.log.dir, state)
    heartbeat_thread = threading.Thread(target=_heartbeat, name="zk-service-heartbeat", daemon=True)
    heartbeat_thread.start()
    web_thread = threading.Thread(target=_run_web, name="station-config-web", daemon=True)
    web_thread.start()
    if startup_wait_seconds:
        sleep_func(startup_wait_seconds)
    if errors:
        state.update({"state": "failed", "message": f"web start failed: {errors[0]}"})
        _write_status(app_config.log.dir, state)
        stop_heartbeat.set()
        progress_func(f"Web 服务启动失败: {errors[0]}")
        return 2

    progress_func("Web 服务已启动，开始启动监听服务")
    exit_code = 0
    try:
        exit_code = _run_watch_with_restart(
            app_config=app_config,
            state=state,
            watch_service_func=watch_service_func,
            progress_func=progress_func,
            sleep_func=sleep_func,
            restart_delay_seconds=watch_restart_delay_seconds,
            max_restarts=max_watch_restarts,
        )
        return exit_code
    finally:
        final_state = "stopped" if exit_code == 0 else "failed"
        state.update({"state": final_state, "message": f"combined service stopped: exit_code={exit_code}"})
        _write_status(app_config.log.dir, state)
        stop_heartbeat.set()
        progress_func("组合服务已退出")


def _run_watch_with_restart(
    *,
    app_config,
    state: dict[str, object],
    watch_service_func: Callable[..., int],
    progress_func: Callable[[str], None],
    sleep_func: Callable[[float], None],
    restart_delay_seconds: float,
    max_restarts: int | None,
) -> int:
    restart_count = 0
    while True:
        state.update(
            {
                "state": "running",
                "message": "watcher running",
                "watcher_restart_count": restart_count,
            }
        )
        _write_status(app_config.log.dir, state)
        try:
            exit_code = int(watch_service_func(app_config, progress_func=progress_func))
        except KeyboardInterrupt:
            raise
        except BaseException as exc:
            exit_code = 1
            state.update({"state": "watcher_failed", "message": f"watcher crashed: {exc}"})
            progress_func(f"监听服务异常退出，准备重启: {exc}")

        if exit_code == 0:
            state.update({"state": "stopped", "message": "watcher stopped normally"})
            _write_status(app_config.log.dir, state)
            return 0

        if max_restarts is not None and restart_count >= max_restarts:
            state.update(
                {
                    "state": "failed",
                    "message": f"watcher stopped after {restart_count} restart(s), exit_code={exit_code}",
                    "watcher_restart_count": restart_count,
                }
            )
            _write_status(app_config.log.dir, state)
            return exit_code

        restart_count += 1
        state.update(
            {
                "state": "restarting",
                "message": f"watcher restarting in {restart_delay_seconds:g}s, last exit_code={exit_code}",
                "watcher_restart_count": restart_count,
            }
        )
        _write_status(app_config.log.dir, state)
        progress_func(f"监听服务已退出，{restart_delay_seconds:g}s 后自动重启: exit_code={exit_code}")
        if restart_delay_seconds:
            sleep_func(restart_delay_seconds)


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


def _write_status(log_dir: str, state: dict[str, object]) -> None:
    try:
        write_service_status(log_dir, state)
    except OSError:
        return


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
