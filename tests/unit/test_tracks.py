"""GPX parsing and the track cache (REQ-002)."""

from __future__ import annotations

import contextlib
import gzip
import importlib.util
import os
import random
import struct
import sys
import warnings
from pathlib import Path

import pytest

from sdash import tracks
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


# --- T-003 review round 1 -------------------------------------------------------------------


def _fit_with_crc(data: bytearray) -> bytes:
    synth = _synth()
    data[-2:] = struct.pack("<H", synth.fit_crc(bytes(data[:-2])))
    return bytes(data)


def _parse_or_value_error(path: Path) -> None:
    with contextlib.suppress(ValueError):
        parse_track(path)


def test_mutated_fit_files_never_raise_anything_but_value_error(tmp_path: Path) -> None:
    synth = _synth()
    good = synth.fit_bytes(_points(synth)[:6])
    rng = random.Random(20260101)
    path = tmp_path / "m.fit"
    for _ in range(400):
        data = bytearray(good)
        for _ in range(rng.randint(1, 4)):
            data[rng.randrange(14, len(data) - 2)] = rng.randrange(256)
        path.write_bytes(_fit_with_crc(data))
        _parse_or_value_error(path)


@pytest.mark.parametrize("base_type", [0x00, 0x02, 0x83, 0x84, 0x88, 0x8C])
def test_fit_with_odd_timestamp_base_type_is_value_error_or_track(
    tmp_path: Path, base_type: int
) -> None:
    synth = _synth()
    data = bytearray(synth.fit_bytes(_points(synth)[:3]))
    # record definition: timestamp field (253, size 4, base type 0x86 uint32) -> another base type;
    # fitdecode then yields a non-datetime (float/int) or raises TypeError
    data[bytes(data).index(bytes([253, 4, 0x86])) + 2] = base_type
    path = tmp_path / "i.fit"
    path.write_bytes(_fit_with_crc(data))
    _parse_or_value_error(path)


def test_fit_with_non_numeric_position_is_skipped_or_value_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Frame(tracks.fitdecode.FitDataMessage):  # type: ignore[misc]
        name = "record"

        def __init__(self) -> None:  # no real message: only get_value is used
            pass

        def get_value(self, name, idx=0, **kw):  # type: ignore[no-untyped-def]
            from datetime import UTC, datetime

            return {
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
                "position_lat": "x",
                "position_long": (1, 2),
            }[name]

    class Reader:
        def __init__(self, *_a: object, **_k: object) -> None: ...
        def __enter__(self) -> Reader:
            return self

        def __exit__(self, *_a: object) -> None: ...
        def __iter__(self):  # type: ignore[no-untyped-def]
            return iter([Frame()])

    monkeypatch.setattr(tracks.fitdecode, "FitReader", Reader)
    path = tmp_path / "n.fit"
    path.write_bytes(b"x")
    assert parse_track(path).t == []


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "91", "-91.5"])
def test_gpx_rejects_invalid_latitude_points(tmp_path: Path, bad: str) -> None:
    p = tmp_path / "a.gpx"
    p.write_text(
        '<gpx version="1.1" creator="x" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        '<trkpt lat="-47.0" lon="-134.0"><time>2026-05-01T08:00:00Z</time></trkpt>'
        f'<trkpt lat="{bad}" lon="-134.0"><time>2026-05-01T08:00:05Z</time></trkpt>'
        '<trkpt lat="-47.001" lon="-134.0"><time>2026-05-01T08:00:10Z</time></trkpt>'
        "</trkseg></trk></gpx>",
        encoding="utf-8",
    )
    assert len(parse_track(p).t) == 2


@pytest.mark.parametrize(
    ("lat", "lon"), [("nan", "-134"), ("500", "-134"), ("-47", "inf"), ("-47", "181")]
)
def test_tcx_rejects_invalid_coordinates(tmp_path: Path, lat: str, lon: str) -> None:
    p = tmp_path / "a.tcx"
    p.write_text(
        '<TrainingCenterDatabase xmlns="x"><Trackpoint><Time>2026-05-01T08:00:00Z</Time>'
        f"<Position><LatitudeDegrees>{lat}</LatitudeDegrees>"
        f"<LongitudeDegrees>{lon}</LongitudeDegrees></Position></Trackpoint>"
        "</TrainingCenterDatabase>",
        encoding="utf-8",
    )
    assert parse_track(p).t == []


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-8"])
@pytest.mark.parametrize(
    "decl", ["<!DOCTYPE a [<!ENTITY b 'c'>]>", "<!doctype a>", "<!entity b 'c'>"]
)
def test_tcx_dtd_refused_in_any_encoding(tmp_path: Path, encoding: str, decl: str) -> None:
    text = f'<?xml version="1.0"?>{decl}<a>&b;</a>'
    path = tmp_path / "x.tcx"
    path.write_bytes(text.encode(encoding))
    with pytest.raises(ValueError, match="DTD"):
        parse_track(path)


def test_gpx_parsing_does_not_use_lxml() -> None:
    # lxml resolves XML entities by default; the stdlib parser (expat) does not resolve external
    # ones and limits entity amplification. Fail loudly if gpxpy would switch to lxml.
    import gpxpy.parser

    assert "lxml" not in str(gpxpy.parser.mod_etree), "gpxpy would parse with lxml"


def test_cache_with_non_object_json_or_bad_types_is_stale_and_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "1.json.gz"
    for payload in (
        b"[]",
        b"null",
        b'"x"',
        b'{"t":1,"lat":[],"lon":[],"d":[]}',
        b'{"t":["a"],"lat":[1],"lon":[1],"d":[1]}',
        b'{"t":[1,2],"lat":[1],"lon":[1],"d":[1]}',
    ):
        path.write_bytes(gzip.compress(payload))
        assert tracks.read_cache_if_fresh(path, (1, 1)) is None
        with pytest.raises(ValueError):
            read_cache(path)


def test_cache_write_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    track = Track(t=[1], lat=[-47.0], lon=[-134.0], d=[0.0])
    path = tmp_path / "1.json.gz"
    write_cache(path, track)
    before = path.read_bytes()

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        write_cache(path, Track(t=[2], lat=[-47.0], lon=[-134.0], d=[0.0]))
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["1.json.gz"]  # temp file cleaned up


# --- T-013: text / whitespace / BOM before the XML declaration -----------------------------------


def _tcx_bytes() -> bytes:
    synth = _synth()
    return synth.tcx_bytes(_points(synth))


@pytest.mark.parametrize(
    "prefix",
    [b" ", b"\n\n", b"\t \r\n", b"\xef\xbb\xbf", b"\xef\xbb\xbf\n", b"Strava export\n", b"x"],
)
def test_tcx_with_text_whitespace_or_bom_before_declaration_parses(
    tmp_path: Path, prefix: bytes
) -> None:
    path = tmp_path / "x.tcx"
    path.write_bytes(prefix + _tcx_bytes())
    assert len(parse_track(path).t) == 30


def test_tcx_with_leading_whitespace_parses_when_gzipped(tmp_path: Path) -> None:
    path = tmp_path / "x.tcx.gz"
    path.write_bytes(gzip.compress(b"\n  " + _tcx_bytes(), mtime=0))
    assert len(parse_track(path).t) == 30


def test_tcx_utf16_with_bom_and_leading_whitespace_parses(tmp_path: Path) -> None:
    text = "\n " + _tcx_bytes().decode().replace("UTF-8", "UTF-16")
    path = tmp_path / "x.tcx"
    path.write_bytes(text.encode("utf-16"))
    assert len(parse_track(path).t) == 30


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-32"])
def test_tcx_dtd_still_refused_after_leading_text(tmp_path: Path, encoding: str) -> None:
    text = 'junk\n <?xml version="1.0"?><!DOCTYPE a [<!ENTITY b "c">]><a>&b;</a>'
    path = tmp_path / "x.tcx"
    path.write_bytes(text.encode(encoding))
    with pytest.raises(ValueError, match="DTD"):
        parse_track(path)


def test_tcx_without_any_xml_is_still_an_error(tmp_path: Path) -> None:
    path = tmp_path / "x.tcx"
    path.write_bytes(b"just some text")
    with pytest.raises(ValueError, match="TCX"):
        parse_track(path)


# --- T-014: hardening -----------------------------------------------------------------------------


def test_fit_failure_reason_names_the_exception_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Reader:
        def __init__(self, *a: object, **k: object) -> None:
            raise KeyError("boom")

    monkeypatch.setattr(tracks.fitdecode, "FitReader", Reader)
    path = tmp_path / "x.fit"
    path.write_bytes(b"x")
    with pytest.raises(ValueError, match=r"cannot read FIT x\.fit: KeyError"):
        parse_track(path)


def test_gpx_trackpoint_without_latitude_is_a_reported_failure(tmp_path: Path) -> None:
    p = tmp_path / "a.gpx"
    p.write_text(
        '<gpx version="1.1" creator="x" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        '<trkpt lon="-134.0"><time>2026-05-01T08:00:00Z</time></trkpt>'
        "</trkseg></trk></gpx>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"cannot read GPX a\.gpx"):
        parse_track(p)


@pytest.mark.parametrize("bad", ["Infinity", "-Infinity", "NaN"])
@pytest.mark.parametrize("key", ["t", "lat", "d"])
def test_cache_with_non_finite_numbers_is_stale_and_unreadable(
    tmp_path: Path, bad: str, key: str
) -> None:
    fields = {"t": "1", "lat": "-47.0", "lon": "-134.0", "d": "0.0"}
    fields[key] = bad
    body = ",".join(f'"{k}":[{v}]' for k, v in fields.items())
    path = tmp_path / "1.json.gz"
    path.write_bytes(gzip.compress(("{" + body + ',"src_size":1,"src_mtime_ns":1}').encode()))
    assert tracks.read_cache_if_fresh(path, (1, 1)) is None
    with pytest.raises(ValueError, match="corrupt cache"):
        read_cache(path)
