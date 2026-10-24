"""Ride files -> Track (time, position, cumulative distance), plus the per-ride cache.

The cache (cache/<id>.json.gz) also stores the source file's size and mtime; a ride is re-parsed
only when either changed.
"""

from __future__ import annotations

import gzip
import io
import json
import math
import os
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
        if not (math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180):
            return  # not a real position: skipped
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
                when = p.time if p.time.tzinfo is not None else p.time.replace(tzinfo=UTC)
                b.add(when.timestamp(), float(p.latitude), float(p.longitude))
    return b.track()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _refuse_dtd(data: bytes, name: str) -> None:
    """Refuse DOCTYPE/ENTITY declarations in any encoding (UTF-8, UTF-16/32, BOM or not)."""
    texts = [data.decode("utf-8", errors="ignore")]
    if data[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in data[:8]:
        for enc in ("utf-16", "utf-16-le", "utf-16-be", "utf-32"):
            texts.append(data.decode(enc, errors="ignore"))
    for text in texts:
        low = text.lower()
        if "<!doctype" in low or "<!entity" in low:
            raise ValueError(f"cannot read TCX {name}: DTD/entity declarations are not allowed")


def _strip_leading_junk(data: bytes) -> bytes:
    """Drop a BOM and any text/whitespace before the first '<' (expat wants `<?xml` at byte 0).

    UTF-16 with a BOM is handled in text form; UTF-32 and BOM-less UTF-16 are left as they are.
    """
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        if data[:4] == b"\xff\xfe\x00\x00":
            return data  # UTF-32 LE
        text = data.decode("utf-16", errors="replace")
        i = text.find("<")
        return text[i:].encode("utf-16") if i > 0 else data
    if data[:4] in (b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00") or b"\x00" in data[:8]:
        return data
    data = data.removeprefix(b"\xef\xbb\xbf")
    i = data.find(b"<")
    return data[i:] if i > 0 else data


def _parse_tcx(data: bytes, name: str) -> Track:
    _refuse_dtd(data, name)
    data = _strip_leading_junk(data)
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


def _number(x: object) -> float | None:
    if isinstance(x, bool) or not isinstance(x, int | float):
        return None
    return float(x)


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
                    lat = _number(frame.get_value("position_lat", fallback=None))
                    lon = _number(frame.get_value("position_long", fallback=None))
                    if not isinstance(ts, datetime) or lat is None or lon is None:
                        continue  # no (valid) time or position: skipped
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                    b.add(ts.timestamp(), lat * _SEMICIRCLE_TO_DEG, lon * _SEMICIRCLE_TO_DEG)
    except Exception as exc:  # fitdecode/struct/assert errors: any failure means a bad file
        raise ValueError(f"cannot read FIT {name}: {type(exc).__name__}: {exc}") from exc
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
    """Write atomically: a temp file in the same directory, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {"t": track.t, "lat": track.lat, "lon": track.lon, "d": track.d}
    if source is not None:
        payload["src_size"], payload["src_mtime_ns"] = source
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with gzip.GzipFile(tmp, "wb", mtime=0) as fh:
            fh.write(json.dumps(payload, separators=(",", ":")).encode())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _load_cache(path: Path) -> dict[str, object]:
    """The cache file's JSON object; ValueError when it is unreadable or not an object."""
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, EOFError, zlib.error, ValueError) as exc:  # incl. BadGzipFile, JSON errors
        raise ValueError(f"corrupt cache file {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"corrupt cache file {path.name}: not a JSON object")
    return raw


def _num_list(raw: dict[str, object], key: str) -> list[float]:
    v = raw.get(key)
    if not isinstance(v, list) or not all(
        isinstance(x, int | float) and not isinstance(x, bool) for x in v
    ):
        raise ValueError(f"field {key!r} is not a list of numbers")
    try:
        out = [float(x) for x in v]
    except OverflowError:  # an integer too large for a float
        raise ValueError(f"field {key!r} contains a number that is too large") from None
    if not all(math.isfinite(x) for x in out):
        raise ValueError(f"field {key!r} contains NaN or Infinity")
    return out


def _track_of(raw: dict[str, object]) -> Track:
    t, lat, lon, d = (_num_list(raw, k) for k in ("t", "lat", "lon", "d"))
    if not len(t) == len(lat) == len(lon) == len(d):
        raise ValueError("fields have different lengths")
    return Track(t=[int(x) for x in t], lat=lat, lon=lon, d=d)


def read_cache(path: Path) -> Track:
    """The cached track; ValueError (message names the file) when the cache is corrupt."""
    try:
        return _track_of(_load_cache(path))
    except ValueError as exc:
        if "corrupt cache" in str(exc):
            raise
        raise ValueError(f"corrupt cache file {path.name}: {exc}") from exc


def read_cache_if_fresh(path: Path, source: SourceStamp) -> Track | None:
    """The cached track when it was made from a file with this size and mtime, else None.

    A missing, unreadable, malformed or stamp-less cache file counts as stale.
    """
    try:
        raw = _load_cache(path)
        if (raw.get("src_size"), raw.get("src_mtime_ns")) != source:
            return None
        return _track_of(raw)
    except ValueError:
        return None
