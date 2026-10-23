"""GPX parsing and the track cache (REQ-002)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdash.tracks import Track, haversine_m, parse_track, read_cache, write_cache

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "minimal.gpx"


def test_haversine_one_degree_of_latitude() -> None:
    assert haversine_m(-47.0, -134.0, -46.0, -134.0) == pytest.approx(111_195, rel=1e-3)
    assert haversine_m(-47.0, -134.0, -47.0, -134.0) == 0.0


def test_parse_gpx_fixture() -> None:
    track = parse_track(FIXTURE)
    n = len(track.t)
    assert n > 2
    assert len(track.lat) == len(track.lon) == len(track.d) == n
    assert track.t == sorted(track.t)
    assert track.t[0] == 1777622400  # 2026-05-01T08:00:00Z
    assert track.d[0] == 0.0
    assert all(b >= a for a, b in zip(track.d, track.d[1:], strict=False))
    assert track.d[-1] > 0


def test_parse_gpx_drops_points_without_time(tmp_path: Path) -> None:
    gpx = tmp_path / "a.gpx"
    gpx.write_text(
        '<gpx version="1.1" creator="x" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        '<trkpt lat="-47.0" lon="-134.0"><time>2026-05-01T08:00:00Z</time></trkpt>'
        '<trkpt lat="-47.0001" lon="-134.0"></trkpt>'
        '<trkpt lat="-47.0002" lon="-134.0"><time>2026-05-01T08:00:10Z</time></trkpt>'
        "</trkseg></trk></gpx>",
        encoding="utf-8",
    )
    track = parse_track(gpx)
    assert len(track.t) == 2
    assert track.d[1] == pytest.approx(haversine_m(-47.0, -134.0, -47.0002, -134.0))


def test_unsupported_extension_raises(tmp_path: Path) -> None:
    p = tmp_path / "a.xyz"
    p.write_bytes(b"")
    with pytest.raises(ValueError, match="unsupported"):
        parse_track(p)


def test_broken_gpx_raises_value_error(tmp_path: Path) -> None:
    p = tmp_path / "a.gpx"
    p.write_text("not xml", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_track(p)


def test_cache_roundtrip(tmp_path: Path) -> None:
    track = Track(t=[1, 2], lat=[-47.0, -47.1], lon=[-134.0, -134.0], d=[0.0, 11.5])
    path = tmp_path / "cache" / "7.json.gz"
    write_cache(path, track)
    assert read_cache(path) == track
