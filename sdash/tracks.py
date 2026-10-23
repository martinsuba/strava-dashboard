"""Ride files -> Track (time, position, cumulative distance), plus the per-ride cache.

The cache (cache/<id>.json.gz) also stores the source file's size and mtime; a ride is re-parsed
only when either changed.
"""

from __future__ import annotations

import gzip
import io
import json
import math
import struct
import warnings
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

import fitdecode
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


MAX_DECOMPRESSED_BYTES = 200 * 1024 * 1024  # a ride file is untrusted input: cap gunzip output


def _read_bytes(path: Path) -> bytes:
    """File content; .gz is decompressed with a size cap (ValueError when exceeded)."""
    if not path.name.endswith(".gz"):
        if path.stat().st_size > MAX_DECOMPRESSED_BYTES:
            raise ValueError(f"{path.name}: file larger than {MAX_DECOMPRESSED_BYTES} bytes")
        return path.read_bytes()
    try:
        with gzip.open(path, "rb") as fh:
            data = fh.read(MAX_DECOMPRESSED_BYTES + 1)
    except (EOFError, gzip.BadGzipFile, zlib.error) as exc:
        raise ValueError(f"{path.name}: corrupt gzip data: {exc}") from exc
    if len(data) > MAX_DECOMPRESSED_BYTES:
        raise ValueError(f"{path.name}: decompressed size exceeds {MAX_DECOMPRESSED_BYTES} bytes")
    return data


class _Builder:
    """Collects (time, lat, lon) samples and derives the cumulative distance."""

    def __init__(self) -> None:
        self.t: list[int] = []
        self.lat: list[float] = []
        self.lon: list[float] = []
        self.d: list[float] = []

    def add(self, t: float, lat: float, lon: float) -> None:
        dist = self.d[-1] if self.d else 0.0
        if self.lat:
            dist += haversine_m(self.lat[-1], self.lon[-1], lat, lon)
        self.t.append(round(t))
        self.lat.append(lat)
        self.lon.append(lon)
        self.d.append(dist)

    def track(self) -> Track:
        return Track(self.t, self.lat, self.lon, self.d)


def _parse_gpx(data: bytes, name: str) -> Track:
    try:
        gpx = gpxpy.parse(data.decode("utf-8"))
    except Exception as exc:  # gpxpy raises several exception types for bad input
        raise ValueError(f"cannot read GPX {name}: {exc}") from exc
    b = _Builder()
    for track in gpx.tracks:
        for segment in track.segments:
            for p in segment.points:
                if p.time is None:
                    continue
                b.add(p.time.timestamp(), p.latitude, p.longitude)
    return b.track()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_tcx(data: bytes, name: str) -> Track:
    if b"<!DOCTYPE" in data[:4096].upper() or b"<!ENTITY" in data.upper():
        raise ValueError(f"cannot read TCX {name}: DTD/entity declarations are not allowed")
    b = _Builder()
    try:
        for _, el in ElementTree.iterparse(io.BytesIO(data)):
            if _local(el.tag) != "Trackpoint":
                continue
            fields = {_local(c.tag): c for c in el.iter()}
            el.clear()
            time_el = fields.get("Time")
            lat_el = fields.get("LatitudeDegrees")
            lon_el = fields.get("LongitudeDegrees")
            if time_el is None or lat_el is None or lon_el is None:
                continue  # no position (or no time): skipped
            when = datetime.fromisoformat((time_el.text or "").strip().replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            b.add(
                when.timestamp(),
                float((lat_el.text or "").strip()),
                float((lon_el.text or "").strip()),
            )
    except (ElementTree.ParseError, ValueError) as exc:
        raise ValueError(f"cannot read TCX {name}: {exc}") from exc
    return b.track()


_SEMICIRCLE_TO_DEG = 180.0 / 2**31


def _parse_fit(data: bytes, name: str) -> Track:
    b = _Builder()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # fitdecode warns about developer fields; harmless
            with fitdecode.FitReader(io.BytesIO(data)) as reader:
                for frame in reader:
                    if not isinstance(frame, fitdecode.FitDataMessage) or frame.name != "record":
                        continue
                    ts = frame.get_value("timestamp", fallback=None)
                    lat = frame.get_value("position_lat", fallback=None)
                    lon = frame.get_value("position_long", fallback=None)
                    if ts is None or lat is None or lon is None:
                        continue
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                    b.add(ts.timestamp(), lat * _SEMICIRCLE_TO_DEG, lon * _SEMICIRCLE_TO_DEG)
    except (fitdecode.FitError, struct.error, ValueError, OverflowError, EOFError) as exc:
        raise ValueError(f"cannot read FIT {name}: {exc}") from exc
    return b.track()


def parse_track(path: Path) -> Track:
    """Read a ride file (.fit/.gpx/.tcx, each optionally .gz).

    Records without a position are skipped. Raises ValueError for unsupported or unreadable files.
    """
    kind = path.name.removesuffix(".gz").rsplit(".", 1)[-1].lower()
    parsers = {"gpx": _parse_gpx, "fit": _parse_fit, "tcx": _parse_tcx}
    if kind not in parsers:
        raise ValueError(f"unsupported file format: {path.name}")
    return parsers[kind](_read_bytes(path), path.name)


SourceStamp = tuple[int, int]  # (size in bytes, mtime in ns) of the ride file


def source_stamp(path: Path) -> SourceStamp:
    st = path.stat()
    return st.st_size, st.st_mtime_ns


def write_cache(path: Path, track: Track, source: SourceStamp | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {"t": track.t, "lat": track.lat, "lon": track.lon, "d": track.d}
    if source is not None:
        payload["src_size"], payload["src_mtime_ns"] = source
    with gzip.GzipFile(path, "wb", mtime=0) as fh:
        fh.write(json.dumps(payload, separators=(",", ":")).encode())


def _load_cache(path: Path) -> dict[str, object]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        raw: dict[str, object] = json.load(fh)
    return raw


def _track_of(raw: dict[str, object]) -> Track:
    return Track(
        t=[int(x) for x in raw["t"]],  # type: ignore[attr-defined]
        lat=[float(x) for x in raw["lat"]],  # type: ignore[attr-defined]
        lon=[float(x) for x in raw["lon"]],  # type: ignore[attr-defined]
        d=[float(x) for x in raw["d"]],  # type: ignore[attr-defined]
    )


def read_cache(path: Path) -> Track:
    return _track_of(_load_cache(path))


def read_cache_if_fresh(path: Path, source: SourceStamp) -> Track | None:
    """The cached track when it was made from a file with this size and mtime, else None.

    A missing, unreadable or stamp-less cache file counts as stale.
    """
    try:
        raw = _load_cache(path)
        if (raw.get("src_size"), raw.get("src_mtime_ns")) != source:
            return None
        return _track_of(raw)
    except (OSError, ValueError, KeyError, TypeError, EOFError, zlib.error):
        return None
