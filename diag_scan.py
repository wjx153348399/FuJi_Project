from __future__ import annotations

import argparse
import time
from pathlib import Path

from zk_impedance_upload.config import load_config
from zk_impedance_upload.date_window import build_date_window
from zk_impedance_upload.dedupe import dedupe_batch
from zk_impedance_upload.fingerprint import HashCache, calculate_sha256, split_history_uploaded
from zk_impedance_upload.log_store import LogStore
from zk_impedance_upload.parser import parse_candidate
from zk_impedance_upload.scanner import scan_files


def main() -> int:
    parser = argparse.ArgumentParser(description="诊断共享盘扫描阶段")
    parser.add_argument("--config", default="config.json")
    parser.add_argument(
        "--mode",
        choices=["basic", "walk", "fullscan", "pipeline", "list-candidates", "hash-sample", "group-by-dir"],
        default="basic",
        help="basic=检查配置与一级目录，walk=递归遍历计数，fullscan=执行项目真实扫描，pipeline=执行扫描后各阶段计时，list-candidates=列候选文件，hash-sample=测样本文件 hash 耗时，group-by-dir=按目录聚合候选文件",
    )
    parser.add_argument(
        "--max-seconds",
        type=int,
        default=60,
        help="walk 模式最大执行秒数",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="hash-sample 模式最多测多少个文件",
    )
    args = parser.parse_args()

    start = time.time()
    config = load_config(args.config)
    print("stage=config_ok", flush=True)
    LogStore(config.log.dir).ensure_ready()
    print("stage=log_ok", flush=True)

    date_window = build_date_window(day_offset=config.upload.day_offset)
    print(
        f"stage=window_ok target_day={date_window.target_day} "
        f"start={date_window.start} end={date_window.end}",
        flush=True,
    )

    root = Path(config.share.root)
    print(f"stage=root exists={root.exists()} is_dir={root.is_dir()} path={root}", flush=True)

    if args.mode == "basic":
        _run_basic(config, root)
    elif args.mode == "walk":
        _run_walk(config, root, max_seconds=args.max_seconds)
    elif args.mode == "pipeline":
        _run_pipeline(config, root, date_window)
    elif args.mode == "list-candidates":
        _run_list_candidates(config, root, date_window, limit=args.limit)
    elif args.mode == "group-by-dir":
        _run_group_by_dir(config, root, date_window, limit=args.limit)
    elif args.mode == "hash-sample":
        _run_hash_sample(config, root, date_window, limit=args.limit)
    else:
        _run_fullscan(config, root, date_window)

    print(f"stage=done elapsed={time.time() - start:.2f}s mode={args.mode}", flush=True)
    return 0


def _run_basic(config, root: Path) -> None:
    for target_name in _target_dirs(config):
        target_path = root / target_name
        print(f"target=start path={target_path}", flush=True)
        print(
            f"target=meta exists={target_path.exists()} "
            f"is_dir={target_path.is_dir() if target_path.exists() else False}",
            flush=True,
        )
        if not target_path.exists() or not target_path.is_dir():
            continue
        list_start = time.time()
        try:
            entries = list(target_path.iterdir())
            print(
                f"target=list_ok entries={len(entries)} "
                f"elapsed={time.time() - list_start:.2f}s",
                flush=True,
            )
        except Exception as exc:  # pragma: no cover - diagnostic only
            print(f"target=list_error type={type(exc).__name__} error={exc}", flush=True)


def _run_walk(config, root: Path, max_seconds: int) -> None:
    deadline = time.time() + max_seconds
    dir_count = 0
    file_count = 0
    for target_name in _target_dirs(config):
        target_path = root / target_name
        print(f"walk=target path={target_path}", flush=True)
        if not target_path.exists() or not target_path.is_dir():
            print("walk=skip reason=missing_or_not_dir", flush=True)
            continue
        for current_root, dir_names, file_names in _safe_walk(target_path):
            dir_count += 1
            file_count += len(file_names)
            if dir_count % 100 == 0:
                print(
                    f"walk=progress dirs={dir_count} files={file_count} current={current_root}",
                    flush=True,
                )
            dir_names[:] = [
                name
                for name in dir_names
                if name not in set(config.scan.exclude_dirs or [])
            ]
            if time.time() >= deadline:
                print(
                    f"walk=timeout dirs={dir_count} files={file_count} current={current_root}",
                    flush=True,
                )
                return
    print(f"walk=completed dirs={dir_count} files={file_count}", flush=True)


def _target_dirs(config) -> list[str]:
    enabled_targets = [target for target in config.scan.targets or [] if target.enabled]
    if enabled_targets:
        return [target.dir for target in enabled_targets]
    return list(config.scan.target_dirs or [])


def _run_fullscan(config, root: Path, date_window) -> None:
    scan_start = time.time()
    result = scan_files(root, config.scan, date_window)
    print(
        "fullscan=result "
        f"candidates={len(result.candidates)} "
        f"missing_dirs={len(result.missing_dirs)} "
        f"failed_dirs={len(result.failed_dirs)} "
        f"elapsed={time.time() - scan_start:.2f}s",
        flush=True,
    )
    if result.candidates:
        print(f"fullscan=first_candidate path={result.candidates[0].path}", flush=True)


def _run_pipeline(config, root: Path, date_window) -> None:
    t0 = time.time()
    scan_result = scan_files(root, config.scan, date_window)
    print(
        f"pipeline=scan candidates={len(scan_result.candidates)} "
        f"missing_dirs={len(scan_result.missing_dirs)} "
        f"failed_dirs={len(scan_result.failed_dirs)} "
        f"elapsed={time.time() - t0:.2f}s",
        flush=True,
    )

    t1 = time.time()
    parsed_files = [parse_candidate(candidate) for candidate in scan_result.candidates]
    print(
        f"pipeline=parse parsed={len(parsed_files)} elapsed={time.time() - t1:.2f}s",
        flush=True,
    )

    hash_cache = HashCache()

    t2 = time.time()
    batch_result = dedupe_batch(parsed_files, hash_cache)
    print(
        f"pipeline=dedupe selected={len(batch_result.selected)} "
        f"skipped={len(batch_result.skipped)} elapsed={time.time() - t2:.2f}s",
        flush=True,
    )

    t3 = time.time()
    log_store = LogStore(config.log.dir)
    fingerprints = log_store.load_uploaded_fingerprints()
    history_result = split_history_uploaded(batch_result.selected, fingerprints, hash_cache)
    print(
        f"pipeline=history pending={len(history_result.pending)} "
        f"skipped={len(history_result.skipped)} elapsed={time.time() - t3:.2f}s",
        flush=True,
    )


def _run_hash_sample(config, root: Path, date_window, limit: int) -> None:
    scan_result = scan_files(root, config.scan, date_window)
    candidates = sorted(scan_result.candidates, key=lambda item: item.size, reverse=True)
    print(f"hash_sample=candidates total={len(candidates)}", flush=True)
    for candidate in candidates[:limit]:
        t0 = time.time()
        digest = calculate_sha256(candidate.path)
        elapsed = time.time() - t0
        print(
            f"hash_sample=file size={candidate.size} elapsed={elapsed:.2f}s "
            f"path={candidate.path} sha256={digest[:16]}",
            flush=True,
        )


def _run_list_candidates(config, root: Path, date_window, limit: int) -> None:
    scan_result = scan_files(root, config.scan, date_window)
    candidates = sorted(scan_result.candidates, key=lambda item: item.size, reverse=True)
    print(f"list_candidates=total {len(candidates)}", flush=True)
    for index, candidate in enumerate(candidates[:limit], start=1):
        print(
            f"list_candidates=item index={index} size={candidate.size} "
            f"mtime={candidate.modified_at} path={candidate.path}",
            flush=True,
        )


def _run_group_by_dir(config, root: Path, date_window, limit: int) -> None:
    scan_result = scan_files(root, config.scan, date_window)
    grouped: dict[str, tuple[int, int]] = {}
    for candidate in scan_result.candidates:
        key = str(candidate.path.parent)
        count, total_size = grouped.get(key, (0, 0))
        grouped[key] = (count + 1, total_size + candidate.size)

    items = sorted(grouped.items(), key=lambda item: (item[1][0], item[1][1]))
    print(f"group_by_dir=total_dirs {len(items)}", flush=True)
    for index, (directory, (count, total_size)) in enumerate(items[:limit], start=1):
        print(
            f"group_by_dir=item index={index} count={count} total_size={total_size} path={directory}",
            flush=True,
        )


def _safe_walk(root: Path):
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            children = list(current.iterdir())
        except Exception as exc:  # pragma: no cover - diagnostic only
            print(f"walk=error path={current} type={type(exc).__name__} error={exc}", flush=True)
            continue
        dir_names = [child.name for child in children if child.is_dir()]
        file_names = [child.name for child in children if not child.is_dir()]
        yield current, dir_names, file_names
        for child in reversed(children):
            if child.is_dir():
                stack.append(child)


if __name__ == "__main__":
    raise SystemExit(main())
