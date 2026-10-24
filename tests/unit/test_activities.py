"""Reading activities.csv: duplicate headers, Strava date format, cycling filter (REQ-002)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from sdash.activities import CYCLING_TYPES, parse_strava_date, read_activities

HEADER = (
    "Activity ID,Activity Date,Activity Name,Activity Type,Elapsed Time,Distance,Activity Gear,"
    "Filename,Elapsed Time,Moving Time,Distance"
)


def _write(path: Path, *rows: str) -> Path:
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return path


def test_parse_strava_date_is_utc() -> None:
    assert parse_strava_date("Oct 20, 2026, 3:45:46 AM") == datetime(
        2026, 10, 20, 3, 45, 46, tzinfo=UTC
    )
    assert parse_strava_date("Jun 1, 2026, 12:00:00 PM") == datetime(
        2026, 6, 1, 12, 0, 0, tzinfo=UTC
    )
    assert parse_strava_date("Jun 1, 2026, 12:05:00 AM") == datetime(
        2026, 6, 1, 0, 5, 0, tzinfo=UTC
    )
    assert parse_strava_date("Dec 31, 2019, 11:59:59 PM") == datetime(
        2019, 12, 31, 23, 59, 59, tzinfo=UTC
    )


def test_parse_strava_date_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="date"):
        parse_strava_date("yesterday")


def test_first_occurrence_of_duplicate_headers_wins(tmp_path: Path) -> None:
    csv_path = _write(
        tmp_path / "activities.csv",
        '5,"Jun 1, 2026, 9:00:00 AM","Morning, ride",Ride,2000,12.50,Bike A,activities/9.gpx,'
        "2007.0,1900.0,12623.4",
    )
    (act,) = read_activities(csv_path)
    assert act.id == "5"
    assert act.name == "Morning, ride"
    assert act.date == datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    assert act.distance_km == 12.5
    assert act.elapsed_s == 2000
    assert act.moving_s == 1900
    assert act.gear == "Bike A"
    assert act.filename == "activities/9.gpx"


def test_blank_numbers_default_to_zero(tmp_path: Path) -> None:
    csv_path = _write(
        tmp_path / "activities.csv",
        '6,"Jun 2, 2026, 9:00:00 AM",x,E-Bike Ride,,,,,,,',
    )
    (act,) = read_activities(csv_path)
    assert (act.distance_km, act.elapsed_s, act.moving_s, act.filename) == (0.0, 0, 0, "")


def test_cycling_filter(tmp_path: Path) -> None:
    rows = [
        f'{i},"Jun 1, 2026, 9:00:00 AM",n,{t},1,1,,f,1,1,1'
        for i, t in enumerate(["Ride", "E-Bike Ride", "Run", "Virtual Ride"])
    ]
    acts = read_activities(_write(tmp_path / "activities.csv", *rows))
    assert [a.type for a in acts if a.is_cycling] == ["Ride", "E-Bike Ride"]
    assert {"Ride", "E-Bike Ride"} == CYCLING_TYPES


def test_missing_column_is_reported(tmp_path: Path) -> None:
    p = tmp_path / "activities.csv"
    p.write_text("Activity ID,Activity Name\n1,x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Activity Date"):
        read_activities(p)


def test_bad_date_on_non_cycling_row_is_ignored(tmp_path: Path) -> None:
    rows = [
        '1,"not a date",n,Run,1,1,,f,1,1,1',
        '2,"Jun 1, 2026, 9:00:00 AM",n,Ride,1,1,,f,1,1,1',
    ]
    acts = read_activities(_write(tmp_path / "activities.csv", *rows), cycling_only=True)
    assert [a.id for a in acts] == ["2"]


def test_bad_date_on_cycling_row_is_collected_or_raised(tmp_path: Path) -> None:
    rows = [
        '1,"not a date",n,Ride,1,1,,f,1,1,1',
        '2,"Jun 1, 2026, 9:00:00 AM",n,Ride,1,1,,f,1,1,1',
    ]
    p = _write(tmp_path / "activities.csv", *rows)
    errors: list[tuple[str, str]] = []
    acts = read_activities(p, cycling_only=True, errors=errors)
    assert [a.id for a in acts] == ["2"]
    assert errors and errors[0][0] == "1" and "date" in errors[0][1]
    with pytest.raises(ValueError, match="date"):
        read_activities(p, cycling_only=True)


# --- T-013: thousands separators -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("2,496", 2496.0),
        ("1,234.5", 1234.5),
        ("-1,234", -1234.0),
        ("1,234,567.89", 1234567.89),
        ("1,234,567.5", 1234567.5),
        ("12.5", 12.5),
        ("", 0.0),
        (" 7 ", 7.0),
    ],
)
def test_numbers_with_thousands_separators(tmp_path: Path, text: str, value: float) -> None:
    row = f'1,"Jun 1, 2026, 9:00:00 AM",n,Swim,1,"{text}",,f,1,1,1'
    (act,) = read_activities(_write(tmp_path / "activities.csv", row))
    assert act.distance_km == value


@pytest.mark.parametrize(
    "text",
    ["2,49", "2,4960", "1,23", ",496", "12,34,567", "1.234,5", "abc", "0,500", "-0,500", "00,500"],
)
def test_decimal_comma_is_never_taken_for_a_thousands_separator(tmp_path: Path, text: str) -> None:
    row = f'7,"Jun 1, 2026, 9:00:00 AM",n,Swim,1,"{text}",,f,1,1,1'
    p = _write(tmp_path / "activities.csv", row)
    errors: list[tuple[str, str]] = []
    assert read_activities(p, errors=errors) == []
    assert errors and errors[0][0] == "7" and "Distance" in errors[0][1], errors
    with pytest.raises(ValueError, match="Distance"):
        read_activities(p)


def test_thousands_separator_row_does_not_hide_other_rows(tmp_path: Path) -> None:
    rows = [
        '1,"Jun 1, 2026, 9:00:00 AM",n,Swim,1,"2,496",,f,1,1,1',
        '2,"Jun 1, 2026, 9:00:00 AM",n,Ride,1,5.5,,f,1,1,1',
    ]
    acts = read_activities(_write(tmp_path / "activities.csv", *rows))
    assert [a.id for a in acts] == ["1", "2"]
