"""Synthetic input builders for the pipeline acceptance tests.

Everything here is made up: tracks are generated around SYNTH_ORIGIN, a point in the open South
Pacific (no land, no roads), so no real ride can ever look like these. The formats mirror the facts
recorded in docs/ARCHITECTURE.md ("External services / APIs"): Strava's activities.csv (duplicated
headers, "Oct 20, 2026, 3:45:46 AM" UTC dates), FIT with `record` messages (semicircles),
StravaGPX-style GPX, TCX, and gzip variants.

T-001 (tests/fixtures/make_fixtures.py) may import these builders instead of duplicating them.
"""

from __future__ import annotations

import csv
import gzip
import io
import itertools
import json
import math
import struct
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------------------------
# Geometry: a local flat frame in metres around a made-up origin.
# --------------------------------------------------------------------------------------------
SYNTH_ORIGIN = (-47.25, -134.75)  # open ocean, South Pacific
# Bounding box every synthetic coordinate must fall into (REQ-010 "synthetic fixtures").
SYNTH_BOX = {"lat": (-48.0, -46.0), "lon": (-136.0, -133.0)}
M_PER_DEG_LAT = 111_194.93  # mean Earth radius 6371 km


def xy_to_latlon(
    x: float, y: float, origin: tuple[float, float] = SYNTH_ORIGIN
) -> tuple[float, float]:
    """x = metres east, y = metres north of origin -> (lat, lon)."""
    lat0, lon0 = origin
    lat = lat0 + y / M_PER_DEG_LAT
    lon = lon0 + x / (M_PER_DEG_LAT * math.cos(math.radians(lat0)))
    return lat, lon


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


@dataclass
class Point:
    t: int  # epoch seconds (UTC)
    lat: float | None
    lon: float | None
    d: float  # cumulative distance in metres


def build_track(
    waypoints_xy: Sequence[tuple[float, float]],
    *,
    start: datetime,
    speed_mps: float = 5.0,
    spacing_m: float = 5.0,
    stops: Iterable[tuple[float, int]] = (),
    first_offset_m: float = 0.0,
) -> list[Point]:
    """Sample a polyline (metres) at `spacing_m`, moving at `speed_mps`.

    stops: (distance_m_along_path, seconds) -> the rider stands still there (extra points, same
    position, time advancing every second). first_offset_m shifts where the first sample lies,
    so sparse tracks need not hit waypoints exactly.
    """
    stops_left = sorted(stops)
    legs: list[tuple[tuple[float, float], tuple[float, float], float]] = []
    total = 0.0
    for (x1, y1), (x2, y2) in itertools.pairwise(waypoints_xy):
        length = math.hypot(x2 - x1, y2 - y1)
        legs.append(((x1, y1), (x2, y2), length))
        total += length

    def pos_at(s: float) -> tuple[float, float]:
        for (x1, y1), (x2, y2), length in legs:
            if s <= length:
                f = 0.0 if length == 0 else s / length
                return x1 + (x2 - x1) * f, y1 + (y2 - y1) * f
            s -= length
        return legs[-1][1]

    t0 = int(start.timestamp())
    points: list[Point] = []
    s = first_offset_m
    t = float(t0)
    while s <= total + 1e-9:
        lat, lon = xy_to_latlon(*pos_at(s))
        points.append(Point(round(t), lat, lon, s))
        while stops_left and stops_left[0][0] <= s:
            _, secs = stops_left.pop(0)
            for _ in range(secs):
                t += 1
                points.append(Point(round(t), lat, lon, s))
        s += spacing_m
        t += spacing_m / speed_mps
    return points


def straight_north(y0: float, y1: float, x: float = 0.0) -> list[tuple[float, float]]:
    return [(x, y0), (x, y1)]


# --------------------------------------------------------------------------------------------
# File writers
# --------------------------------------------------------------------------------------------
def _iso(t: int) -> str:
    return datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def gpx_bytes(points: Sequence[Point], name: str = "Synthetic ride") -> bytes:
    """StravaGPX-style GPX 1.1 (trkpt with ele and time, no extensions)."""
    out = io.StringIO()
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.write(
        '<gpx creator="StravaGPX" version="1.1" xmlns="http://www.topografix.com/GPX/1/1" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://www.topografix.com/GPX/1/1 '
        'http://www.topografix.com/GPX/1/1/gpx.xsd">\n'
    )
    out.write(f" <metadata>\n  <time>{_iso(points[0].t)}</time>\n </metadata>\n")
    out.write(f" <trk>\n  <name>{name}</name>\n  <type>1</type>\n  <trkseg>\n")
    for p in points:
        if p.lat is None or p.lon is None:
            continue
        out.write(
            f'   <trkpt lat="{p.lat:.7f}" lon="{p.lon:.7f}">\n'
            f"    <ele>12.0</ele>\n    <time>{_iso(p.t)}</time>\n   </trkpt>\n"
        )
    out.write("  </trkseg>\n </trk>\n</gpx>\n")
    return out.getvalue().encode()


def tcx_bytes(points: Sequence[Point]) -> bytes:
    out = io.StringIO()
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.write(
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/'
        'TrainingCenterDatabase/v2">\n <Activities>\n  <Activity Sport="Biking">\n'
    )
    out.write(f'   <Id>{_iso(points[0].t)}</Id>\n   <Lap StartTime="{_iso(points[0].t)}">\n')
    out.write("    <Track>\n")
    for p in points:
        out.write(f"     <Trackpoint>\n      <Time>{_iso(p.t)}</Time>\n")
        if p.lat is not None and p.lon is not None:
            out.write(
                f"      <Position>\n       <LatitudeDegrees>{p.lat:.7f}</LatitudeDegrees>\n"
                f"       <LongitudeDegrees>{p.lon:.7f}</LongitudeDegrees>\n      </Position>\n"
            )
        out.write(f"      <DistanceMeters>{p.d:.1f}</DistanceMeters>\n     </Trackpoint>\n")
    out.write("    </Track>\n   </Lap>\n  </Activity>\n </Activities>\n</TrainingCenterDatabase>\n")
    return out.getvalue().encode()


# FIT: minimal, valid FIT 1.0 file with file_id + record messages (see FIT SDK "FIT File Types").
FIT_EPOCH = 631_065_600  # 1989-12-31T00:00:00Z
_CRC_TABLE = (
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
)  # fmt: skip


def fit_crc(data: bytes, crc: int = 0) -> int:
    for byte in data:
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[byte & 0xF]
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[(byte >> 4) & 0xF]
    return crc


def _semicircles(deg: float) -> int:
    return round(deg * (2**31) / 180.0)


def fit_bytes(points: Sequence[Point]) -> bytes:
    """Encode points as FIT `record` messages (timestamp, position_lat/long, distance).

    Points with lat/lon None get the FIT invalid value (0x7FFFFFFF), i.e. "no position".
    """
    body = bytearray()
    # Definition, local 0 -> global 0 file_id: type(0,enum), manufacturer(1,uint16), time_created(4,uint32)
    body += bytes([0x40, 0, 0]) + struct.pack("<HB", 0, 3)
    body += bytes([0, 1, 0x00, 1, 2, 0x84, 4, 4, 0x86])
    body += bytes([0x00]) + struct.pack("<BHI", 4, 255, points[0].t - FIT_EPOCH)
    # Definition, local 1 -> global 20 record: timestamp(253), position_lat(0), position_long(1), distance(5)
    body += bytes([0x41, 0, 0]) + struct.pack("<HB", 20, 4)
    body += bytes([253, 4, 0x86, 0, 4, 0x85, 1, 4, 0x85, 5, 4, 0x86])
    for p in points:
        lat = 0x7FFFFFFF if p.lat is None else _semicircles(p.lat)
        lon = 0x7FFFFFFF if p.lon is None else _semicircles(p.lon)
        body += bytes([0x01]) + struct.pack("<IiiI", p.t - FIT_EPOCH, lat, lon, round(p.d * 100))
    header = struct.pack("<BBHI4s", 14, 0x10, 2132, len(body), b".FIT")
    header += struct.pack("<H", fit_crc(header))
    data = header + bytes(body)
    return data + struct.pack("<H", fit_crc(data))


def encode_track(points: Sequence[Point], fmt: str) -> bytes:
    """fmt: one of gpx, gpx.gz, fit, fit.gz, tcx, tcx.gz."""
    base = fmt.removesuffix(".gz")
    raw = {"gpx": gpx_bytes, "fit": fit_bytes, "tcx": tcx_bytes}[base](points)
    return gzip.compress(raw, mtime=0) if fmt.endswith(".gz") else raw


# --------------------------------------------------------------------------------------------
# activities.csv (Strava export layout)
# --------------------------------------------------------------------------------------------
# Column order as publicly documented for Strava bulk exports. docs/ARCHITECTURE.md records that the
# real file has 101 columns with `Elapsed Time`, `Distance`, `Max Heart Rate`, `Relative Effort`
# and `Commute` duplicated (first occurrence = summary values) but not the full list; this list has
# those duplicates in the documented positions. T-001 should reconcile the exact list.
ACTIVITIES_HEADER: list[str] = [
    "Activity ID", "Activity Date", "Activity Name", "Activity Type", "Activity Description",
    "Elapsed Time", "Distance", "Max Heart Rate", "Relative Effort", "Commute",
    "Activity Private Note", "Activity Gear", "Filename", "Athlete Weight", "Bike Weight",
    "Elapsed Time", "Moving Time", "Distance", "Max Speed", "Average Speed", "Elevation Gain",
    "Elevation Loss", "Elevation Low", "Elevation High", "Max Grade", "Average Grade",
    "Average Positive Grade", "Average Negative Grade", "Max Cadence", "Average Cadence",
    "Max Heart Rate", "Average Heart Rate", "Max Watts", "Average Watts", "Calories",
    "Max Temperature", "Average Temperature", "Relative Effort", "Total Work", "Number of Runs",
    "Uphill Time", "Downhill Time", "Other Time", "Perceived Exertion", "Type", "Start Time",
    "Weighted Average Power", "Power Count", "Prefer Perceived Exertion",
    "Perceived Relative Effort", "Commute", "Total Weight Lifted", "From Upload",
    "Grade Adjusted Distance", "Weather Observation Time", "Weather Condition",
    "Weather Temperature", "Apparent Temperature", "Dewpoint", "Humidity", "Weather Pressure",
    "Wind Speed", "Wind Gust", "Wind Bearing", "Precipitation Intensity", "Sunrise Time",
    "Sunset Time", "Moon Phase", "Bike", "Gear", "Precipitation Probability",
    "Precipitation Type", "Cloud Cover", "Weather Visibility", "UV Index", "Weather Ozone",
    "Jump Count", "Total Grit", "Average Flow", "Flagged", "Average Elapsed Speed",
    "Dirt Distance", "Newly Explored Distance", "Newly Explored Dirt Distance", "Activity Count",
    "Total Steps", "Carbon Saved", "Pool Length", "Training Load", "Intensity",
    "Average Grade Adjusted Pace", "Timer Time", "Total Cycles", "Recovery", "With Pet",
    "Competition", "Long Run", "For a Cause", "Media",
]  # fmt: skip
DUPLICATED_COLUMNS = ("Elapsed Time", "Distance", "Max Heart Rate", "Relative Effort", "Commute")


def strava_date(dt: datetime) -> str:
    """'Oct 20, 2026, 3:45:46 AM' (UTC), as in the real export."""
    dt = dt.astimezone(UTC)
    hour12 = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt:%b} {dt.day}, {dt.year}, {hour12}:{dt:%M}:{dt:%S} {ampm}"


@dataclass
class Activity:
    id: str
    date: datetime
    name: str
    type: str = "Ride"
    gear: str = "Synthetic road bike"
    filename: str = ""  # e.g. "activities/9100001.gpx"; file ID != activity ID
    distance_km: float = 0.0
    elapsed_s: int = 0
    moving_s: int = 0
    extra: dict[str, str] = field(default_factory=dict)


def activities_csv(activities: Sequence[Activity]) -> bytes:
    """Build activities.csv. Second occurrences of duplicated columns hold *different* values
    (metres instead of km, decimals) so a reader that takes the last occurrence is caught."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(ACTIVITIES_HEADER)
    for a in activities:
        seen: set[str] = set()
        row: list[str] = []
        for col in ACTIVITIES_HEADER:
            first = col not in seen
            seen.add(col)
            if col in a.extra:
                row.append(a.extra[col])
            elif col == "Activity ID":
                row.append(a.id)
            elif col == "Activity Date":
                row.append(strava_date(a.date))
            elif col == "Activity Name":
                row.append(a.name)
            elif col == "Activity Type":
                row.append(a.type)
            elif col == "Activity Gear":
                row.append(a.gear)
            elif col == "Filename":
                row.append(a.filename)
            elif col == "Elapsed Time":
                row.append(str(a.elapsed_s) if first else f"{a.elapsed_s + 7}.0")
            elif col == "Moving Time":
                row.append(f"{a.moving_s}.0")
            elif col == "Distance":
                row.append(f"{a.distance_km:.2f}" if first else f"{a.distance_km * 1000 + 123:.1f}")
            elif col == "Commute":
                row.append("false" if first else "0.0")
            elif col == "Relative Effort":
                row.append("12" if first else "13.0")
            elif col == "Max Heart Rate":
                row.append("150" if first else "151.0")
            else:
                row.append("")
        w.writerow(row)
    return out.getvalue().encode()


# --------------------------------------------------------------------------------------------
# Export / data-dir builders
# --------------------------------------------------------------------------------------------
SEGMENTS_CSV_HEADER = [
    "Segment Name", "Activity ID", "Starting Latitude", "Starting Longitude",
    "Ending Latitude", "Ending Longitude",
]  # fmt: skip

PERSONAL_FILES: dict[str, bytes] = {
    "messages.json": b'[{"from": "Synthetic Friend", "text": "dummy"}]',
    "contacts.csv": b"Name,Email\nSynthetic Friend,friend@example.invalid\n",
    "profile.csv": b"Athlete ID,First Name\n1,Synthetic\n",
    "logins.csv": b"Login Time,IP\n2026-01-01,192.0.2.1\n",
    "media/0001.jpg": b"\xff\xd8\xff\xe0 synthetic jpeg",
    "media/0002.mp4": b"synthetic video",
}
ALLOWED_EXPORT_FILES = {
    "activities.csv", "segments.csv", "starred_segments.csv", "bikes.csv", "components.csv",
}  # fmt: skip


def segments_csv(rows: Sequence[tuple[str, str, float, float, float, float]]) -> bytes:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(SEGMENTS_CSV_HEADER)
    for name, act, slat, slon, elat, elon in rows:
        w.writerow([name, act, f"{slat:.6f}", f"{slon:.6f}", f"{elat:.6f}", f"{elon:.6f}"])
    return out.getvalue().encode()


@dataclass
class Ride:
    """An activity plus its track and file format."""

    activity: Activity
    points: list[Point] | None
    fmt: str = "gpx"
    file_id: str = ""
    raw_bytes: bytes | None = None  # overrides encoding (e.g. corrupt files)

    def __post_init__(self) -> None:
        if not self.file_id:
            self.file_id = str(9_000_000 + int(self.activity.id) % 1_000_000)
        if not self.activity.filename:
            self.activity.filename = f"activities/{self.file_id}.{self.fmt}"
        if self.points and not self.activity.elapsed_s:
            self.activity.elapsed_s = self.points[-1].t - self.points[0].t
            self.activity.moving_s = self.activity.elapsed_s
            self.activity.distance_km = round(self.points[-1].d / 1000, 2)

    def file_bytes(self) -> bytes:
        if self.raw_bytes is not None:
            return self.raw_bytes
        assert self.points is not None
        return encode_track(self.points, self.fmt)


def export_files(
    rides: Sequence[Ride],
    *,
    segments_rows: Sequence[tuple[str, str, float, float, float, float]] = (),
    personal: bool = True,
) -> dict[str, bytes]:
    """All files of a synthetic export (path inside the zip -> bytes)."""
    files: dict[str, bytes] = {"activities.csv": activities_csv([r.activity for r in rides])}
    for r in rides:
        if r.activity.filename:
            files[r.activity.filename] = r.file_bytes()
    files["segments.csv"] = segments_csv(segments_rows)
    files["starred_segments.csv"] = b"Starred Date,Segment ID\n"
    files["bikes.csv"] = b"Bike Name,Bike Brand,Bike Model\nSynthetic road bike,Acme,One\n"
    if personal:
        files.update(PERSONAL_FILES)
    return files


def write_zip(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 20, 3, 45, 46))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
    return path


def write_raw(data_dir: Path, rides: Sequence[Ride], **kw: Any) -> Path:
    """Lay out an already-imported data dir (data_dir/raw/...) without running `sdash import`."""
    raw = data_dir / "raw"
    for name, data in export_files(rides, personal=False, **kw).items():
        target = raw / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return raw


def segments_yaml(segments: Sequence[dict[str, Any]]) -> str:
    """Serialise segments in the ARCHITECTURE.md segments.yaml shape (JSON is valid YAML)."""
    lines = []
    for s in segments:
        lines.append(f"- name: {json.dumps(s['name'])}")
        for key in ("ref_activity", "start", "end"):
            if key in s:
                lines.append(f"  {key}: {json.dumps(s[key])}")
    return "\n".join(lines) + "\n" if lines else "[]\n"
