"""REQ-005: Site data. Schema from docs/ARCHITECTURE.md ("Site JSON"); keys are checked as a
minimum set (extra keys are allowed, coordinates are not)."""

from __future__ import annotations

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
