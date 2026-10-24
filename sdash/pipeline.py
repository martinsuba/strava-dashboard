"""parse -> match -> build-data steps over a data dir (raw/, cache/, segments.yaml)."""

from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass
from pathlib import Path

from sdash.activities import Activity, read_activities
from sdash.match import GATE_M, Reference, find_efforts, reference_from
from sdash.segments import (
    Segment,
    SegmentError,
    check_unique,
    load_segments_lenient,
    load_segments_or_empty,
    segment_from_entry,
    write_segments,
)
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


def reference_only_activities(
    data_dir: Path, rides: list[Activity]
) -> tuple[list[Activity], list[tuple[str, str]]]:
    """Non-cycling activities used as a segment's reference (e.g. a hike): they get parsed too.

    Also returns (id, reason) for wanted reference rows that activities.csv holds but that cannot
    be read; those are never dropped silently.
    """
    try:
        segments, _ = load_segments_lenient(data_dir / "segments.yaml")
    except SegmentError:
        return [], []  # reported by `match`, which reads segments.yaml
    wanted = {seg.ref_activity for seg in segments if valid_activity_id(seg.ref_activity)}
    wanted -= {a.id for a in rides}
    if not wanted:
        return [], []
    errors: list[tuple[str, str]] = []
    try:
        rows = read_activities(data_dir / "raw" / "activities.csv", errors=errors)
    except ValueError as exc:
        raise PipelineError(str(exc)) from exc
    found = [a for a in rows if a.id in wanted and valid_activity_id(a.id)]
    return found, [(i, reason) for i, reason in errors if i in wanted]


def parse_rides(data_dir: Path) -> ParseReport:
    """Parse every cycling ride (and non-ride segment reference) into cache/<id>.json.gz.

    A broken file is reported, not fatal.
    """
    parsed = 0
    activities, failed = cycling_rides(data_dir)
    extra, reference_errors = reference_only_activities(data_dir, activities)
    extra_ids = {a.id for a in extra}
    failed += reference_errors
    references = 0
    for act in activities + extra:
        is_reference = act.id in extra_ids
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
            f"segment {segment.name!r}: reference activity {segment.ref_activity} does not pass "
            f"both start and end (at least {2 * GATE_M:.0f} m apart)"
        )
    return reference


@dataclass(frozen=True)
class MatchReport:
    activities: list[Activity]
    results: list[SegmentResult]  # valid segments only
    problems: list[str]  # segment-level problems; each names the segment and is skipped (exit 2)


def match_segments(data_dir: Path) -> MatchReport:
    """Read segments.yaml and find efforts in every cached cycling ride.

    A segment-level problem (invalid fields, duplicate name, unusable reference) is collected in
    `problems` and that segment skipped; the others are matched. An unreadable segments.yaml
    raises PipelineError.
    """
    try:
        segments, problems = load_segments_lenient(data_dir / "segments.yaml")
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
        if seg.ref_activity not in ref_cache:
            path = cache_path(data_dir, seg.ref_activity)
            ref_cache[seg.ref_activity] = tracks.get(seg.ref_activity) or (
                _read_cache(path) if path.is_file() else None
            )
        try:
            reference = _reference(seg, ref_cache[seg.ref_activity])
        except PipelineError as exc:
            problems.append(str(exc))
            continue
        efforts = [
            e
            for act in activities
            if act.id in tracks
            for e in find_efforts(tracks[act.id], seg.start, seg.end, act.id, reference=reference)
        ]
        results.append(SegmentResult(seg, reference.length_m, efforts))
    return MatchReport(activities, results, problems)


def build_data(data_dir: Path, out: Path) -> MatchReport:
    report = match_segments(data_dir)
    write_site_data(out, report.activities, report.results)
    return report


def _ride_track(data_dir: Path, activity_id: str) -> Track:
    """The cached track of an activity; parses (and caches) the file if it is not cached yet."""
    cache = cache_path(data_dir, activity_id)  # refuses non-numeric IDs
    if cache.is_file():
        return _read_cache(cache)
    csv_path = data_dir / "raw" / "activities.csv"
    if not csv_path.is_file():
        raise PipelineError(f"{csv_path} not found: run `sdash import` first")
    try:
        rows = read_activities(csv_path, errors=[])
    except ValueError as exc:
        raise PipelineError(str(exc)) from exc
    act = next((a for a in rows if a.id == activity_id), None)
    if act is None:
        raise PipelineError(f"activity {activity_id} not found in activities.csv")
    if not act.filename:
        raise PipelineError(f"activity {activity_id} has no file in activities.csv")
    try:
        path = ride_file(data_dir, act.filename)
        stamp = source_stamp(path)
        track = parse_track(path)
    except Exception as exc:
        raise PipelineError(f"activity {activity_id} cannot be read: {exc}") from exc
    if not track.t:
        raise PipelineError(f"activity {activity_id} has no positions")
    write_cache(cache, track, stamp)
    return track


def _position_at(track: Track, dist_m: float) -> tuple[float, float]:
    """(lat, lon) at cumulative distance `dist_m`, interpolated linearly between track points."""
    i = bisect.bisect_right(track.d, dist_m) - 1
    i = max(0, min(i, len(track.d) - 2))
    d0, d1 = track.d[i], track.d[i + 1]
    f = 0.0 if d1 == d0 else (dist_m - d0) / (d1 - d0)
    return (
        track.lat[i] + f * (track.lat[i + 1] - track.lat[i]),
        track.lon[i] + f * (track.lon[i + 1] - track.lon[i]),
    )


def add_segment(
    data_dir: Path, name: str, activity_id: str, from_km: float, to_km: float
) -> Segment:
    """Append a segment taken from `activity_id` between two distances (km) to segments.yaml."""
    if not (0 <= from_km < to_km):
        raise PipelineError(f"--from-km ({from_km}) must be >= 0 and less than --to-km ({to_km})")
    try:
        track = _ride_track(data_dir, activity_id)
    except ValueError as exc:
        raise PipelineError(str(exc)) from exc
    if len(track.d) < 2:
        raise PipelineError(f"activity {activity_id} has fewer than 2 track points")
    total_km = track.d[-1] / 1000
    if to_km * 1000 > track.d[-1] + 1e-6:
        raise PipelineError(
            f"--to-km {to_km} is beyond the end of activity {activity_id} ({total_km:.3f} km)"
        )
    length_m = (to_km - from_km) * 1000
    if length_m < 2 * GATE_M:
        raise PipelineError(
            f"segment {name!r} would be only {math.floor(length_m)} m long; the minimum is "
            f"{2 * GATE_M:.0f} m (two gates)"
        )
    start = _position_at(track, from_km * 1000)
    end = _position_at(track, to_km * 1000)
    path = data_dir / "segments.yaml"
    try:
        existing = load_segments_or_empty(path)
        seg = segment_from_entry(
            {"name": name, "ref_activity": activity_id, "start": list(start), "end": list(end)}
        )
        check_unique([*existing, seg])
    except SegmentError as exc:
        raise PipelineError(str(exc)) from exc
    _reference(seg, track)  # refuses a segment that match would reject (degenerate reference)
    try:
        write_segments(path, [*existing, seg])
    except (SegmentError, OSError) as exc:
        raise PipelineError(f"cannot write {path.name}: {exc}") from exc
    return seg
