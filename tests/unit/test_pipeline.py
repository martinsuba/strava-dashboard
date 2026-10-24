"""Untrusted data (activities.csv, segments.yaml) must not reach outside the data dir."""

from __future__ import annotations

import importlib.util
import shutil
import struct
import sys
from pathlib import Path

import pytest

from sdash.pipeline import PipelineError, match_segments, parse_rides

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "minimal.gpx"
HEADER = (
    "Activity ID,Activity Date,Activity Name,Activity Type,Filename,"
    "Activity Gear,Distance,Elapsed Time,Moving Time"
)


def _data(tmp_path: Path, *rows: str) -> Path:
    data = tmp_path / "data"
    (data / "raw" / "activities").mkdir(parents=True)
    shutil.copy(FIXTURE, data / "raw" / "activities" / "ok.gpx")
    shutil.copy(FIXTURE, tmp_path / "outside.gpx")
    (data / "raw" / "activities.csv").write_text("\n".join([HEADER, *rows]) + "\n")
    return data


def _row(
    activity_id: str, filename: str, type_: str = "Ride", date: str = "Jun 1, 2026, 9:00:00 AM"
) -> str:
    return f'{activity_id},"{date}",n,{type_},{filename},,0,0,0'


def test_good_ride_is_parsed(tmp_path: Path) -> None:
    data = _data(tmp_path, _row("5", "activities/ok.gpx"))
    report = parse_rides(data)
    assert report.parsed == 1 and report.failed == []
    assert (data / "cache" / "5.json.gz").is_file()


@pytest.mark.parametrize("bad_id", ["../evil", "1/../../x", "abc", ""])
def test_activity_id_must_be_numeric(tmp_path: Path, bad_id: str) -> None:
    data = _data(tmp_path, _row(bad_id, "activities/ok.gpx"), _row("6", "activities/ok.gpx"))
    report = parse_rides(data)
    assert report.parsed == 1
    assert [f[0] for f in report.failed] == [bad_id]
    assert sorted(p.name for p in (data / "cache").iterdir()) == ["6.json.gz"]
    assert not (tmp_path / "evil.json.gz").exists()


@pytest.mark.parametrize("name", ["../../outside.gpx", "activities/../../../outside.gpx"])
def test_filename_with_parent_dirs_is_reported(tmp_path: Path, name: str) -> None:
    data = _data(tmp_path, _row("7", name))
    report = parse_rides(data)
    assert report.parsed == 0
    assert report.failed and report.failed[0][0] == "7" and "outside" in report.failed[0][1]


def test_absolute_filename_is_reported(tmp_path: Path) -> None:
    data = _data(tmp_path, _row("8", str(tmp_path / "outside.gpx")))
    report = parse_rides(data)
    assert report.parsed == 0 and report.failed[0][0] == "8"


def test_bad_date_on_a_ride_is_a_failed_ride_and_run_continues(tmp_path: Path) -> None:
    data = _data(
        tmp_path,
        _row("1", "activities/ok.gpx", date="garbage"),
        _row("2", "activities/ok.gpx", type_="Run", date="garbage"),
        _row("3", "activities/ok.gpx"),
    )
    report = parse_rides(data)
    assert report.parsed == 1
    assert [f[0] for f in report.failed] == ["1"]


def test_bad_ref_activity_names_the_segment(tmp_path: Path) -> None:
    data = _data(tmp_path, _row("5", "activities/ok.gpx"))
    (data / "segments.yaml").write_text(
        '- name: "Sneaky"\n  ref_activity: "../../x"\n  start: [-47.0, -134.0]\n'
        "  end: [-46.9, -134.0]\n"
    )
    with pytest.raises(PipelineError, match="Sneaky"):
        match_segments(data)


# --- T-003: cache and cycling filter ------------------------------------------------------------


def test_unchanged_ride_is_not_parsed_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdash import pipeline

    data = _data(tmp_path, _row("5", "activities/ok.gpx"))
    assert parse_rides(data).parsed == 1
    calls: list[Path] = []
    real = pipeline.parse_track
    monkeypatch.setattr(pipeline, "parse_track", lambda p: calls.append(p) or real(p))
    assert parse_rides(data).parsed == 1
    assert calls == []


def test_changed_size_or_mtime_invalidates_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    from sdash import pipeline

    data = _data(tmp_path, _row("5", "activities/ok.gpx"))
    parse_rides(data)
    ride = data / "raw" / "activities" / "ok.gpx"
    calls: list[Path] = []
    real = pipeline.parse_track
    monkeypatch.setattr(pipeline, "parse_track", lambda p: calls.append(p) or real(p))
    st = ride.stat()
    os.utime(ride, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    parse_rides(data)
    assert len(calls) == 1
    ride.write_bytes(ride.read_bytes() + b"\n")  # size (and mtime) changed
    parse_rides(data)
    assert len(calls) == 2


def test_corrupt_cache_file_is_rebuilt(tmp_path: Path) -> None:
    data = _data(tmp_path, _row("5", "activities/ok.gpx"))
    parse_rides(data)
    (data / "cache" / "5.json.gz").write_bytes(b"junk")
    assert parse_rides(data).parsed == 1
    assert (data / "cache" / "5.json.gz").read_bytes() != b"junk"


def test_corrupt_fit_is_reported_and_others_continue(tmp_path: Path) -> None:
    data = _data(tmp_path, _row("1", "activities/bad.fit"), _row("2", "activities/ok.gpx"))
    (data / "raw" / "activities" / "bad.fit").write_bytes(b"\x0e\x10nonsense" * 10)
    report = parse_rides(data)
    assert report.parsed == 1
    assert [f[0] for f in report.failed] == ["1"]
    assert report.failed[0][1]


def test_only_ride_and_ebike_are_parsed(tmp_path: Path) -> None:
    data = _data(
        tmp_path,
        _row("1", "activities/ok.gpx", "Ride"),
        _row("2", "activities/ok.gpx", "E-Bike Ride"),
        _row("3", "activities/ok.gpx", "Run"),
        _row("4", "activities/ok.gpx", "Virtual Ride"),
    )
    parse_rides(data)
    assert sorted(p.name for p in (data / "cache").iterdir()) == ["1.json.gz", "2.json.gz"]


def _synth():  # type: ignore[no-untyped-def]
    path = Path(__file__).resolve().parents[1] / "acceptance" / "pipeline" / "_synth.py"
    spec = importlib.util.spec_from_file_location("_synth_for_pipeline_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fit() -> bytes:
    mod = _synth()
    pts = [mod.Point(1_780_000_000 + 10 * i, -47.25 + 0.0001 * i, -134.75, 0.0) for i in range(20)]
    return bytes(mod.fit_bytes(pts))


def _bad_fit(good: bytes) -> bytes:
    """Valid CRC, but the timestamp field has base type uint16 with size 4: fitdecode raises TypeError."""
    data = bytearray(good)
    data[good.index(bytes([253, 4, 0x86])) + 2] = 0x84
    data[-2:] = struct.pack("<H", _synth().fit_crc(bytes(data[:-2])))
    return bytes(data)


def test_bad_fit_between_good_rides_is_reported_and_others_cached(tmp_path: Path) -> None:
    data = _data(
        tmp_path,
        _row("1", "activities/ok.gpx"),
        _row("2", "activities/bad.fit"),
        _row("3", "activities/ok.fit"),
    )
    good = _fit()
    (data / "raw" / "activities" / "ok.fit").write_bytes(good)
    (data / "raw" / "activities" / "bad.fit").write_bytes(_bad_fit(good))
    report = parse_rides(data)
    assert report.parsed == 2
    assert [f[0] for f in report.failed] == ["2"]
    assert sorted(p.name for p in (data / "cache").iterdir()) == ["1.json.gz", "3.json.gz"]


def test_unexpected_exception_in_a_parser_is_a_failed_ride(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdash import pipeline

    real = pipeline.parse_track

    def flaky(path: Path):  # type: ignore[no-untyped-def]
        if path.name == "bad.gpx":
            raise AttributeError("boom")
        return real(path)

    monkeypatch.setattr(pipeline, "parse_track", flaky)
    data = _data(tmp_path, _row("1", "activities/bad.gpx"), _row("2", "activities/ok.gpx"))
    shutil.copy(FIXTURE, data / "raw" / "activities" / "bad.gpx")
    report = parse_rides(data)
    assert report.parsed == 1 and [f[0] for f in report.failed] == ["1"]


def test_stale_cache_removed_when_changed_ride_fails_or_vanishes(tmp_path: Path) -> None:
    data = _data(tmp_path, _row("1", "activities/a.gpx"), _row("2", "activities/b.gpx"))
    for n in ("a", "b"):
        shutil.copy(FIXTURE, data / "raw" / "activities" / f"{n}.gpx")
    assert parse_rides(data).parsed == 2
    (data / "raw" / "activities" / "a.gpx").write_text("not xml now")
    (data / "raw" / "activities" / "b.gpx").unlink()
    report = parse_rides(data)
    assert report.parsed == 0 and len(report.failed) == 2
    assert not list((data / "cache").glob("*.json.gz"))


def test_match_with_corrupt_cache_gives_pipeline_error(tmp_path: Path) -> None:
    data = _data(tmp_path, _row("1", "activities/ok.gpx"))
    (data / "cache").mkdir()
    (data / "cache" / "1.json.gz").write_bytes(b"garbage")
    (data / "segments.yaml").write_text(
        '- name: s\n  ref_activity: "1"\n  start: [-47.0, -134.0]\n  end: [-47.001, -134.0]\n'
    )
    with pytest.raises(PipelineError, match="cache"):
        match_segments(data)
