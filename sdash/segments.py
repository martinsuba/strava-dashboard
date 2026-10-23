"""segments.yaml: load segment definitions and derive slugs (REQ-003).

Full validation messages (ranges, duplicates) and `segment add/import-strava` arrive with T-006.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class SegmentError(Exception):
    """A problem with segments.yaml; the message names the segment and the problem."""


@dataclass(frozen=True)
class Segment:
    name: str
    slug: str
    ref_activity: str
    start: tuple[float, float]  # (lat, lon)
    end: tuple[float, float]


def slugify(name: str) -> str:
    """'River path north' -> 'river-path-north'; lowercase ASCII words joined by '-'."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    if not slug:
        raise SegmentError(f"segment {name!r}: cannot derive a slug from the name")
    return slug


def _point(entry: dict[str, Any], key: str, name: str) -> tuple[float, float]:
    value = entry[key]
    try:
        lat, lon = value
        return float(lat), float(lon)
    except (TypeError, ValueError) as exc:
        raise SegmentError(f"segment {name!r}: {key} must be [lat, lon]") from exc


def load_segments(path: Path) -> list[Segment]:
    if not path.is_file():
        raise SegmentError(f"{path.name} not found in {path.parent}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SegmentError(f"{path.name}: invalid YAML: {exc}") from exc
    if data is None:
        data = []
    if not isinstance(data, list):
        raise SegmentError(f"{path.name} must be a list of segments")
    segments: list[Segment] = []
    for i, entry in enumerate(data, 1):
        if not isinstance(entry, dict) or "name" not in entry:
            raise SegmentError(f"segment #{i}: missing field name")
        name = str(entry["name"])
        for key in ("ref_activity", "start", "end"):
            if key not in entry:
                raise SegmentError(f"segment {name!r}: missing field {key}")
        segments.append(
            Segment(
                name=name,
                slug=slugify(name),
                ref_activity=str(entry["ref_activity"]),
                start=_point(entry, "start", name),
                end=_point(entry, "end", name),
            )
        )
    return segments
