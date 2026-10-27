"""Output guard (REQ-009/REQ-010) and segments.yaml backups (D-004).

The guard runs on the built site (web/dist) before anything is published. The push to gh-pages
itself is T-012; `deploy()` runs the guard and stops there until that lands.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from math import isfinite
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


LATLON_KEYS = frozenset({"lat", "lon", "lng", "latitude", "longitude", "latlng"})
JSON_SUFFIXES = (".json", ".geojson")


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _looks_like_pair(items: list[Any]) -> bool:
    """Two numbers, at least one non-integer, within lat/lon ranges: a coordinate pair."""
    if len(items) != 2 or not all(_is_number(x) for x in items):
        return False
    a, b = items
    return (
        all(isfinite(x) for x in items)
        and any(x != int(x) for x in items)
        and abs(a) <= 90
        and abs(b) <= 180
    )


def _coordinate_findings(obj: Any, keys: frozenset[str], pairs: bool) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() in keys:
                found.add(f"field {key}")
            found |= _coordinate_findings(value, keys, pairs)
    elif isinstance(obj, list):
        if pairs and _looks_like_pair(obj):
            found.add("lat/lon-like number pair")
        for value in obj:
            found |= _coordinate_findings(value, keys, pairs)
    return found


def check_site(dist: Path) -> list[str]:
    """One line per problem: raw files, symlinks, and coordinates in any JSON/GeoJSON file.

    Under data/ the full key list and the lat/lon pair shape are checked; elsewhere (e.g. Vite
    manifests) only lat/lon-style keys. Symlinks are flagged and never followed.
    """
    problems: list[str] = []
    for root, dirs, files in os.walk(dist):
        for name in sorted(dirs + files):
            path = Path(root) / name
            if path.is_symlink():
                problems.append(f"{path.relative_to(dist).as_posix()}: symlink")
        for name in sorted(files):
            path = Path(root) / name
            rel = path.relative_to(dist).as_posix()
            if path.is_symlink():
                continue
            if name.lower().endswith(RAW_SUFFIXES):
                problems.append(f"{rel}: raw ride/export file")
            elif name.lower().endswith(JSON_SUFFIXES):
                in_data = rel.startswith("data/")
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    if in_data:
                        problems.append(f"{rel}: unreadable JSON, cannot verify no coordinates")
                    continue
                found = _coordinate_findings(data, COORD_KEYS if in_data else LATLON_KEYS, in_data)
                if found:
                    problems.append(f"{rel}: coordinates ({', '.join(sorted(found))})")
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
