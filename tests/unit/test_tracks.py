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


# --- T-003: FIT / TCX / .gz, bounded decompression, cache stamp -------------------------------

import gzip  # noqa: E402
import importlib.util  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
import warnings  # noqa: E402

from sdash import tracks  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]


def _synth():  # type: ignore[no-untyped-def]
    path = _ROOT / "tests" / "acceptance" / "pipeline" / "_synth.py"
    spec = importlib.util.spec_from_file_location("_synth_for_tracks_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _points(synth, missing: tuple[int, ...] = ()):  # type: ignore[no-untyped-def]
    pts = [
        synth.Point(1_780_000_000 + 10 * i, -47.25 + 0.0001 * i, -134.75 + 0.0002 * i, 0.0)
        for i in range(30)
    ]
    for i in missing:
        pts[i] = synth.Point(pts[i].t, None, None, 0.0)
    return pts


@pytest.mark.parametrize("fmt", ["gpx", "gpx.gz", "fit", "fit.gz", "tcx", "tcx.gz"])
def test_each_format_skips_positionless_records(tmp_path: Path, fmt: str) -> None:
    synth = _synth()
    pts = _points(synth, missing=(3, 4, 20) if not fmt.startswith("gpx") else ())
    path = tmp_path / f"r.{fmt}"
    path.write_bytes(synth.encode_track(pts, fmt))
    track = parse_track(path)
    want = [p for p in pts if p.lat is not None]
    assert track.t == [p.t for p in want]
    for lat, lon, p in zip(track.lat, track.lon, want, strict=True):
        assert lat == pytest.approx(p.lat, abs=1e-6)
        assert lon == pytest.approx(p.lon, abs=1e-6)
    assert track.d[0] == 0.0
    assert all(b > a for a, b in zip(track.d, track.d[1:], strict=False))


def test_fit_semicircles_converted_to_degrees(tmp_path: Path) -> None:
    synth = _synth()
    path = tmp_path / "r.fit"
    path.write_bytes(synth.fit_bytes([synth.Point(1_780_000_000, 48.1486, 17.1077, 0.0)]))
    track = parse_track(path)
    assert track.lat == [pytest.approx(48.1486, abs=1e-6)]
    assert track.lon == [pytest.approx(17.1077, abs=1e-6)]


def test_fit_parse_emits_no_warnings(tmp_path: Path) -> None:
    synth = _synth()
    path = tmp_path / "r.fit"
    path.write_bytes(synth.fit_bytes(_points(synth)))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        parse_track(path)


@pytest.mark.parametrize("name", ["r.fit", "r.fit.gz", "r.gpx.gz", "r.tcx.gz", "r.tcx"])
def test_corrupt_files_raise_value_error(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    path.write_bytes(b"\x0e\x10garbage, not a ride file" * 10)
    with pytest.raises(ValueError):
        parse_track(path)


def test_truncated_gzip_raises_value_error(tmp_path: Path) -> None:
    synth = _synth()
    data = synth.encode_track(_points(synth), "fit.gz")
    path = tmp_path / "r.fit.gz"
    path.write_bytes(data[: len(data) // 2])
    with pytest.raises(ValueError):
        parse_track(path)


def test_gzip_bomb_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracks, "MAX_DECOMPRESSED_BYTES", 10_000)
    path = tmp_path / "bomb.gpx.gz"
    path.write_bytes(gzip.compress(b"<gpx>" + b" " * 1_000_000, mtime=0))
    with pytest.raises(ValueError, match="exceeds"):
        parse_track(path)


def test_gzip_just_under_cap_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    synth = _synth()
    raw = synth.gpx_bytes(_points(synth))
    monkeypatch.setattr(tracks, "MAX_DECOMPRESSED_BYTES", len(raw))
    path = tmp_path / "ok.gpx.gz"
    path.write_bytes(gzip.compress(raw, mtime=0))
    assert len(parse_track(path).t) == 30


def test_tcx_with_entity_declaration_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "x.tcx"
    path.write_bytes(b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY b "c">]><a>&b;</a>')
    with pytest.raises(ValueError, match="DTD"):
        parse_track(path)


def test_cache_is_fresh_only_for_the_same_stamp(tmp_path: Path) -> None:
    track = Track(t=[1], lat=[-47.0], lon=[-134.0], d=[0.0])
    path = tmp_path / "c" / "1.json.gz"
    write_cache(path, track, (100, 5))
    assert tracks.read_cache_if_fresh(path, (100, 5)) == track
    assert tracks.read_cache_if_fresh(path, (101, 5)) is None
    assert tracks.read_cache_if_fresh(path, (100, 6)) is None


def test_cache_without_stamp_or_missing_or_corrupt_is_stale(tmp_path: Path) -> None:
    track = Track(t=[1], lat=[-47.0], lon=[-134.0], d=[0.0])
    path = tmp_path / "1.json.gz"
    assert tracks.read_cache_if_fresh(path, (1, 1)) is None
    write_cache(path, track)
    assert tracks.read_cache_if_fresh(path, (1, 1)) is None
    path.write_bytes(b"not gzip")
    assert tracks.read_cache_if_fresh(path, (1, 1)) is None


def test_source_stamp_follows_size_and_mtime(tmp_path: Path) -> None:
    p = tmp_path / "f"
    p.write_bytes(b"abc")
    os.utime(p, ns=(1, 2_000_000_000))
    assert tracks.source_stamp(p) == (3, 2_000_000_000)
