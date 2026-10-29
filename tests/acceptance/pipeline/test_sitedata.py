"""REQ-005: Site data. Schema from docs/ARCHITECTURE.md ("Site JSON"); keys are checked as a
minimum set (extra keys are allowed, coordinates are not)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import _scenarios as sc
import pytest
from _synth import segments_yaml, write_raw
from conftest import SdashRunner, coordinate_leaks, load_json, run_pipeline

pytestmark = pytest.mark.req("REQ-005")

INDEX_SEGMENT_KEYS = {"slug", "name", "efforts", "pr_s", "pr_date"}
INDEX_RIDE_KEYS = {"id", "date", "name", "km", "n_efforts"}
SEGMENT_KEYS = {"name", "ref_length_m", "efforts", "per_year"}
PER_YEAR_KEYS = {"year", "count", "best_s"}
RIDE_KEYS = {"id", "date", "name", "km", "elapsed_s", "moving_s", "gear", "efforts"}
RIDE_EFFORT_KEYS = {
    "slug",
    "name",
    "elapsed_s",
    "pr_s",
    "avg_s",
    "gap_to_pr_s",
    "rank",
    "of",
    "is_pr",
    "is_pr_at_time",
}
NO_MATCH = "1000000003"


def _setup(data_dir: Path) -> None:
    elsewhere = sc.ride(NO_MATCH, [(800, -500), (800, 2500)], day=2, name="Synthetic east road")
    write_raw(data_dir, [sc.reference_ride(), sc.normal_with_stop(), elsewhere])
    (data_dir / "segments.yaml").write_text(segments_yaml([sc.segment()]))


def test_req005_site_data_has_lists_and_effort_data(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path
) -> None:
    _setup(data_dir)
    out = run_pipeline(sdash, tmp_path / "site-data")

    index = load_json(out / "index.json")
    assert {"generated", "segments", "rides"} <= index.keys()
    assert len(index["segments"]) == 1
    seg_entry = index["segments"][0]
    assert seg_entry.keys() >= INDEX_SEGMENT_KEYS, seg_entry
    assert seg_entry["name"] == sc.SEGMENT_NAME and seg_entry["efforts"] == 2
    assert abs(seg_entry["pr_s"] - 400) <= 5
    rides = {str(r["id"]): r for r in index["rides"]}
    assert set(rides) == {sc.REF_ID, "1000000002", NO_MATCH}
    for r in rides.values():
        assert r.keys() >= INDEX_RIDE_KEYS, r
    assert rides["1000000002"]["n_efforts"] == 1 and rides[NO_MATCH]["n_efforts"] == 0

    seg = load_json(out / "segments" / f"{seg_entry['slug']}.json")
    assert seg.keys() >= SEGMENT_KEYS, seg.keys()
    assert abs(seg["ref_length_m"] - sc.SEG_LEN) < 50
    assert len(seg["efforts"]) == 2
    assert seg["per_year"] and all(y.keys() >= PER_YEAR_KEYS for y in seg["per_year"])
    assert {(y["year"], y["count"]) for y in seg["per_year"]} == {(2026, 2)}

    for rid in rides:
        ride = load_json(out / "rides" / f"{rid}.json")
        assert ride.keys() >= RIDE_KEYS, ride.keys()
    ride = load_json(out / "rides" / "1000000002.json")
    assert len(ride["efforts"]) == 1 and ride["efforts"][0].keys() >= RIDE_EFFORT_KEYS
    effort = ride["efforts"][0]
    assert (effort["rank"], effort["of"], effort["is_pr"]) == (2, 2, False)
    assert abs(effort["gap_to_pr_s"] - 60) <= 5
    assert load_json(out / "rides" / f"{NO_MATCH}.json")["efforts"] == []


def _expected_median(times: list[int]) -> int:
    """The ARCHITECTURE "Site JSON" rule: middle value, or mean of the two middle ones rounded
    half-even (2 * mean is an exact integer, so no float rounding is involved)."""
    t = sorted(times)
    mid = len(t) // 2
    if len(t) % 2:
        return t[mid]
    twice = t[mid - 1] + t[mid]
    return twice // 2 if twice % 2 == 0 else (twice // 2 + (twice // 2) % 2)


@pytest.mark.parametrize(
    ("stops", "half"),
    [
        ([], False),  # 2 efforts (400 s, 460 s), even count
        ([(1500.0, 30)], False),  # 3 efforts, odd count
        ([(1500.0, 30), (1700.0, 31)], True),  # 4 efforts, middle values sum to an odd number
    ],
    ids=["even", "odd", "half"],
)
def test_req005_segment_file_has_median_s_by_the_ride_rule(
    sdash: SdashRunner,
    data_dir: Path,
    tmp_path: Path,
    stops: list[tuple[float, int]],
    half: bool,
) -> None:
    extra = []
    if stops:
        extra.append(sc.ride("1000000010", [(0, -500), (0, 2500)], day=2, stops=[stops[0]]))
    if len(stops) > 1:
        extra.append(sc.ride("1000000011", [(0, -500), (0, 2500)], day=3, stops=[stops[1]]))
    write_raw(data_dir, [sc.reference_ride(), sc.normal_with_stop(), *extra])
    (data_dir / "segments.yaml").write_text(segments_yaml([sc.segment()]))
    out = run_pipeline(sdash, tmp_path / "site-data")
    index = load_json(out / "index.json")
    seg = load_json(out / "segments" / f"{index['segments'][0]['slug']}.json")
    times = [e["elapsed_s"] for e in seg["efforts"]]
    assert len(times) == 2 + len(extra)
    middle = sorted(times)[len(times) // 2 - 1 : len(times) // 2 + 1]
    if half:
        assert sum(middle) % 2 == 1, f"scenario no longer produces a .5 median: {times}"
    assert isinstance(seg["median_s"], int)
    assert seg["median_s"] == _expected_median(times)
    # the ride pages carry the very same number
    for e in seg["efforts"]:
        ride = load_json(out / "rides" / f"{e['activity_id']}.json")
        assert [x["median_s"] for x in ride["efforts"]] == [seg["median_s"]]


def test_req005_site_data_has_no_coordinates_or_raw_tracks(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path
) -> None:
    _setup(data_dir)
    out = run_pipeline(sdash, tmp_path / "site-data")
    files = [p for p in out.rglob("*") if p.is_file()]
    assert files, "build-data wrote nothing"
    leaks: list[str] = []
    for p in files:
        rel = p.relative_to(out)
        assert p.suffix == ".json", f"only derived JSON may be written, found {rel}"
        leaks += [f"{rel}: {leak}" for leak in coordinate_leaks(json.loads(p.read_text()))]
    assert not leaks, "\n".join(leaks)


def test_req005_build_twice_is_byte_identical(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path
) -> None:
    _setup(data_dir)
    first = run_pipeline(sdash, tmp_path / "first")
    time.sleep(1.1)  # a wall-clock timestamp in the output would differ now
    second = run_pipeline(sdash, tmp_path / "second")

    def snapshot(root: Path) -> dict[str, bytes]:
        return {
            str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
        }

    a, b = snapshot(first), snapshot(second)
    assert a, "build-data wrote nothing"
    assert a.keys() == b.keys()
    diff = [name for name in a if a[name] != b[name]]
    assert not diff, f"files differ between identical builds: {diff}"


def test_req009_build_data_writes_matching_build_info(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path
) -> None:
    """D-008: build-info.json = {source, data_sha256 over all other files, sorted, path NUL bytes NUL}."""
    _setup(data_dir)
    out = run_pipeline(sdash, tmp_path / "site-data")
    info = load_json(out / "build-info.json")
    assert info["source"] == "sdash build-data"
    digest = hashlib.sha256()
    others = [p for p in out.rglob("*") if p.is_file() and p != out / "build-info.json"]
    assert others, "build-data wrote no other files"
    for p in sorted(others, key=lambda f: f.relative_to(out).as_posix()):
        digest.update(p.relative_to(out).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    assert info["data_sha256"] == digest.hexdigest()
