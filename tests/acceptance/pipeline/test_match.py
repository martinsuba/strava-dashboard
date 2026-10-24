"""REQ-004: Segment matching. Inputs are synthetic GPX rides (see _scenarios.py); each test runs
`sdash parse`, `sdash match`, `sdash build-data --out` and reads efforts from
segments/<slug>.json (Effort fields from docs/ARCHITECTURE.md: activity_id, elapsed_s, ...)."""

from __future__ import annotations

from pathlib import Path

import _scenarios as sc
import pytest
from _synth import Ride, segments_yaml, write_raw
from conftest import SdashRunner, efforts_by_activity, run_pipeline

pytestmark = pytest.mark.req("REQ-004")
TEST_RIDE = "1000000002"


def _match(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path, rides: list[Ride], seg: dict
) -> dict:
    write_raw(data_dir, rides)
    (data_dir / "segments.yaml").write_text(segments_yaml([seg]))
    out = run_pipeline(sdash, tmp_path / "site-data")
    return efforts_by_activity(out, seg["name"])


def test_req004_effort_found_elapsed_includes_stops(sdash, data_dir, tmp_path) -> None:
    efforts = _match(
        sdash, data_dir, tmp_path, [sc.reference_ride(), sc.normal_with_stop()], sc.segment()
    )
    assert len(efforts.get(TEST_RIDE, [])) == 1, efforts
    elapsed = efforts[TEST_RIDE][0]["elapsed_s"]
    assert abs(elapsed - sc.EXPECTED_NORMAL_ELAPSED) <= 5, (
        f"elapsed {elapsed} (60 s stop included?)"
    )


def test_req004_different_road_no_effort(sdash, data_dir, tmp_path) -> None:
    efforts = _match(sdash, data_dir, tmp_path, [sc.reference_ride(), sc.detour()], sc.segment())
    assert efforts.get(sc.REF_ID), "the reference ride itself should match (sanity)"
    assert efforts.get(TEST_RIDE, []) == []


def test_req004_ridden_distance_off_by_more_than_10_percent_no_effort(
    sdash, data_dir, tmp_path
) -> None:
    efforts = _match(
        sdash, data_dir, tmp_path, [sc.reference_ride(), sc.loop_detour()], sc.segment()
    )
    assert efforts.get(sc.REF_ID), "the reference ride itself should match (sanity)"
    assert efforts.get(TEST_RIDE, []) == []


def test_req004_opposite_direction_no_effort(sdash, data_dir, tmp_path) -> None:
    efforts = _match(sdash, data_dir, tmp_path, [sc.reference_ride(), sc.reverse()], sc.segment())
    assert efforts.get(sc.REF_ID), "the reference ride itself should match (sanity)"
    assert efforts.get(TEST_RIDE, []) == []


def test_req004_two_laps_two_efforts(sdash, data_dir, tmp_path) -> None:
    efforts = _match(sdash, data_dir, tmp_path, [sc.reference_ride(), sc.two_laps()], sc.segment())
    laps = efforts.get(TEST_RIDE, [])
    assert len(laps) == 2, laps
    for e in laps:
        assert abs(e["elapsed_s"] - 400) <= 5
    assert laps[0]["start_t"] != laps[1]["start_t"]


def test_req004_sparse_track_effort_found(sdash, data_dir, tmp_path) -> None:
    efforts = _match(sdash, data_dir, tmp_path, [sc.reference_ride(), sc.sparse()], sc.segment())
    assert len(efforts.get(TEST_RIDE, [])) == 1, efforts
    assert abs(efforts[TEST_RIDE][0]["elapsed_s"] - 400) <= 15


def test_req004_out_and_back_not_zero_length(sdash, data_dir, tmp_path) -> None:
    seg = sc.segment(start=sc.A, end=sc.A)
    rides = [sc.out_and_back_reference(), sc.out_and_back_ride()]
    efforts = _match(sdash, data_dir, tmp_path, rides, seg)
    found = efforts.get(TEST_RIDE, [])
    assert len(found) == 1, found
    assert abs(found[0]["elapsed_s"] - 400) <= 10, "out-and-back matched as a zero-length effort"
    assert found[0]["distance_m"] > 1500


def test_req004_non_ride_reference_activity_used(sdash, data_dir, tmp_path) -> None:
    ride = sc.ride(TEST_RIDE, [(0, -500), (0, 2500)], day=1)
    efforts = _match(sdash, data_dir, tmp_path, [sc.hike_reference(), ride], sc.segment())
    assert len(efforts.get(TEST_RIDE, [])) == 1, efforts
    assert abs(efforts[TEST_RIDE][0]["elapsed_s"] - 400) <= 5
    assert sc.REF_ID not in efforts, "the hike itself is not a ride and must not get an effort"


def test_req004_start_passed_45m_away_no_effort(sdash, data_dir, tmp_path) -> None:
    rides = [sc.reference_ride(), sc.start_gate_offset(45)]
    efforts = _match(sdash, data_dir, tmp_path, rides, sc.segment())
    assert efforts.get(sc.REF_ID), "the reference ride itself should match (sanity)"
    assert efforts.get(TEST_RIDE, []) == [], "start gate is 30 m; this ride passed ~44 m away"


def test_req004_start_passed_20m_away_effort_found(sdash, data_dir, tmp_path) -> None:
    """Positive control for the 45 m case: same road shape, inside the 30 m gate."""
    rides = [sc.reference_ride(), sc.start_gate_offset(20)]
    efforts = _match(sdash, data_dir, tmp_path, rides, sc.segment())
    found = efforts.get(TEST_RIDE, [])
    assert len(found) == 1, found
    assert 370 <= found[0]["elapsed_s"] <= 420


def test_req004_path_80m_off_reference_no_effort(sdash, data_dir, tmp_path) -> None:
    rides = [sc.reference_ride(), sc.near_detour()]
    efforts = _match(sdash, data_dir, tmp_path, rides, sc.segment())
    assert efforts.get(sc.REF_ID), "the reference ride itself should match (sanity)"
    assert efforts.get(TEST_RIDE, []) == [], "a reference point ~80 m from the ride (limit 60 m)"
