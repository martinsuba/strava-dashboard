"""Derived site JSON (docs/ARCHITECTURE.md, "Site JSON"). Never contains coordinates.

Deterministic: nothing here reads the clock, no set iteration. Definitions (see ARCHITECTURE.md):
rank = position by elapsed time among all efforts of a segment (ties: earlier start wins);
is_pr = rank 1; is_pr_at_time = faster than every earlier effort (first effort counts);
avg_s = mean elapsed rounded to int; per_year buckets by the UTC calendar year of the effort start.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sdash.activities import Activity
from sdash.match import Effort
from sdash.segments import Segment


@dataclass(frozen=True)
class SegmentResult:
    segment: Segment
    ref_length_m: float
    efforts: list[Effort]


def iso_utc(epoch_s: float) -> str:
    return datetime.fromtimestamp(epoch_s, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _ranked(efforts: Sequence[Effort]) -> list[tuple[Effort, int, bool]]:
    """Chronological (effort, rank, is_pr_at_time); rank 1 = fastest, ties: earlier start first."""
    chrono = sorted(efforts, key=lambda e: (e.start_t, e.activity_id))
    by_speed = sorted(chrono, key=lambda e: (e.elapsed_s, e.start_t, e.activity_id))
    rank = {id(e): i for i, e in enumerate(by_speed, 1)}
    out: list[tuple[Effort, int, bool]] = []
    best: int | None = None
    for e in chrono:
        out.append((e, rank[id(e)], best is None or e.elapsed_s < best))
        best = e.elapsed_s if best is None else min(best, e.elapsed_s)
    return out


def _segment_json(result: SegmentResult, ride_names: dict[str, str]) -> dict[str, Any]:
    slug = result.segment.slug
    ranked = _ranked(result.efforts)
    pr_s = min((e.elapsed_s for e, _, _ in ranked), default=0)
    efforts: list[dict[str, Any]] = []
    for e, rank, is_pr_at_time in ranked:
        efforts.append(
            {
                "segment_slug": slug,
                "activity_id": e.activity_id,
                "ride_name": ride_names.get(e.activity_id, ""),
                "start_t": e.start_t,
                "elapsed_s": e.elapsed_s,
                "distance_m": e.distance_m,
                "avg_kmh": round(e.distance_m / e.elapsed_s * 3.6, 1) if e.elapsed_s else 0.0,
                "rank": rank,
                "gap_to_pr_s": e.elapsed_s - pr_s,
                "is_pr_at_time": is_pr_at_time,
            }
        )
    years: dict[int, list[int]] = defaultdict(list)
    for e, _, _ in ranked:
        years[datetime.fromtimestamp(e.start_t, UTC).year].append(e.elapsed_s)
    return {
        "name": result.segment.name,
        "ref_length_m": round(result.ref_length_m),
        "efforts": efforts,
        "per_year": [
            {"year": y, "count": len(v), "best_s": min(v)} for y, v in sorted(years.items())
        ],
    }


def write_site_data(
    out: Path, activities: Sequence[Activity], results: Sequence[SegmentResult]
) -> None:
    """Replace the JSON files in `out` with index.json and segments/<slug>.json."""
    # Only the files this writer owns; anything else in `out` is left alone.
    for stale in [
        out / "index.json",
        *sorted((out / "segments").glob("*.json")),
        *sorted((out / "rides").glob("*.json")),
    ]:
        stale.unlink(missing_ok=True)
    ride_names = {a.id: a.name for a in activities}
    ride_dates = {a.id: iso_utc(a.date.timestamp()) for a in activities}
    ride_efforts: dict[str, list[dict[str, Any]]] = defaultdict(list)

    index_segments: list[dict[str, Any]] = []
    for r in results:
        ranked = _ranked(r.efforts)
        pr = min(ranked, key=lambda t: t[1], default=None)
        pr_s = pr[0].elapsed_s if pr else None
        avg_s = round(sum(e.elapsed_s for e, _, _ in ranked) / len(ranked)) if ranked else None
        index_segments.append(
            {
                "slug": r.segment.slug,
                "name": r.segment.name,
                "efforts": len(ranked),
                "pr_s": pr_s,
                "pr_date": (
                    ride_dates.get(pr[0].activity_id, iso_utc(pr[0].start_t)) if pr else None
                ),
            }
        )
        for e, rank, at_time in ranked:
            assert pr_s is not None
            ride_efforts[e.activity_id].append(
                {
                    "slug": r.segment.slug,
                    "name": r.segment.name,
                    "elapsed_s": e.elapsed_s,
                    "pr_s": pr_s,
                    "avg_s": avg_s,
                    "gap_to_pr_s": e.elapsed_s - pr_s,
                    "rank": rank,
                    "of": len(ranked),
                    "is_pr": rank == 1,
                    "is_pr_at_time": at_time,
                }
            )
        _write_json(out / "segments" / f"{r.segment.slug}.json", _segment_json(r, ride_names))

    rides = sorted(activities, key=lambda a: (a.date, a.id), reverse=True)
    for a in rides:
        _write_json(
            out / "rides" / f"{a.id}.json",
            {
                "id": a.id,
                "date": ride_dates[a.id],
                "name": a.name,
                "km": round(a.distance_km, 1),
                "elapsed_s": a.elapsed_s,
                "moving_s": a.moving_s,
                "gear": a.gear,
                "efforts": ride_efforts.get(a.id, []),
            },
        )
    _write_json(
        out / "index.json",
        {
            "generated": ride_dates[rides[0].id] if rides else None,
            "segments": index_segments,
            "rides": [
                {
                    "id": a.id,
                    "date": ride_dates[a.id],
                    "name": a.name,
                    "km": round(a.distance_km, 1),
                    "n_efforts": len(ride_efforts.get(a.id, [])),
                }
                for a in rides
            ],
        },
    )
