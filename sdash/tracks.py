"""Ride files -> Track (time, position, cumulative distance), plus the per-ride cache.

Only GPX is read so far; FIT/TCX/.gz and the size+mtime cache key arrive with T-003.
"""

from __future__ import annotations

import gzip
import json
import math
from dataclasses import dataclass
from pathlib import Path

import gpxpy
import gpxpy.gpx

EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class Track:
    t: list[int]  # epoch seconds
    lat: list[float]
    lon: list[float]
    d: list[float]  # cumulative distance in metres


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _parse_gpx(path: Path) -> Track:
    try:
        gpx = gpxpy.parse(path.read_text(encoding="utf-8"))
    except Exception as exc:  # gpxpy raises several exception types for bad input
        raise ValueError(f"cannot read GPX {path.name}: {exc}") from exc
    t: list[int] = []
    lat: list[float] = []
    lon: list[float] = []
    d: list[float] = []
    dist = 0.0
    for track in gpx.tracks:
        for segment in track.segments:
            for p in segment.points:
                if p.time is None:
                    continue
                if lat:
                    dist += haversine_m(lat[-1], lon[-1], p.latitude, p.longitude)
                t.append(round(p.time.timestamp()))
                lat.append(p.latitude)
                lon.append(p.longitude)
                d.append(dist)
    return Track(t, lat, lon, d)


def parse_track(path: Path) -> Track:
    """Read a ride file. Raises ValueError for unsupported or unreadable files."""
    if path.name.endswith(".gpx"):
        return _parse_gpx(path)
    raise ValueError(f"unsupported file format: {path.name}")


def write_cache(path: Path, track: Track) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"t": track.t, "lat": track.lat, "lon": track.lon, "d": track.d}
    with gzip.GzipFile(path, "wb", mtime=0) as fh:
        fh.write(json.dumps(payload, separators=(",", ":")).encode())


def read_cache(path: Path) -> Track:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        raw = json.load(fh)
    return Track(
        t=[int(x) for x in raw["t"]],
        lat=[float(x) for x in raw["lat"]],
        lon=[float(x) for x in raw["lon"]],
        d=[float(x) for x in raw["d"]],
    )
