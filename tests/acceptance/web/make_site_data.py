#!/usr/bin/env python3
"""Generate tests/acceptance/web/site-data/: a synthetic site-data set in the exact JSON shape of
docs/ARCHITECTURE.md "Site JSON" (index.json, segments/<slug>.json, rides/<id>.json).

All names, IDs, dates and times are made up. No coordinates. Deterministic: re-running produces
byte-identical files. The web acceptance tests (tests/acceptance/web/) assert on these values, so
changing this data changes what those tests mean: such a change needs a test-review.

Run: python3 tests/acceptance/web/make_site_data.py
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent / "site-data"

# id, date (UTC), name, km, moving_s, elapsed_s, gear
RIDES = [
    ("3000000101", "2019-05-04T08:10:00Z", "Morning loop", 28.4, 3720, 3900, "Old steel bike"),
    ("3000000102", "2020-07-19T09:00:00Z", "Hill repeats", 31.0, 4380, 4700, "Old steel bike"),
    ("3000000103", "2021-06-13T07:30:00Z", "Hill repeats", 30.8, 4320, 4555, "Road bike"),
    ("3000000104", "2023-09-10T16:45:00Z", "Evening spin", 25.5, 3480, 3611, "Road bike"),
    ("3000000105", "2024-06-12T16:20:00Z", "Hill repeats", 31.2, 4210, 4502, "Road bike"),
    ("3000000106", "2025-05-04T10:00:00Z", "Gravel detour", 44.1, 6600, 7020, "Gravel bike"),
    ("3000000107", "2026-06-07T07:15:00Z", "Sunday long ride", 88.3, 12000, 13020, "Road bike"),
    ("3000000108", "2026-10-18T15:05:00Z", "Evening loop", 42.6, 5892, 6400, "Road bike"),
    ("3000000109", "2026-09-01T12:00:00Z", "Recovery spin", 18.0, 2700, 2760, "Road bike"),
]

# slug, name, ref_length_m, efforts: ride id -> elapsed_s (segment start = ride start + offset)
SEGMENTS = [
    (
        "hill-road-climb",
        "Hill Road climb",
        2400,
        {
            "3000000101": 456,
            "3000000102": 395,
            "3000000103": 379,
            "3000000104": 372,
            "3000000105": 341,
            "3000000106": 377,
            "3000000107": 355,
            "3000000108": 365,
        },
    ),
    (
        "lakeside-flat",
        "Lakeside flat",
        1800,
        {"3000000104": 252, "3000000106": 238, "3000000108": 260},
    ),
    ("quarry-descent", "Quarry descent", 900, {}),
]
START_OFFSET_S = 900  # efforts start 15 min into the ride

# Rides are deliberately NOT stored newest-first: the UI must sort (REQ-006).
INDEX_RIDE_ORDER = [
    "3000000104", "3000000108", "3000000101", "3000000109", "3000000106",
    "3000000102", "3000000107", "3000000103", "3000000105",
]  # fmt: skip


def epoch(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp())


def dump(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n")


def main() -> None:
    rides = {r[0]: r for r in RIDES}
    ride_efforts: dict[str, list[dict[str, object]]] = {r[0]: [] for r in RIDES}
    index_segments = []
    if OUT.exists():
        shutil.rmtree(OUT)

    for slug, name, length, efforts in SEGMENTS:
        chrono = sorted(efforts.items(), key=lambda kv: rides[kv[0]][1])
        by_time = sorted(efforts.items(), key=lambda kv: (kv[1], rides[kv[0]][1]))
        rank = {rid: i + 1 for i, (rid, _) in enumerate(by_time)}
        pr_s = by_time[0][1] if by_time else None
        avg_s = round(sum(efforts.values()) / len(efforts)) if efforts else None
        best_so_far: int | None = None
        seg_efforts = []
        for rid, elapsed in chrono:
            is_pr_at_time = best_so_far is None or elapsed < best_so_far
            best_so_far = elapsed if best_so_far is None else min(best_so_far, elapsed)
            assert pr_s is not None and avg_s is not None
            seg_efforts.append(
                {
                    "segment_slug": slug,
                    "activity_id": rid,
                    "ride_name": rides[rid][2],
                    "start_t": epoch(rides[rid][1]) + START_OFFSET_S,
                    "elapsed_s": elapsed,
                    "distance_m": length,
                    "avg_kmh": round(length / 1000 / (elapsed / 3600), 1),
                    "rank": rank[rid],
                    "gap_to_pr_s": elapsed - pr_s,
                    "is_pr_at_time": is_pr_at_time,
                }
            )
            ride_efforts[rid].append(
                {
                    "slug": slug,
                    "name": name,
                    "elapsed_s": elapsed,
                    "pr_s": pr_s,
                    "avg_s": avg_s,
                    "gap_to_pr_s": elapsed - pr_s,
                    "rank": rank[rid],
                    "of": len(efforts),
                    "is_pr": rank[rid] == 1,
                    "is_pr_at_time": is_pr_at_time,
                }
            )
        years: dict[int, list[int]] = {}
        for rid, elapsed in chrono:
            years.setdefault(int(rides[rid][1][:4]), []).append(elapsed)
        per_year = [
            {"year": y, "count": len(v), "best_s": min(v)} for y, v in sorted(years.items())
        ]
        dump(
            OUT / "segments" / f"{slug}.json",
            {"name": name, "ref_length_m": length, "efforts": seg_efforts, "per_year": per_year},
        )
        pr_date = rides[by_time[0][0]][1] if by_time else None
        index_segments.append(
            {"slug": slug, "name": name, "efforts": len(efforts), "pr_s": pr_s, "pr_date": pr_date}
        )

    for rid, date, name, km, moving, elapsed, gear in RIDES:
        dump(
            OUT / "rides" / f"{rid}.json",
            {
                "id": rid,
                "date": date,
                "name": name,
                "km": km,
                "elapsed_s": elapsed,
                "moving_s": moving,
                "gear": gear,
                "efforts": ride_efforts[rid],
            },
        )
    index_rides = [
        {
            "id": rid,
            "date": rides[rid][1],
            "name": rides[rid][2],
            "km": rides[rid][3],
            "n_efforts": len(ride_efforts[rid]),
        }
        for rid in INDEX_RIDE_ORDER
    ]
    generated = max(r[1] for r in RIDES)  # deterministic: newest ride, not the wall clock
    assert generated == datetime(2026, 10, 18, 15, 5, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    dump(
        OUT / "index.json",
        {"generated": generated, "segments": index_segments, "rides": index_rides},
    )


if __name__ == "__main__":
    main()
