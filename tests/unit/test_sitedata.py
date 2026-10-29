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
        "build-info.json",
        "index.json",
        "rides/1.json",
        "rides/2.json",
        "rides/3.json",
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


def _write(tmp_path: Path, acts: list[Activity], results: list[SegmentResult]) -> Path:
    out = tmp_path / "o"
    write_site_data(out, acts, results)
    return out


def _load(path: Path) -> dict:  # type: ignore[type-arg]
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def test_rank_ties_earlier_start_wins(tmp_path: Path) -> None:
    acts = [_act("1", 1, "A"), _act("2", 2, "B"), _act("3", 3, "C")]
    effs = [_eff("2", 200, 300), _eff("1", 100, 300), _eff("3", 300, 310)]
    out = _write(tmp_path, acts, [SegmentResult(SEG, 2000.0, effs)])
    seg = _load(out / "segments" / "river-path-north.json")
    assert {e["activity_id"]: e["rank"] for e in seg["efforts"]} == {"1": 1, "2": 2, "3": 3}
    assert _load(out / "rides" / "1.json")["efforts"][0]["is_pr"] is True
    assert _load(out / "rides" / "2.json")["efforts"][0]["is_pr"] is False
    # equal time is not faster than the earlier one: not a PR at the time
    assert [e["is_pr_at_time"] for e in seg["efforts"]] == [True, False, False]


def test_pr_at_time_sequence_and_ride_effort_fields(tmp_path: Path) -> None:
    acts = [_act(str(i), i, f"R{i}") for i in range(1, 6)]
    times = [400, 420, 390, 395, 380]
    effs = [_eff(str(i), 1000 * i, t) for i, t in enumerate(times, 1)]
    out = _write(tmp_path, acts, [SegmentResult(SEG, 2000.0, effs)])
    seg = _load(out / "segments" / "river-path-north.json")
    assert [e["is_pr_at_time"] for e in seg["efforts"]] == [True, False, True, False, True]
    ride = _load(out / "rides" / "4.json")
    assert ride["efforts"] == [
        {"slug": "river-path-north", "name": "River path north", "elapsed_s": 395, "pr_s": 380,
         "avg_s": 397, "median_s": 395, "slowest_s": 420, "gap_to_pr_s": 15, "rank": 3, "of": 5, "is_pr": False,
         "is_pr_at_time": False}
    ]  # fmt: skip
    assert list(ride) == [
        "id", "date", "name", "km", "elapsed_s", "moving_s", "gear", "efforts"
    ]  # fmt: skip


def test_average_is_rounded_mean(tmp_path: Path) -> None:
    acts = [_act("1", 1, "A"), _act("2", 2, "B")]
    effs = [_eff("1", 100, 301), _eff("2", 200, 304)]  # mean 302.5 -> 302 (round half even)
    out = _write(tmp_path, acts, [SegmentResult(SEG, 2000.0, effs)])
    assert _load(out / "rides" / "1.json")["efforts"][0]["avg_s"] == 302


def _ride_effort(tmp_path: Path, times: list[int]) -> dict[str, int]:
    acts = [_act(str(i), i, f"R{i}") for i in range(1, len(times) + 1)]
    effs = [_eff(str(i), 1000 * i, t) for i, t in enumerate(times, 1)]
    out = _write(tmp_path, acts, [SegmentResult(SEG, 2000.0, effs)])
    e = _load(out / "rides" / "1.json")["efforts"][0]
    return {"median_s": e["median_s"], "slowest_s": e["slowest_s"]}


def test_median_and_slowest_odd_count(tmp_path: Path) -> None:
    assert _ride_effort(tmp_path, [500, 300, 900]) == {"median_s": 500, "slowest_s": 900}


def test_median_even_count_mean_of_middle_rounded_half_even(tmp_path: Path) -> None:
    # middle values 301 and 304 -> 302.5 -> 302 (half even)
    assert _ride_effort(tmp_path, [300, 301, 304, 999])["median_s"] == 302
    # middle values 302 and 305 -> 303.5 -> 304 (half even)
    assert _ride_effort(tmp_path, [300, 302, 305, 999])["median_s"] == 304


def test_median_and_slowest_single_effort(tmp_path: Path) -> None:
    assert _ride_effort(tmp_path, [412]) == {"median_s": 412, "slowest_s": 412}


def test_per_year_uses_bratislava_calendar_year(tmp_path: Path) -> None:
    def ts(*a: int) -> int:
        return int(datetime(*a, tzinfo=UTC).timestamp())  # type: ignore[arg-type]

    effs = [
        _eff("1", ts(2025, 12, 31, 23, 30), 500),  # 00:30 on 1 Jan in Bratislava (+1 h)
        _eff("2", ts(2025, 12, 31, 22, 59, 59), 480),  # 23:59:59 on 31 Dec: still 2025
        _eff("3", ts(2026, 6, 30, 22, 30), 450),  # summer +2 h: 00:30 on 1 Jul, still 2026
        _eff("4", ts(2026, 12, 31, 22, 30), 440),  # 23:30 on 31 Dec: 2026
    ]
    acts = [_act(str(i), i, "R") for i in range(1, 5)]
    out = _write(tmp_path, acts, [SegmentResult(SEG, 2000.0, effs)])
    seg = _load(out / "segments" / "river-path-north.json")
    assert seg["per_year"] == [
        {"year": 2025, "count": 1, "best_s": 480},
        {"year": 2026, "count": 3, "best_s": 440},
    ]


def test_avg_kmh_matches_oracle_expression(tmp_path: Path) -> None:
    # 900 m in 800 s: d/t*3.6 rounds to 4.0 but the oracle's d/1000/(t/3600) rounds to 4.1
    effs = [Effort(activity_id="1", start_t=100, elapsed_s=800, distance_m=900.0)]
    out = _write(tmp_path, [_act("1", 1, "A")], [SegmentResult(SEG, 900.0, effs)])
    seg = _load(out / "segments" / "river-path-north.json")
    assert seg["efforts"][0]["avg_kmh"] == 4.1


def test_ride_without_efforts_and_no_activities(tmp_path: Path) -> None:
    out = _write(tmp_path, [_act("9", 1, "Lonely")], [SegmentResult(EMPTY, 1000.0, [])])
    ride = _load(out / "rides" / "9.json")
    assert ride["efforts"] == [] and ride["km"] == 12.3 and ride["gear"] == ""
    assert _load(out / "index.json")["rides"][0]["n_efforts"] == 0
    empty = tmp_path / "e"
    write_site_data(empty, [], [])
    assert _load(empty / "index.json") == {"generated": None, "segments": [], "rides": []}


def test_schema_keys_exactly(tmp_path: Path) -> None:
    out = tmp_path / "o"
    _build(out)
    index = _load(out / "index.json")
    assert list(index) == ["generated", "segments", "rides"]
    assert set(index["segments"][0]) == {"slug", "name", "efforts", "pr_s", "pr_date"}
    assert set(index["rides"][0]) == {"id", "date", "name", "km", "n_efforts"}
    seg = _load(out / "segments" / "river-path-north.json")
    assert set(seg) == {"name", "ref_length_m", "efforts", "per_year"}
    assert set(seg["efforts"][0]) == {
        "segment_slug", "activity_id", "ride_name", "start_t", "elapsed_s", "distance_m",
        "avg_kmh", "rank", "gap_to_pr_s", "is_pr_at_time",
    }  # fmt: skip
    assert set(seg["per_year"][0]) == {"year", "count", "best_s"}
