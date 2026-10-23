"""Site JSON writer (REQ-005): schema, ranks, no coordinates."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sdash.activities import Activity
from sdash.match import Effort
from sdash.segments import Segment
from sdash.sitedata import SegmentResult, write_site_data


def _act(i: str, day: int, name: str) -> Activity:
    return Activity(
        id=i,
        date=datetime(2026, 5, day, 8, 0, tzinfo=UTC),
        name=name,
        type="Ride",
        gear="",
        filename="",
        distance_km=12.345,
        elapsed_s=1,
        moving_s=1,
    )


SEG = Segment(
    name="River path north",
    slug="river-path-north",
    ref_activity="1",
    start=(-47.0, -134.0),
    end=(-46.98, -134.0),
)
EMPTY = Segment(
    name="Empty", slug="empty", ref_activity="1", start=(-47.0, -134.0), end=(-46.9, -134.0)
)


def _eff(act: str, start_t: int, elapsed: int) -> Effort:
    return Effort(activity_id=act, start_t=start_t, elapsed_s=elapsed, distance_m=2000.0)


def _build(out: Path) -> None:
    acts = [_act("1", 1, "First"), _act("2", 3, "Second"), _act("3", 2, "Third")]
    efforts = {
        "river-path-north": [
            _eff("1", 1777622400, 400),
            _eff("2", 1777795200, 460),
            _eff("3", 1777708800, 380),
        ],
        "empty": [],
    }
    results = [
        SegmentResult(SEG, 2001.4, efforts["river-path-north"]),
        SegmentResult(EMPTY, 9000.0, []),
    ]
    write_site_data(out, acts, results)


def test_files_and_index(tmp_path: Path) -> None:
    out = tmp_path / "o"
    _build(out)
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()) == [
        "index.json",
        "segments/empty.json",
        "segments/river-path-north.json",
    ]
    index = json.loads((out / "index.json").read_text())
    assert index["generated"] == "2026-05-03T08:00:00Z"  # newest ride start, not the clock
    assert index["segments"] == [
        {"slug": "river-path-north", "name": "River path north", "efforts": 3,
         "pr_s": 380, "pr_date": "2026-05-02T08:00:00Z"},
        {"slug": "empty", "name": "Empty", "efforts": 0, "pr_s": None, "pr_date": None},
    ]  # fmt: skip
    rides = {r["id"]: r for r in index["rides"]}
    assert rides["2"] == {
        "id": "2", "date": "2026-05-03T08:00:00Z", "name": "Second", "km": 12.3, "n_efforts": 1,
    }  # fmt: skip


def test_segment_json_ranks_and_pr_at_time(tmp_path: Path) -> None:
    out = tmp_path / "o"
    _build(out)
    seg = json.loads((out / "segments" / "river-path-north.json").read_text())
    assert seg["name"] == "River path north"
    assert seg["ref_length_m"] == 2001
    by_act = {e["activity_id"]: e for e in seg["efforts"]}
    assert [by_act[a]["rank"] for a in "123"] == [2, 3, 1]
    assert [by_act[a]["gap_to_pr_s"] for a in "123"] == [20, 80, 0]
    assert [by_act[a]["is_pr_at_time"] for a in "123"] == [True, False, True]
    first = by_act["1"]
    assert first["ride_name"] == "First"
    assert first["segment_slug"] == "river-path-north"
    assert first["avg_kmh"] == 18.0
    assert first["start_t"] == 1777622400
    assert [e["activity_id"] for e in seg["efforts"]] == ["1", "3", "2"]  # chronological
    assert seg["per_year"] == [{"year": 2026, "count": 3, "best_s": 380}]


def test_empty_segment(tmp_path: Path) -> None:
    out = tmp_path / "o"
    _build(out)
    seg = json.loads((out / "segments" / "empty.json").read_text())
    assert seg["efforts"] == [] and seg["per_year"] == []


def test_no_coordinates_in_output(tmp_path: Path) -> None:
    out = tmp_path / "o"
    _build(out)
    text = "".join(p.read_text() for p in out.rglob("*.json"))
    for forbidden in ('"lat"', '"lon"', '"start"', '"end"', "-47.0", "-134.0"):
        assert forbidden not in text


def test_rebuild_is_byte_identical_and_replaces_stale_files(tmp_path: Path) -> None:
    out = tmp_path / "o"
    (out / "segments").mkdir(parents=True)
    (out / "segments" / "stale.json").write_text("{}")
    _build(out)
    first = {p.name: p.read_bytes() for p in out.rglob("*.json")}
    assert "stale.json" not in first
    _build(out)
    assert first == {p.name: p.read_bytes() for p in out.rglob("*.json")}


def test_rebuild_leaves_foreign_json_alone(tmp_path: Path) -> None:
    out = tmp_path / "o"
    keep = [out / "keep.json", out / "deep" / "nested" / "keep.json"]
    for k in keep:
        k.parent.mkdir(parents=True, exist_ok=True)
        k.write_text("{}")
    _build(out)
    _build(out)
    assert all(k.read_text() == "{}" for k in keep)
