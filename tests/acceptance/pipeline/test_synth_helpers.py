"""Harness self-checks: the synthetic builders produce valid files and the REQ-004 scenarios really
satisfy (or violate) the rule each test claims. These pass today; they guard the test inputs, not
the product, so a failing acceptance test always means the product is wrong."""

from __future__ import annotations

import gzip
import io
import itertools
import math
import zipfile
from collections import Counter
from pathlib import Path

import _scenarios as sc
import fitdecode
import gpxpy
from _synth import (
    ACTIVITIES_HEADER,
    DUPLICATED_COLUMNS,
    SYNTH_BOX,
    Point,
    encode_track,
    export_files,
    haversine_m,
    strava_date,
    write_zip,
)


def _ll(p: Point) -> tuple[float, float]:
    assert p.lat is not None and p.lon is not None
    return p.lat, p.lon


def test_fit_encoder_roundtrips_with_fitdecode() -> None:
    pts = sc.reference_ride().points
    assert pts
    pts = [*pts[:3], Point(pts[3].t, None, None, pts[3].d), *pts[4:10]]
    data = encode_track(pts, "fit.gz")
    records = []
    with fitdecode.FitReader(io.BytesIO(gzip.decompress(data))) as fit:
        for frame in fit:
            if isinstance(frame, fitdecode.FitDataMessage) and frame.name == "record":
                records.append(frame)
    assert len(records) == 10
    assert records[3].get_value("position_lat") is None
    lat = records[0].get_value("position_lat") * 180 / 2**31
    assert abs(lat - pts[0].lat) < 1e-6  # type: ignore[operator]


def test_gpx_and_tcx_are_parseable() -> None:
    pts = sc.reference_ride().points
    assert pts
    gpx = gpxpy.parse(encode_track(pts, "gpx").decode())
    assert sum(len(s.points) for t in gpx.tracks for s in t.segments) == len(pts)
    assert b"<Trackpoint>" in gzip.decompress(encode_track(pts, "tcx.gz"))


def test_activities_header_has_documented_duplicates() -> None:
    counts = Counter(ACTIVITIES_HEADER)
    assert {c for c, n in counts.items() if n > 1} == set(DUPLICATED_COLUMNS)
    assert strava_date(sc.DAY0.replace(hour=15, minute=4, second=5)) == "May 1, 2026, 3:04:05 PM"


def test_export_zip_contains_personal_files(tmp_path: Path) -> None:
    z = write_zip(tmp_path / "e.zip", export_files([sc.reference_ride()]))
    names = zipfile.ZipFile(z).namelist()
    assert "activities.csv" in names and "messages.json" in names and "media/0001.jpg" in names


def _min_dist_to_path(p: tuple[float, float], path: list[tuple[float, float]]) -> float:
    return min(haversine_m(p, q) for q in path)


def test_scenarios_satisfy_their_givens() -> None:
    ref = [_ll(p) for p in sc.reference_ride().points or []]
    start, end = ref[0], ref[-1]
    ref_len = sum(haversine_m(a, b) for a, b in itertools.pairwise(ref))
    assert abs(ref_len - sc.SEG_LEN) < 5

    def ridden(r: list[tuple[float, float]]) -> tuple[float, float, float, float]:
        i = min(range(len(r)), key=lambda k: haversine_m(r[k], start))
        j = min(range(i, len(r)), key=lambda k: haversine_m(r[k], end))
        length = sum(haversine_m(a, b) for a, b in zip(r[i:j], r[i + 1 : j + 1], strict=False))
        worst = max(_min_dist_to_path(p, r[i : j + 1]) for p in ref[::10])
        return haversine_m(r[i], start), haversine_m(r[j], end), length, worst

    for make in (sc.normal_with_stop, sc.sparse):
        g_start, g_end, length, worst = ridden([_ll(p) for p in make().points or []])
        assert g_start <= 30 and g_end <= 30 and abs(length / ref_len - 1) <= 0.10 and worst <= 60

    g_start, g_end, length, worst = ridden([_ll(p) for p in sc.detour().points or []])
    assert g_start <= 30 and g_end <= 30, "detour must pass both gates"
    assert abs(length / ref_len - 1) <= 0.10, "detour must pass the length rule"
    assert worst > 60, "detour must fail only the path rule"

    g_start, g_end, length, worst = ridden([_ll(p) for p in sc.loop_detour().points or []])
    assert g_start <= 30 and g_end <= 30 and worst <= 60, "loop detour must pass gates and path"
    assert length / ref_len - 1 > 0.10, "loop detour must fail only the length rule"

    sparse = [_ll(p) for p in sc.sparse().points or []]
    gaps = [haversine_m(a, b) for a, b in itertools.pairwise(sparse)]
    assert min(gaps) >= 45 and max(gaps) <= 55

    stop = sc.normal_with_stop().points or []
    t_a = next(p.t for p in stop if p.d >= 500)
    t_b = next(p.t for p in stop if p.d >= 2500)
    assert t_b - t_a == sc.EXPECTED_NORMAL_ELAPSED


def test_all_synthetic_points_are_in_the_synthetic_box() -> None:
    for make in (sc.reference_ride, sc.two_laps, sc.detour, sc.out_and_back_ride):
        for p in make().points or []:
            lat, lon = _ll(p)
            assert SYNTH_BOX["lat"][0] < lat < SYNTH_BOX["lat"][1]
            assert SYNTH_BOX["lon"][0] < lon < SYNTH_BOX["lon"][1]
    assert math.isclose(sc.latlon(sc.A)[0], -47.25)
