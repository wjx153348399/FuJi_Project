from __future__ import annotations

import argparse
import sys

from zk_impedance_upload import __version__
from zk_impedance_upload.config import load_config
from zk_impedance_upload.exceptions import ConfigError, LogError
from zk_impedance_upload.log_store import LogStore
from zk_impedance_upload.runner import run_upload_task
from zk_impedance_upload.share_auth import ensure_share_access
from zk_impedance_upload.watcher import run_watch_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zk-impedance-upload",
        description="阻抗共享盘 Excel 上传脚本",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="配置文件路径，默认读取当前目录下的 config.json",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="只校验配置文件，不执行上传任务",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="启动监听服务，只记录共享盘变化事件，不执行上传",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.check_config:
        try:
            config = load_config(args.config)
        except ConfigError as exc:
            print(f"配置校验失败: {exc}", file=sys.stderr)
            return 2
        try:
            ensure_share_access(config)
            LogStore(config.log.dir).ensure_ready()
        except ConfigError as exc:
            print(f"配置校验失败: {exc}", file=sys.stderr)
            return 2
        except (LogError, OSError) as exc:
            print(f"日志目录检查失败: {exc}", file=sys.stderr)
            return 2
        print(f"配置校验通过: {args.config}")
        return 0

    try:
        config = load_config(args.config)
        if args.watch:
            if not config.watch.enabled:
                print("监听功能未启用: 请在配置文件中设置 watch.enabled=true", file=sys.stderr)
                return 2
            return run_watch_service(config, progress_func=print)
        result = run_upload_task(config, progress_func=print)
    except ConfigError as exc:
        print(f"配置校验失败: {exc}", file=sys.stderr)
        return 2
    except LogError as exc:
        print(f"日志目录检查失败: {exc}", file=sys.stderr)
        return 2

    print(
        "上传任务完成: "
        f"success={result.stats['success_count']}, "
        f"fail={result.stats['fail_count']}, "
        f"skip={result.stats['skip_count']}"
    )
    return 0
