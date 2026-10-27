"""Command line interface for the strava-dashboard pipeline.

The harness only defines the command surface (see docs/TESTS.md, "CLI contract"). Every
subcommand is a stub that exits non-zero with "not implemented" until its task lands.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from sdash import __version__, deploy, importer, pipeline, segments

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


def _default_web_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "web"


def _cmd_import(data_dir: Path, source: str) -> int:
    count = importer.import_source(source, data_dir)
    print(f"imported {count} files into {data_dir / 'raw'}")
    return 0


def _cmd_parse(data_dir: Path) -> int:
    report = pipeline.parse_rides(data_dir)
    extra = f", {report.references} reference tracks" if report.references else ""
    print(f"parsed {report.parsed} rides{extra}, {len(report.failed)} failed")
    for activity_id, reason in report.failed:
        print(f"failed {activity_id}: {reason}")
    return 0


EXIT_WARNINGS = 2  # segment-level problems: reported, those segments skipped, the rest done


def _print_report(report: pipeline.MatchReport) -> int:
    """Per-segment effort lines, then one warning per skipped segment. Returns the exit code."""
    for r in report.results:
        print(f"{r.segment.name}: {len(r.efforts)} efforts")
    return _print_problems(report)


def _print_problems(report: pipeline.MatchReport) -> int:
    """One warning per skipped segment. Returns the exit code."""
    for problem in report.problems:
        print(f"warning: {problem} (segment skipped)")
    return EXIT_WARNINGS if report.problems else 0


def _cmd_match(data_dir: Path) -> int:
    return _print_report(pipeline.match_segments(data_dir))


def _cmd_build_data(data_dir: Path, out: Path | None) -> int:
    target = out or _default_web_dir() / "public" / "data"
    report = pipeline.build_data(data_dir, target)
    print(f"wrote {len(report.results)} segments to {target}")
    return _print_problems(report)


def _import_quietly(data_dir: Path, source: str) -> int:
    try:
        return _cmd_import(data_dir, source)
    except pipeline.PipelineError:
        raise
    except Exception as exc:  # never show a traceback: it could carry the export link
        raise pipeline.PipelineError(f"import failed ({type(exc).__name__})") from None


def _build_site(web_dir: Path) -> None:
    npm = shutil.which("npm")
    if npm is None:
        raise pipeline.PipelineError("npm not found: cannot build the site")
    sys.stdout.flush()  # keep the report above the build log when piped
    build = subprocess.run([npm, "run", "build"], cwd=web_dir, check=False)
    if build.returncode != 0:
        raise pipeline.PipelineError("site build failed")


def _guard_and_deploy(web_dir: Path, remote: str | None, publish: bool) -> None:
    try:
        deploy.guard(web_dir / "dist")
        if publish:
            deploy.deploy(web_dir, remote)
    except (deploy.GuardError, deploy.DeployError) as exc:
        raise pipeline.PipelineError(str(exc)) from exc


def _cmd_deploy(args: argparse.Namespace) -> int:
    web_dir: Path = args.web_dir or _default_web_dir()
    _guard_and_deploy(web_dir, args.remote, publish=True)
    return 0


def _cmd_refresh(data_dir: Path, args: argparse.Namespace) -> int:
    """Each step must succeed (PipelineError -> exit 1, nothing deployed); segment warnings -> 2."""
    web_dir: Path = args.web_dir or _default_web_dir()
    try:
        deploy.backup_segments(data_dir / "segments.yaml")
    except OSError as exc:
        raise pipeline.PipelineError(
            f"cannot back up segments.yaml ({type(exc).__name__}: {exc.strerror})"
        ) from None
    if args.source:
        _import_quietly(data_dir, args.source)
    _cmd_parse(data_dir)
    target = web_dir / "public" / "data"
    report = pipeline.build_data(data_dir, target)
    for r in report.results:
        print(f"{r.segment.name}: {len(r.efforts)} efforts")
    print(f"wrote {len(report.results)} segments to {target}")
    status = _print_problems(report)  # 2 when segments were skipped: still builds and deploys
    _build_site(web_dir)
    _guard_and_deploy(web_dir, args.remote, publish=not args.no_deploy)
    return status


def _cmd_segment_add(data_dir: Path, args: argparse.Namespace) -> int:
    seg = pipeline.add_segment(data_dir, args.name, args.activity, args.from_km, args.to_km)
    print(f"added segment {seg.name!r} (slug {seg.slug}) to {data_dir / 'segments.yaml'}")
    return 0


def _cmd_segment_import_strava(data_dir: Path) -> int:
    try:
        report = segments.import_strava_csv(
            data_dir / "raw" / "segments.csv", data_dir / "segments.yaml"
        )
    except segments.SegmentError as exc:
        raise pipeline.PipelineError(str(exc)) from exc
    print(
        f"added {report.added}, skipped {report.skipped_existing} existing, "
        f"{len(report.invalid)} invalid"
    )
    for row, reason in report.invalid:
        print(f"invalid row {row}: {reason}", file=sys.stderr)
    return 1 if report.invalid and not report.added else 0


IMPLEMENTED = {
    "import",
    "parse",
    "match",
    "build-data",
    "refresh",
    "deploy",
    "segment add",
    "segment import-strava",
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = str(args.command)
    if command == "segment":
        command = f"segment {args.segment_command}"
    if command not in IMPLEMENTED:
        print(f"sdash {command}: not implemented", file=sys.stderr)
        return 1
    data_dir: Path = (args.data_dir or default_data_dir()).expanduser()
    try:
        if command == "import":
            return _import_quietly(data_dir, args.source)
        if command == "parse":
            return _cmd_parse(data_dir)
        if command == "match":
            return _cmd_match(data_dir)
        if command == "build-data":
            return _cmd_build_data(data_dir, args.out)
        if command == "segment add":
            return _cmd_segment_add(data_dir, args)
        if command == "segment import-strava":
            return _cmd_segment_import_strava(data_dir)
        if command == "deploy":
            return _cmd_deploy(args)
        return _cmd_refresh(data_dir, args)
    except pipeline.PipelineError as exc:
        print(f"sdash {command}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:  # e.g. unwritable data dir: one line, no traceback
        print(f"sdash {command}: {type(exc).__name__}: {exc.strerror or exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
