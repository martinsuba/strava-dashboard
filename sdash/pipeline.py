"""parse -> match -> build-data steps over a data dir (raw/, cache/, segments.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sdash.activities import Activity, read_activities
from sdash.match import find_efforts
from sdash.segments import Segment, SegmentError, load_segments
from sdash.sitedata import SegmentResult, write_site_data
from sdash.tracks import Track, parse_track, read_cache, write_cache


class PipelineError(Exception):
    """A step failed in a way the user must fix; the message goes to stderr."""


@dataclass(frozen=True)
class ParseReport:
    parsed: int
    failed: list[tuple[str, str]]  # (activity id, reason)


def cycling_activities(data_dir: Path) -> list[Activity]:
    csv_path = data_dir / "raw" / "activities.csv"
    if not csv_path.is_file():
        raise PipelineError(f"{csv_path} not found: run `sdash import` first")
    try:
        return [a for a in read_activities(csv_path) if a.is_cycling]
    except ValueError as exc:
        raise PipelineError(str(exc)) from exc


def cache_path(data_dir: Path, activity_id: str) -> Path:
    return data_dir / "cache" / f"{activity_id}.json.gz"


def parse_rides(data_dir: Path) -> ParseReport:
    """Parse every cycling ride into cache/<id>.json.gz; a broken file is reported, not fatal."""
    parsed = 0
    failed: list[tuple[str, str]] = []
    for act in cycling_activities(data_dir):
        if not act.filename:
            failed.append((act.id, "no file in activities.csv"))
            continue
        path = data_dir / "raw" / act.filename
        try:
            track = parse_track(path)
        except (OSError, ValueError) as exc:
            failed.append((act.id, str(exc)))
            continue
        if not track.t:
            failed.append((act.id, "no positions in file"))
            continue
        write_cache(cache_path(data_dir, act.id), track)
        parsed += 1
    return ParseReport(parsed, failed)


def _ref_length(segment: Segment, ref: Track | None) -> float:
    if ref is None:
        raise PipelineError(
            f"segment {segment.name!r}: reference activity {segment.ref_activity} "
            "has no parsed track"
        )
    efforts = find_efforts(ref, segment.start, segment.end)
    if not efforts:
        raise PipelineError(
            f"segment {segment.name!r}: reference activity {segment.ref_activity} "
            "does not pass both start and end"
        )
    return float(efforts[0].distance_m)


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
            tracks[act.id] = read_cache(path)
    ref_cache: dict[str, Track | None] = {}
    results: list[SegmentResult] = []
    for seg in segments:
        if seg.ref_activity not in ref_cache:
            path = cache_path(data_dir, seg.ref_activity)
            ref_cache[seg.ref_activity] = tracks.get(seg.ref_activity) or (
                read_cache(path) if path.is_file() else None
            )
        length = _ref_length(seg, ref_cache[seg.ref_activity])
        efforts = [
            e
            for act in activities
            if act.id in tracks
            for e in find_efforts(tracks[act.id], seg.start, seg.end, act.id)
        ]
        results.append(SegmentResult(seg, length, efforts))
    return activities, results


def build_data(data_dir: Path, out: Path) -> list[SegmentResult]:
    activities, results = match_segments(data_dir)
    write_site_data(out, activities, results)
    return results
