"""REQ-003: Segment definitions (data_dir/segments.yaml, see docs/ARCHITECTURE.md)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import _scenarios as sc
import pytest
import yaml
from _synth import haversine_m, segments_yaml, write_raw
from conftest import SdashRunner, load_json, run_pipeline

pytestmark = pytest.mark.req("REQ-003")


def _load_segments(data_dir: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load((data_dir / "segments.yaml").read_text())
    assert isinstance(data, list), "segments.yaml must stay a YAML list"
    return data


def test_req003_slug_derived_from_name_and_stable(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path
) -> None:
    write_raw(data_dir, [sc.reference_ride()])
    (data_dir / "segments.yaml").write_text(segments_yaml([sc.segment(name="River path north")]))
    out = run_pipeline(sdash, tmp_path / "out1")
    slugs = {s["name"]: s["slug"] for s in load_json(out / "index.json")["segments"]}
    assert slugs["River path north"] == "river-path-north"
    assert (out / "segments" / "river-path-north.json").is_file()

    # Adding another segment before it must not change its slug.
    other = sc.segment(name="Ünïcode & Co: sprint!")
    (data_dir / "segments.yaml").write_text(
        segments_yaml([other, sc.segment(name="River path north")])
    )
    out2 = run_pipeline(sdash, tmp_path / "out2")
    slugs2 = {s["name"]: s["slug"] for s in load_json(out2 / "index.json")["segments"]}
    assert slugs2["River path north"] == "river-path-north"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slugs2["Ünïcode & Co: sprint!"]), slugs2


def _broken(kind: str) -> list[dict[str, Any]]:
    good = sc.segment(name="Good segment")
    bad = sc.segment(name="Broken segment")
    if kind == "missing-field":
        del bad["end"]
    elif kind == "latitude-out-of-range":
        bad["start"] = [95.0, bad["start"][1]]
    elif kind == "longitude-out-of-range":
        bad["end"] = [bad["end"][0], 200.0]
    elif kind == "duplicate-name":
        return [good, sc.segment(name="Broken segment"), sc.segment(name="Broken segment")]
    return [good, bad]


PROBLEM_WORDS = {
    "missing-field": r"\bend\b|missing",
    "latitude-out-of-range": r"range|invalid|lat",
    "longitude-out-of-range": r"range|invalid|lon",
    "duplicate-name": r"duplicate",
}


# One xfail mark per case, so each task un-marks exactly the cases it implements.
KINDS = [
    pytest.param(
        kind,
        marks=pytest.mark.xfail(strict=True, reason="REQ-003 validation not implemented (T-006)"),
    )
    if kind != "missing-field"
    else kind
    for kind in PROBLEM_WORDS
]


@pytest.mark.parametrize("kind", KINDS)
def test_req003_invalid_segment_fails_naming_segment_and_problem(
    sdash: SdashRunner, data_dir: Path, kind: str
) -> None:
    write_raw(data_dir, [sc.reference_ride()])
    (data_dir / "segments.yaml").write_text(segments_yaml(_broken(kind)))
    sdash("parse")  # may or may not validate segments; matching must
    result = sdash("match")
    assert result.returncode != 0, f"invalid segments.yaml ({kind}) accepted"
    assert "not implemented" not in result.output
    assert "Broken segment" in result.output, f"error must name the segment:\n{result.output}"
    assert re.search(PROBLEM_WORDS[kind], result.output, re.IGNORECASE), result.output


@pytest.mark.xfail(strict=True, reason="REQ-003 `segment add` not implemented (T-006)")
def test_req003_segment_add_from_ride_and_km(sdash: SdashRunner, data_dir: Path) -> None:
    ride = sc.ride("1000000061", [(0, 0), (0, 5000)], spacing_m=10.0)
    write_raw(data_dir, [sc.reference_ride(), ride])
    (data_dir / "segments.yaml").write_text(segments_yaml([sc.segment(name="Existing segment")]))
    sdash("parse").ok()
    sdash(
        "segment", "add", "--name", "Added climb", "--activity", "1000000061",
        "--from-km", "1.0", "--to-km", "3.5",
    ).ok()  # fmt: skip
    segs = _load_segments(data_dir)
    assert [s["name"] for s in segs] == ["Existing segment", "Added climb"], "must append"
    added = segs[1]
    assert str(added["ref_activity"]) == "1000000061"
    start_err = haversine_m(tuple(added["start"]), tuple(sc.latlon((0, 1000))))
    end_err = haversine_m(tuple(added["end"]), tuple(sc.latlon((0, 3500))))
    assert start_err < 15 and end_err < 15, (
        f"start off by {start_err:.1f} m, end off by {end_err:.1f} m"
    )


@pytest.mark.xfail(strict=True, reason="REQ-003 `segment import-strava` not implemented (T-006)")
def test_req003_import_strava_segments_skips_existing(sdash: SdashRunner, data_dir: Path) -> None:
    hill_s, hill_e = sc.latlon((0, 100)), sc.latlon((0, 900))
    flat_s, flat_e = sc.latlon((300, 0)), sc.latlon((300, 1500))
    write_raw(
        data_dir,
        [sc.reference_ride()],
        segments_rows=[
            ("Existing segment", "1000000077", -47.0, -134.0, -47.01, -134.01),
            ("Strava hill", "1000000071", *hill_s, *hill_e),
            ("Strava flat", "1000000072", *flat_s, *flat_e),
        ],
    )
    existing = sc.segment(name="Existing segment")
    (data_dir / "segments.yaml").write_text(segments_yaml([existing]))
    sdash("segment", "import-strava").ok()
    segs = _load_segments(data_dir)
    assert [s["name"] for s in segs] == ["Existing segment", "Strava hill", "Strava flat"]
    assert segs[0]["start"] == pytest.approx(existing["start"]), "existing segment must not change"
    by_name = {s["name"]: s for s in segs}
    assert str(by_name["Strava hill"]["ref_activity"]) == "1000000071"
    assert by_name["Strava hill"]["start"] == pytest.approx(hill_s, abs=1e-6)
    assert by_name["Strava flat"]["end"] == pytest.approx(flat_e, abs=1e-6)
