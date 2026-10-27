"""Output guard (REQ-009/REQ-010) and segments.yaml backups (D-004).

The guard runs on the built site (web/dist) before anything is published. The push to gh-pages
itself is T-012; `deploy()` runs the guard and stops there until that lands.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RAW_SUFFIXES = (
    ".fit", ".fit.gz", ".gpx", ".gpx.gz", ".tcx", ".tcx.gz", ".zip", ".csv", ".csv.gz",
)  # fmt: skip
COORD_KEYS = frozenset(
    {
        "lat",
        "lon",
        "lng",
        "latitude",
        "longitude",
        "start",
        "end",
        "coords",
        "coordinates",
        "points",
        "track",
        "ref_points",
        "polyline",
        "position",
        "latlng",
    }
)
KEEP_BACKUPS = 10


class GuardError(Exception):
    """The built site must not be published; the message names every offending file."""


class DeployError(Exception):
    """Deploying failed (after the guard passed)."""


def _coordinate_keys(obj: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() in COORD_KEYS:
                found.add(str(key))
            found |= _coordinate_keys(value)
    elif isinstance(obj, list):
        for value in obj:
            found |= _coordinate_keys(value)
    return found


def check_site(dist: Path) -> list[str]:
    """One line per problem: raw ride/export files anywhere, coordinate keys in data/**/*.json."""
    problems: list[str] = []
    for root, _dirs, files in os.walk(dist):
        for name in sorted(files):
            path = Path(root) / name
            rel = path.relative_to(dist).as_posix()
            if name.lower().endswith(RAW_SUFFIXES):
                problems.append(f"{rel}: raw ride/export file")
            elif name.lower().endswith(".json") and rel.startswith("data/"):
                try:
                    keys = _coordinate_keys(json.loads(path.read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    problems.append(f"{rel}: unreadable JSON, cannot verify it has no coordinates")
                    continue
                if keys:
                    problems.append(f"{rel}: coordinate field(s) {', '.join(sorted(keys))}")
    return sorted(problems)


def guard(dist: Path) -> None:
    """Raise GuardError unless `dist` is a built site without raw files or coordinates."""
    if not (dist / "index.html").is_file():
        raise GuardError(f"{dist} has no index.html: the site was not built")
    problems = check_site(dist)
    if problems:
        raise GuardError("output guard failed, nothing deployed:\n  " + "\n  ".join(problems))


def deploy(web_dir: Path, remote: str | None) -> None:
    """Guard, then publish web/dist to gh-pages (the publishing half arrives with T-012)."""
    guard(web_dir / "dist")
    raise DeployError("pushing to gh-pages is not implemented yet (T-012)")


def backup_segments(path: Path, keep: int = KEEP_BACKUPS) -> Path | None:
    """Copy segments.yaml to segments.bak/ (last `keep` copies); None if missing or unchanged."""
    if not path.is_file():
        return None
    folder = path.with_name("segments.bak")
    content = path.read_bytes()
    existing = sorted(folder.glob("segments-*.yaml")) if folder.is_dir() else []
    if existing and existing[-1].read_bytes() == content:
        return None
    folder.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = folder / f"segments-{stamp}.yaml"
    target.write_bytes(content)
    for old in sorted(folder.glob("segments-*.yaml"))[:-keep]:
        old.unlink()
    return target
