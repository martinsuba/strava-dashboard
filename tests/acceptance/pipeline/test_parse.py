"""REQ-002: Parse rides. Tracks are read back from the cache documented in docs/ARCHITECTURE.md
(cache/<activity id>.json.gz with arrays t, lat, lon, d); activity fields from rides/<id>.json."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import _scenarios as sc
import pytest
from _synth import Activity, Point, Ride, segments_yaml, write_raw
from conftest import SdashRunner, load_json, read_cached_track, run_pipeline

pytestmark = pytest.mark.req("REQ-002")


def _track(n_missing_at: tuple[int, ...] = ()) -> list[Point]:
    pts = sc.ride("1", [(0, 0), (0, 2000)], spacing_m=20.0).points
    assert pts
    for i in n_missing_at:
        pts[i] = Point(pts[i].t, None, None, pts[i].d)
    return pts


def _ride(activity_id: str, type: str = "Ride", fmt: str = "gpx", **kw) -> Ride:
    start = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    return Ride(
        Activity(activity_id, start, f"Synthetic {type} {activity_id[-2:]}", type=type),
        kw.pop("points", None) or _track(),
        fmt=fmt,
        **kw,
    )


def test_req002_only_ride_and_ebike_are_kept(sdash: SdashRunner, data_dir: Path) -> None:
    rides = [
        _ride("1000000011", "Ride"),
        _ride("1000000012", "E-Bike Ride"),
        _ride("1000000013", "Run"),
        _ride("1000000014", "Virtual Ride"),
    ]
    write_raw(data_dir, rides)
    sdash("parse").ok()
    cached = {p.name.removesuffix(".json.gz") for p in (data_dir / "cache").glob("*.json.gz")}
    assert {"1000000011", "1000000012"} <= cached
    assert not cached & {"1000000013", "1000000014"}, f"non-cycling activities parsed: {cached}"


FORMATS = ["gpx", "gpx.gz", "fit", "fit.gz", "tcx.gz"]


@pytest.mark.parametrize("fmt", FORMATS)
def test_req002_each_format_yields_track(sdash: SdashRunner, data_dir: Path, fmt: str) -> None:
    missing = () if fmt.startswith("gpx") else (10, 11, 50)  # records without a position
    pts = _track(missing)
    write_raw(data_dir, [_ride("1000000031", fmt=fmt, points=pts)])
    sdash("parse").ok()
    track = read_cached_track(data_dir, "1000000031")
    expected = [p for p in pts if p.lat is not None]
    assert (
        len(track["t"])
        == len(track["lat"])
        == len(track["lon"])
        == len(track["d"])
        == len(expected)
    )
    assert [int(t) for t in track["t"]] == [p.t for p in expected]
    for got_lat, got_lon, p in zip(track["lat"], track["lon"], expected, strict=True):
        assert abs(got_lat - p.lat) < 1e-5 and abs(got_lon - p.lon) < 1e-5  # type: ignore[operator]
    assert all(b >= a for a, b in zip(track["d"], track["d"][1:], strict=False)), (
        "d must not decrease"
    )
    assert abs(track["d"][-1] - 2000) < 40, f"cumulative distance {track['d'][-1]} != ~2000 m"


def test_req002_unparseable_file_reported_run_continues(sdash: SdashRunner, data_dir: Path) -> None:
    rides = [
        _ride("1000000021", fmt="gpx"),
        _ride("1000000022", fmt="fit", raw_bytes=b"\x0e\x10garbage, not a FIT file" * 20),
        _ride("1000000023", fmt="fit.gz"),
    ]
    write_raw(data_dir, rides)
    result = sdash("parse")
    assert result.returncode == 0, f"one bad file must not stop the run:\n{result.output}"
    read_cached_track(data_dir, "1000000021")
    read_cached_track(data_dir, "1000000023")
    reports = (
        "".join(
            p.read_text(errors="replace") for p in (data_dir / "reports").rglob("*") if p.is_file()
        )
        if (data_dir / "reports").is_dir()
        else ""
    )
    report_lines = [
        line for line in (result.output + "\n" + reports).splitlines() if "1000000022" in line
    ]
    assert report_lines, "the failed activity ID must appear in the run report"
    assert any(
        len(line.replace("1000000022", "").strip(" \t:,-|\"'{}[]")) >= 5 for line in report_lines
    ), f"no reason given next to the activity ID: {report_lines}"


def _swap_lat_keep_size_and_mtime(path: Path) -> None:
    """Rewrite the GPX with every latitude moved 1 degree north: same byte size; mtime restored."""
    st = path.stat()
    data = path.read_bytes()
    swapped = data.replace(b'lat="-47.2', b'lat="-46.2')
    assert swapped != data and len(swapped) == len(data)
    path.write_bytes(swapped)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))


def test_req002_unchanged_ride_read_from_cache(sdash: SdashRunner, data_dir: Path) -> None:
    ride = _ride("1000000041", fmt="gpx")
    write_raw(data_dir, [ride])
    sdash("parse").ok()
    first = read_cached_track(data_dir, "1000000041")
    _swap_lat_keep_size_and_mtime(data_dir / "raw" / ride.activity.filename)
    sdash("parse").ok()
    second = read_cached_track(data_dir, "1000000041")
    assert second["lat"][0] == pytest.approx(first["lat"][0], abs=1e-6), (
        "unchanged file (same size + mtime) was re-parsed instead of read from the cache"
    )


def test_req002_changed_ride_is_parsed_again(sdash: SdashRunner, data_dir: Path) -> None:
    ride = _ride("1000000042", fmt="gpx")
    write_raw(data_dir, [ride])
    sdash("parse").ok()
    path = data_dir / "raw" / ride.activity.filename
    _swap_lat_keep_size_and_mtime(path)
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    sdash("parse").ok()
    assert read_cached_track(data_dir, "1000000042")["lat"][0] == pytest.approx(-46.25, abs=0.01)


def _csv_ride(
    activity_id: str,
    when: datetime,
    name: str,
    type: str = "Ride",
    gear: str = "Synthetic gravel bike",
) -> Ride:
    act = Activity(
        activity_id,
        when,
        name,
        type=type,
        gear=gear,
        distance_km=25.31,
        elapsed_s=3600,
        moving_s=3300,
    )
    return Ride(act, _track(), fmt="gpx")


def test_req002_activities_csv_dates_and_duplicate_columns(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path
) -> None:
    cases = {
        "1000000051": (
            datetime(2026, 10, 20, 3, 45, 46, tzinfo=UTC),
            'Ride, with "quotes"',
            "Ride",
        ),
        "1000000052": (datetime(2026, 10, 21, 12, 5, 0, tzinfo=UTC), "Noon e-bike", "E-Bike Ride"),
        "1000000053": (datetime(2026, 10, 22, 0, 30, 0, tzinfo=UTC), "Past midnight", "Ride"),
    }
    rides = [_csv_ride(i, when, name, type) for i, (when, name, type) in cases.items()]
    rides.append(
        _csv_ride("1000000054", datetime(2026, 10, 23, 7, 0, tzinfo=UTC), "Synthetic run", "Run")
    )
    write_raw(data_dir, rides)
    (data_dir / "segments.yaml").write_text(segments_yaml([]))
    out = run_pipeline(sdash, tmp_path / "site-data")

    index_ids = {str(r["id"]) for r in load_json(out / "index.json")["rides"]}
    assert index_ids == set(cases), f"ride list must hold exactly the cycling rides: {index_ids}"
    for activity_id, (when, name, _type) in cases.items():
        ride = load_json(out / "rides" / f"{activity_id}.json")
        got = datetime.fromisoformat(ride["date"])
        got = got if got.tzinfo else got.replace(tzinfo=UTC)
        assert got == when, f"{activity_id}: date {ride['date']} != {when.isoformat()}"
        assert ride["name"] == name
        assert ride["gear"] == "Synthetic gravel bike"
        assert ride["km"] == pytest.approx(25.31, abs=0.01), "Distance: first occurrence (km) wins"
        assert ride["elapsed_s"] == 3600, "Elapsed Time: first occurrence wins"
        assert ride["moving_s"] == 3300


def test_req002_thousands_separator_row_does_not_break_reading_or_references(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path
) -> None:
    """Real data: Swim/Rowing rows have Distance like "2,496" (metres). Every row must still be
    read; here the hike used as a segment reference sits after such a row."""
    swim = Ride(
        Activity(
            "1000000071",
            datetime(2026, 5, 1, 7, 0, tzinfo=UTC),
            "Synthetic swim",
            type="Swim",
            extra={"Distance": "2,496"},
        ),
        None,
        fmt="gpx",
        raw_bytes=b"not used",
    )
    ride = sc.ride("1000000002", [(0, -500), (0, 2500)], day=1)
    write_raw(data_dir, [swim, sc.hike_reference(), ride])
    (data_dir / "segments.yaml").write_text(segments_yaml([sc.segment()]))
    parsed = sdash("parse").ok()
    assert "1000000071" not in parsed.output, "a non-cycling row is not a failure"
    assert "1000000001" not in parsed.output, (
        f"the hike reference failed to parse:\n{parsed.output}"
    )
    read_cached_track(data_dir, sc.REF_ID)
    sdash("match").ok()
    out = tmp_path / "site-data"
    sdash("build-data", "--out", out).ok()
    assert [r["id"] for r in load_json(out / "index.json")["rides"]] == ["1000000002"]
    efforts = load_json(out / "segments" / "synthetic-climb.json")["efforts"]
    assert [e["activity_id"] for e in efforts] == ["1000000002"]


@pytest.mark.parametrize("prefix", [b"\n  ", b"\xef\xbb\xbf\n", b"Exported by Synthetic\n"])
def test_req002_tcx_with_text_before_the_xml_declaration(
    sdash: SdashRunner, data_dir: Path, prefix: bytes
) -> None:
    """Real data: a Strava TCX with text/whitespace/BOM before `<?xml`."""
    from _synth import tcx_bytes

    pts = _track()
    ride = _ride("1000000081", fmt="tcx", points=pts, raw_bytes=prefix + tcx_bytes(pts))
    write_raw(data_dir, [ride])
    result = sdash("parse").ok()
    assert "1000000081" not in result.output, f"parse reported a failure:\n{result.output}"
    track = read_cached_track(data_dir, "1000000081")
    assert len(track["t"]) == len(pts)
    assert abs(track["d"][-1] - 2000) < 40
