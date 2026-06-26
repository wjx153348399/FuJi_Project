from __future__ import annotations

import sys

from zk_impedance_upload.cli import main as cli_main


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    if "--watch" not in args:
        args.append("--watch")
    return cli_main(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
