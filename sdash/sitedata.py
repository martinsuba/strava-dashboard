"""Derived site JSON (docs/ARCHITECTURE.md, "Site JSON"). Never contains coordinates.

Deterministic: nothing here reads the clock. `rides/<id>.json` and richer stats arrive with T-007.
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


def _segment_json(result: SegmentResult, ride_names: dict[str, str]) -> dict[str, Any]:
    slug = result.segment.slug
    chrono = sorted(result.efforts, key=lambda e: (e.start_t, e.activity_id))
    by_speed = sorted(chrono, key=lambda e: (e.elapsed_s, e.start_t))
    rank = {id(e): i for i, e in enumerate(by_speed, 1)}
    pr_s = by_speed[0].elapsed_s if by_speed else 0
    efforts: list[dict[str, Any]] = []
    best_so_far: int | None = None
    for e in chrono:
        is_pr_at_time = best_so_far is None or e.elapsed_s < best_so_far
        best_so_far = e.elapsed_s if best_so_far is None else min(best_so_far, e.elapsed_s)
        efforts.append(
            {
                "segment_slug": slug,
                "activity_id": e.activity_id,
                "ride_name": ride_names.get(e.activity_id, ""),
                "start_t": e.start_t,
                "elapsed_s": e.elapsed_s,
                "distance_m": e.distance_m,
                "avg_kmh": round(e.distance_m / e.elapsed_s * 3.6, 1) if e.elapsed_s else 0.0,
                "rank": rank[id(e)],
                "gap_to_pr_s": e.elapsed_s - pr_s,
                "is_pr_at_time": is_pr_at_time,
            }
        )
    years: dict[int, list[int]] = defaultdict(list)
    for e in chrono:
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
    for stale in list(out.rglob("*.json")) if out.is_dir() else []:
        stale.unlink()
    ride_names = {a.id: a.name for a in activities}
    n_efforts: dict[str, int] = defaultdict(int)
    for r in results:
        for e in r.efforts:
            n_efforts[e.activity_id] += 1

    index_segments: list[dict[str, Any]] = []
    for r in results:
        best = min(r.efforts, key=lambda e: (e.elapsed_s, e.start_t), default=None)
        index_segments.append(
            {
                "slug": r.segment.slug,
                "name": r.segment.name,
                "efforts": len(r.efforts),
                "pr_s": best.elapsed_s if best else None,
                "pr_date": iso_utc(best.start_t) if best else None,
            }
        )
        _write_json(out / "segments" / f"{r.segment.slug}.json", _segment_json(r, ride_names))

    rides = sorted(activities, key=lambda a: (a.date, a.id), reverse=True)
    _write_json(
        out / "index.json",
        {
            "generated": iso_utc(rides[0].date.timestamp()) if rides else None,
            "segments": index_segments,
            "rides": [
                {
                    "id": a.id,
                    "date": iso_utc(a.date.timestamp()),
                    "name": a.name,
                    "km": round(a.distance_km, 1),
                    "n_efforts": n_efforts.get(a.id, 0),
                }
                for a in rides
            ],
        },
    )
