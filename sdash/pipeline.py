"""parse -> match -> build-data steps over a data dir (raw/, cache/, segments.yaml)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sdash.activities import Activity, read_activities
from sdash.match import GATE_M, Reference, find_efforts, reference_from
from sdash.segments import Segment, SegmentError, load_segments
from sdash.sitedata import SegmentResult, write_site_data
from sdash.tracks import (
    Track,
    parse_track,
    read_cache,
    read_cache_if_fresh,
    source_stamp,
    write_cache,
)


class PipelineError(Exception):
    """A step failed in a way the user must fix; the message goes to stderr."""


@dataclass(frozen=True)
class ParseReport:
    parsed: int
    failed: list[tuple[str, str]]  # (activity id, reason)
    references: int = 0  # parsed non-ride reference tracks (not counted in `parsed`)


_ACTIVITY_ID = re.compile(r"[0-9]+")


def valid_activity_id(activity_id: str) -> bool:
    return _ACTIVITY_ID.fullmatch(activity_id) is not None


def cycling_rides(data_dir: Path) -> tuple[list[Activity], list[tuple[str, str]]]:
    """Cycling activities with a safe ID, and (id, reason) for rows that must be reported."""
    csv_path = data_dir / "raw" / "activities.csv"
    if not csv_path.is_file():
        raise PipelineError(f"{csv_path} not found: run `sdash import` first")
    bad: list[tuple[str, str]] = []
    try:
        rows = read_activities(csv_path, cycling_only=True, errors=bad)
    except ValueError as exc:
        raise PipelineError(str(exc)) from exc
    good: list[Activity] = []
    for a in rows:
        if valid_activity_id(a.id):
            good.append(a)
        else:
            bad.append((a.id, "activity ID is not a number"))
    return good, bad


def cycling_activities(data_dir: Path) -> list[Activity]:
    return cycling_rides(data_dir)[0]


def cache_path(data_dir: Path, activity_id: str) -> Path:
    if not valid_activity_id(activity_id):
        raise ValueError(f"invalid activity ID {activity_id!r}")
    return data_dir / "cache" / f"{activity_id}.json.gz"


def ride_file(data_dir: Path, filename: str) -> Path:
    """raw/<filename>, refusing anything that resolves outside raw/ (absolute, ../)."""
    raw = (data_dir / "raw").resolve()
    path = (raw / filename).resolve()
    if not path.is_relative_to(raw):
        raise ValueError(f"file name {filename!r} points outside raw/")
    return path


def reference_only_activities(data_dir: Path, rides: list[Activity]) -> list[Activity]:
    """Non-cycling activities used as a segment's reference (e.g. a hike): they get parsed too."""
    try:
        segments = load_segments(data_dir / "segments.yaml")
    except SegmentError:
        return []  # reported by `match`, which validates segments.yaml
    wanted = {seg.ref_activity for seg in segments if valid_activity_id(seg.ref_activity)}
    wanted -= {a.id for a in rides}
    if not wanted:
        return []
    try:
        rows = read_activities(data_dir / "raw" / "activities.csv", errors=[])
    except ValueError:
        return []
    return [a for a in rows if a.id in wanted and valid_activity_id(a.id)]


def parse_rides(data_dir: Path) -> ParseReport:
    """Parse every cycling ride (and non-ride segment reference) into cache/<id>.json.gz.

    A broken file is reported, not fatal.
    """
    parsed = 0
    activities, failed = cycling_rides(data_dir)
    extra = reference_only_activities(data_dir, activities)
    references = 0
    for act in activities + extra:
        is_reference = act in extra
        if not act.filename:
            failed.append((act.id, "no file in activities.csv"))
            continue
        cache = cache_path(data_dir, act.id)
        try:
            path = ride_file(data_dir, act.filename)
            stamp = source_stamp(path)
            if read_cache_if_fresh(cache, stamp) is not None:
                # unchanged (same size + mtime): not parsed again
                if is_reference:
                    references += 1
                else:
                    parsed += 1
                continue
            track = parse_track(path)
        except Exception as exc:  # one bad ride file must never abort the run
            cache.unlink(missing_ok=True)  # no stale data for a ride that cannot be read now
            failed.append((act.id, str(exc) or type(exc).__name__))
            continue
        if not track.t:
            cache.unlink(missing_ok=True)
            failed.append((act.id, "no positions in file"))
            continue
        write_cache(cache, track, stamp)
        if is_reference:
            references += 1
        else:
            parsed += 1
    return ParseReport(parsed, failed, references)


def _read_cache(path: Path) -> Track:
    try:
        return read_cache(path)
    except ValueError as exc:
        raise PipelineError(f"{exc}: run `sdash parse` again") from exc


def _reference(segment: Segment, ref: Track | None) -> Reference:
    if ref is None:
        raise PipelineError(
            f"segment {segment.name!r}: reference activity {segment.ref_activity} "
            "has no parsed track"
        )
    reference = reference_from(ref, segment.start, segment.end)
    if reference is None:
        raise PipelineError(
            f"segment {segment.name!r}: reference activity {segment.ref_activity} "
            "does not pass both start and end"
        )
    if reference.length_m < 2 * GATE_M:
        raise PipelineError(
            f"segment {segment.name!r}: reference activity {segment.ref_activity} gives a "
            f"segment of only {reference.length_m:.0f} m (start and end are too close or the "
            "track jitters at the gate)"
        )
    return reference


def match_segments(data_dir: Path) -> tuple[list[Activity], list[SegmentResult]]:
    """Validate segments.yaml and find efforts in every cached cycling ride."""
    try:
        segments = load_segments(data_dir / "segments.yaml")
    except SegmentError as exc:
        raise PipelineError(str(exc)) from exc
    activities = cycling_activities(data_dir)
    tracks: dict[str, Track] = {}
    for act in activities:
        path = cache_path(data_dir, act.id)
        if path.is_file():
            tracks[act.id] = _read_cache(path)
    ref_cache: dict[str, Track | None] = {}
    results: list[SegmentResult] = []
    for seg in segments:
        if not valid_activity_id(seg.ref_activity):
            raise PipelineError(
                f"segment {seg.name!r}: ref_activity {seg.ref_activity!r} must be an activity ID"
            )
        if seg.ref_activity not in ref_cache:
            path = cache_path(data_dir, seg.ref_activity)
            ref_cache[seg.ref_activity] = tracks.get(seg.ref_activity) or (
                _read_cache(path) if path.is_file() else None
            )
        reference = _reference(seg, ref_cache[seg.ref_activity])
        efforts = [
            e
            for act in activities
            if act.id in tracks
            for e in find_efforts(tracks[act.id], seg.start, seg.end, act.id, reference=reference)
        ]
        results.append(SegmentResult(seg, reference.length_m, efforts))
    return activities, results


def build_data(data_dir: Path, out: Path) -> list[SegmentResult]:
    activities, results = match_segments(data_dir)
    write_site_data(out, activities, results)
    return results
