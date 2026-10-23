"""Read activities.csv from the Strava export (docs/ARCHITECTURE.md, "Data model")."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

CYCLING_TYPES = frozenset({"Ride", "E-Bike Ride"})

_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTHS = {m: i for i, m in enumerate(_MONTH_NAMES, 1)}


@dataclass(frozen=True)
class Activity:
    id: str
    date: datetime  # UTC
    name: str
    type: str
    gear: str
    filename: str  # relative to raw/, e.g. "activities/123.fit.gz"; may be empty
    distance_km: float
    elapsed_s: int
    moving_s: int

    @property
    def is_cycling(self) -> bool:
        return self.type in CYCLING_TYPES


def parse_strava_date(text: str) -> datetime:
    """'Oct 20, 2026, 3:45:46 AM' (UTC) -> aware datetime. Locale independent."""
    try:
        day_part, year, clock = (p.strip() for p in text.split(","))
        month_name, day = day_part.split()
        hms, ampm = clock.split()
        hour, minute, second = (int(x) for x in hms.split(":"))
        if ampm not in ("AM", "PM") or not 1 <= hour <= 12:
            raise ValueError(ampm)
        hour = hour % 12 + (12 if ampm == "PM" else 0)
        return datetime(int(year), _MONTHS[month_name], int(day), hour, minute, second, tzinfo=UTC)
    except (ValueError, KeyError) as exc:
        raise ValueError(f"unrecognised activity date {text!r}") from exc


def _number(text: str) -> float:
    return float(text) if text.strip() else 0.0


def read_activities(path: Path) -> list[Activity]:
    """All rows of activities.csv. For duplicated column names the first occurrence is used."""
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        first: dict[str, int] = {}
        for i, name in enumerate(header):
            first.setdefault(name, i)
        needed = [
            "Activity ID",
            "Activity Date",
            "Activity Name",
            "Activity Type",
            "Activity Gear",
            "Filename",
            "Distance",
            "Elapsed Time",
            "Moving Time",
        ]
        missing = [c for c in needed if c not in first]
        if missing:
            raise ValueError(f"{path.name}: missing column(s) {', '.join(missing)}")

        def cell(row: list[str], name: str) -> str:
            i = first[name]
            return row[i] if i < len(row) else ""

        return [
            Activity(
                id=cell(row, "Activity ID").strip(),
                date=parse_strava_date(cell(row, "Activity Date")),
                name=cell(row, "Activity Name"),
                type=cell(row, "Activity Type"),
                gear=cell(row, "Activity Gear"),
                filename=cell(row, "Filename"),
                distance_km=_number(cell(row, "Distance")),
                elapsed_s=round(_number(cell(row, "Elapsed Time"))),
                moving_s=round(_number(cell(row, "Moving Time"))),
            )
            for row in reader
            if row
        ]
