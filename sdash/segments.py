"""segments.yaml: load segment definitions and derive slugs (REQ-003).

Every problem is a SegmentError whose message names the segment and the problem. segments.yaml is
rewritten from the parsed segments (same order, deterministic formatting), so comments are not kept.
"""

from __future__ import annotations

import csv
import json
import math
import os
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


FIELDS = ("name", "ref_activity", "start", "end")
STRAVA_HEADER = (
    "Segment Name",
    "Activity ID",
    "Starting Latitude",
    "Starting Longitude",
    "Ending Latitude",
    "Ending Longitude",
)


MAX_NAME_LEN = 120
_BAD_CATEGORIES = {"Cc", "Cs", "Co", "Cn", "Zl", "Zp"}


def _short(text: str | int, limit: int = 80) -> str:
    """repr of `text`, cut to `limit` characters so error messages stay small."""
    text = str(text)
    return repr(text if len(text) <= limit else text[:limit] + "\u2026")


def _label(entry: dict[str, Any], index: int) -> str:
    name = entry.get("name")
    if isinstance(name, str) and name.strip():
        return f"segment {_short(name)}"
    return f"segment #{index}" if index else "new segment"


def _check_name(name: object, label: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise SegmentError(f"{label}: name must be a non-empty text")
    if len(name) > MAX_NAME_LEN:
        raise SegmentError(f"{label}: name is longer than {MAX_NAME_LEN} characters")
    for ch in name:
        if unicodedata.category(ch) in _BAD_CATEGORIES:
            raise SegmentError(
                f"{label}: name contains a control or invalid character U+{ord(ch):04X}"
            )
    return name


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _point(entry: dict[str, Any], key: str, label: str) -> tuple[float, float]:
    value = entry[key]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise SegmentError(f"{label}: {key} must be [lat, lon] (two numbers)")
    lat, lon = _number(value[0]), _number(value[1])
    if lat is None or lon is None:
        raise SegmentError(f"{label}: {key} must be [lat, lon] with numeric coordinates")
    if not -90.0 <= lat <= 90.0:
        raise SegmentError(f"{label}: {key} latitude {lat} is out of range [-90, 90]")
    if not -180.0 <= lon <= 180.0:
        raise SegmentError(f"{label}: {key} longitude {lon} is out of range [-180, 180]")
    return lat, lon


def segment_from_entry(entry: object, index: int = 0) -> Segment:
    """Validate one segments.yaml entry; `index` (1-based) names it if it has no usable name."""
    if not isinstance(entry, dict):
        raise SegmentError(f"segment #{index}: must be a mapping with {', '.join(FIELDS)}")
    label = _label(entry, index)
    for key in FIELDS:
        if key not in entry:
            raise SegmentError(f"{label}: missing field {key}")
    unknown = sorted(str(k) for k in entry if k not in FIELDS)
    if unknown:
        raise SegmentError(
            f"{label}: unknown field {', '.join(unknown)} (allowed: {', '.join(FIELDS)})"
        )
    name = _check_name(entry["name"], label)
    ref = entry["ref_activity"]
    if (
        isinstance(ref, bool)
        or not isinstance(ref, (int, str))
        or not re.fullmatch(r"[0-9]+", str(ref))
    ):
        shown = (
            _short(ref)
            if isinstance(ref, (str, int)) and not isinstance(ref, bool)
            else type(ref).__name__
        )
        raise SegmentError(f"{label}: ref_activity {shown} must be an activity ID (digits only)")
    return Segment(
        name=name,
        slug=slugify(name),
        ref_activity=str(ref),
        start=_point(entry, "start", label),
        end=_point(entry, "end", label),
    )


def check_unique(segments: list[Segment]) -> None:
    """Names must be unique and must not share a slug (the slug is the page URL)."""
    names: dict[str, str] = {}
    slugs: dict[str, str] = {}
    for seg in segments:
        if seg.name in names:
            raise SegmentError(f"segment {_short(seg.name)}: duplicate name")
        if seg.slug in slugs:
            raise SegmentError(
                f"segment {_short(seg.name)}: slug {seg.slug!r} collides with segment "
                f"{_short(slugs[seg.slug])}: rename one of them"
            )
        names[seg.name] = seg.name
        slugs[seg.slug] = seg.name


def _read_entries(path: Path) -> list[object]:
    """The raw entries of segments.yaml; SegmentError when the file itself is unusable."""
    if not path.is_file():
        raise SegmentError(f"{path.name} not found in {path.parent}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise SegmentError(f"{path.name}: invalid YAML: {exc}") from exc
    if data is None:
        data = []
    if not isinstance(data, list):
        raise SegmentError(f"{path.name} must be a list of segments")
    return data


def load_segments(path: Path) -> list[Segment]:
    segments = [segment_from_entry(entry, i) for i, entry in enumerate(_read_entries(path), 1)]
    check_unique(segments)
    return segments


def load_segments_lenient(path: Path) -> tuple[list[Segment], list[str]]:
    """(valid segments, problems). One bad segment never hides the others.

    Invalid entries, later duplicate names and later slug collisions are skipped (the first
    occurrence is kept); each is one problem message that names the segment. An unusable file
    (missing, invalid YAML, not a list) still raises SegmentError.
    """
    segments: list[Segment] = []
    problems: list[str] = []
    names: set[str] = set()
    slugs: dict[str, str] = {}
    for i, entry in enumerate(_read_entries(path), 1):
        try:
            seg = segment_from_entry(entry, i)
        except SegmentError as exc:
            problems.append(str(exc))
            continue
        if seg.name in names:
            problems.append(f"segment {_short(seg.name)}: duplicate name")
        elif seg.slug in slugs:
            problems.append(
                f"segment {_short(seg.name)}: slug {seg.slug!r} collides with segment "
                f"{_short(slugs[seg.slug])}: rename one of them"
            )
        else:
            names.add(seg.name)
            slugs[seg.slug] = seg.name
            segments.append(seg)
    return segments, problems


def load_segments_or_empty(path: Path) -> list[Segment]:
    """Like load_segments, but a missing file means no segments yet."""
    return load_segments(path) if path.exists() else []


def dump_segments(segments: list[Segment]) -> str:
    """Deterministic YAML (JSON scalars are valid YAML); one block per segment, in order."""
    if not segments:
        return "[]\n"
    lines: list[str] = []
    for seg in segments:
        lines.append(f"- name: {json.dumps(seg.name, ensure_ascii=False)}")
        lines.append(f"  ref_activity: {json.dumps(seg.ref_activity)}")
        lines.append(f"  start: {json.dumps(list(seg.start))}")
        lines.append(f"  end: {json.dumps(list(seg.end))}")
    return "\n".join(lines) + "\n"


def write_segments(path: Path, segments: list[Segment]) -> None:
    """Validate, then replace `path` atomically (temp file + os.replace); old file kept on error."""
    check_unique(segments)
    text = dump_segments(segments)
    try:
        again = [segment_from_entry(e, i) for i, e in enumerate(yaml.safe_load(text) or [], 1)]
    except (yaml.YAMLError, SegmentError) as exc:
        raise SegmentError(
            f"{path.name}: refusing to write a file that cannot be read back: {exc}"
        ) from exc
    if again != segments:
        raise SegmentError(
            f"{path.name}: refusing to write a file that does not read back the same"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


@dataclass(frozen=True)
class ImportReport:
    added: int
    skipped_existing: int
    invalid: list[tuple[int, str]]  # (CSV row number, reason); row 1 is the header


def import_strava_csv(csv_path: Path, segments_path: Path) -> ImportReport:
    """Append rows of Strava's segments.csv whose names are new; bad rows are skipped and reported.

    The file is written only if something was added, and only with valid segments.
    """
    if not csv_path.is_file():
        raise SegmentError(f"{csv_path} not found: run `sdash import` first")
    existing = load_segments_or_empty(segments_path)
    known_names = {s.name for s in existing}
    known_slugs = {s.slug: s.name for s in existing}
    new: list[Segment] = []
    skipped = 0
    invalid: list[tuple[int, str]] = []
    try:
        with csv_path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            header = [h.strip() for h in next(reader, [])]
            missing = [h for h in STRAVA_HEADER if h not in header]
            if missing:
                raise SegmentError(f"{csv_path.name}: missing column {', '.join(missing)}")
            col = {h: header.index(h) for h in STRAVA_HEADER}
            for row_no, row in enumerate(reader, 2):
                if not any(c.strip() for c in row):
                    continue
                try:
                    seg = _strava_row(row, col, row_no)
                    if seg.name in known_names:
                        skipped += 1
                        continue
                    if seg.slug in known_slugs:
                        raise SegmentError(
                            f"segment {_short(seg.name)}: slug {seg.slug!r} collides with segment "
                            f"{_short(known_slugs[seg.slug])}"
                        )
                except SegmentError as exc:
                    invalid.append((row_no, str(exc)))
                    continue
                known_names.add(seg.name)
                known_slugs[seg.slug] = seg.name
                new.append(seg)
    except (csv.Error, UnicodeDecodeError) as exc:
        raise SegmentError(f"{csv_path.name}: cannot read: {exc}") from exc
    if new:
        write_segments(segments_path, existing + new)
    return ImportReport(len(new), skipped, invalid)


def _strava_row(row: list[str], col: dict[str, int], row_no: int) -> Segment:
    def cell(header: str) -> str:
        i = col[header]
        return row[i].strip() if i < len(row) else ""

    def num(header: str) -> object:
        try:
            return float(cell(header))
        except ValueError:
            return cell(header)

    entry = {
        "name": cell("Segment Name"),
        "ref_activity": cell("Activity ID"),
        "start": [num("Starting Latitude"), num("Starting Longitude")],
        "end": [num("Ending Latitude"), num("Ending Longitude")],
    }
    return segment_from_entry(entry, row_no)
