"""Command line interface for the strava-dashboard pipeline.

The harness only defines the command surface (see docs/TESTS.md, "CLI contract"). Every
subcommand is a stub that exits non-zero with "not implemented" until its task lands.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from sdash import __version__

DEFAULT_DATA_DIR = Path("~/data/strava-export")


def default_data_dir() -> Path:
    """Data dir from SDASH_DATA_DIR, else ~/data/strava-export."""
    env = os.environ.get("SDASH_DATA_DIR")
    return Path(env).expanduser() if env else DEFAULT_DATA_DIR.expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdash", description="Strava export -> segment efforts -> static site"
    )
    parser.add_argument("--version", action="version", version=f"sdash {__version__}")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="data directory (default: $SDASH_DATA_DIR or ~/data/strava-export)",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("import", help="import an export zip (local path or https link)")
    p.add_argument("source", help="path to an export zip or an https download link")

    sub.add_parser("parse", help="parse cycling rides into cached tracks")
    sub.add_parser("match", help="match segments against parsed rides")

    p = sub.add_parser("build-data", help="write the site JSON")
    p.add_argument("--out", type=Path, default=None, help="output dir (default: web/public/data)")

    seg = sub.add_parser("segment", help="manage segments.yaml")
    seg_sub = seg.add_subparsers(dest="segment_command", required=True, metavar="SUBCOMMAND")
    p = seg_sub.add_parser("add", help="add a segment from a ride and a km range")
    p.add_argument("--name", required=True)
    p.add_argument("--activity", required=True, help="activity ID of the reference ride")
    p.add_argument("--from-km", type=float, required=True)
    p.add_argument("--to-km", type=float, required=True)
    seg_sub.add_parser("import-strava", help="add segments from Strava's segments.csv")

    for name, helptext in (
        ("deploy", "guard and push web/dist to the gh-pages branch"),
        ("refresh", "import (optional), parse, match, build data and site, deploy"),
    ):
        p = sub.add_parser(name, help=helptext)
        if name == "refresh":
            p.add_argument("source", nargs="?", default=None, help="export zip or https link")
            p.add_argument("--no-deploy", action="store_true", help="stop after building the site")
        p.add_argument("--web-dir", type=Path, default=None, help="web project dir (default: web/)")
        p.add_argument("--remote", default=None, help="git remote (name, URL or path) to push to")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = str(args.command)
    if command == "segment":
        command = f"segment {args.segment_command}"
    print(f"sdash {command}: not implemented", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
