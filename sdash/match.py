"""Find segment efforts in a track (REQ-004).

An effort is a start pass within GATE_M of the segment start, a later end pass within GATE_M of
the segment end, a ridden distance between them within +-LENGTH_TOLERANCE of the reference
length, and every reference point (the reference track sampled every ~REF_SPACING_M between its own
start and end passes) within PATH_M of the ride path between the two passes. The distance to the
ride path is the distance to the nearest ride *segment*, so sparse tracks still match. Elapsed time
= time at the end pass - time at the start pass, so stops are included.

When a (start, end) pair fails, the next end pass is tried for the same start and then the next
start pass, so a failed pair never consumes a pass that a later pair needs. Pairs ridden over less than 2 x GATE_M are skipped (gate jitter). Efforts never overlap.
Without a `Reference`, only the gates and the order are checked.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

from sdash.tracks import EARTH_RADIUS_M, Track

GATE_M = 30.0
PATH_M = 60.0
LENGTH_TOLERANCE = 0.10
REF_SPACING_M = 50.0
_M_PER_DEG = EARTH_RADIUS_M * math.pi / 180


@dataclass(frozen=True)
class Effort:
    activity_id: str
    start_t: int  # epoch seconds at the start gate
    elapsed_s: int
    distance_m: int  # ridden distance between the gates


@dataclass(frozen=True)
class Approach:
    """Closest approach of a track to a gate point during one pass."""

    t: float
    d: float
    dist_m: float
    leg: int = 0  # the closest point lies on the leg between track points leg and leg + 1
    u: float = 0.0  # position along that leg, 0..1


def _closest_on_leg(
    track: Track, i: int, lat0: float, lon0: float, cos_lat: float
) -> tuple[float, float, float, float]:
    """(distance m, t, d, u) of the point on leg i nearest to the gate."""
    k = EARTH_RADIUS_M * math.pi / 180
    ax = (track.lon[i] - lon0) * cos_lat * k
    ay = (track.lat[i] - lat0) * k
    bx = (track.lon[i + 1] - lon0) * cos_lat * k
    by = (track.lat[i + 1] - lat0) * k
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    u = 0.0 if length2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length2))
    px, py = ax + u * dx, ay + u * dy
    t = track.t[i] + u * (track.t[i + 1] - track.t[i])
    d = track.d[i] + u * (track.d[i + 1] - track.d[i])
    return math.hypot(px, py), t, d, u


def approaches(track: Track, point: tuple[float, float], gate_m: float = GATE_M) -> list[Approach]:
    """One Approach (the closest point) per pass of the track through the gate circle."""
    lat0, lon0 = point
    cos_lat = math.cos(math.radians(lat0))
    found: list[Approach] = []
    best: Approach | None = None
    for i in range(len(track.t) - 1):
        dist, t, d, u = _closest_on_leg(track, i, lat0, lon0, cos_lat)
        if dist <= gate_m:
            if best is None or dist < best.dist_m:
                best = Approach(t, d, dist, i, u)
        elif best is not None:
            found.append(best)
            best = None
    if best is not None:
        found.append(best)
    return found


@dataclass(frozen=True)
class Reference:
    """What a segment looks like: ridden length and the points a ride must stay close to."""

    length_m: float
    points: tuple[tuple[float, float], ...]  # (lat, lon), every ~REF_SPACING_M, both ends included


def point_segment_distance_m(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    """Distance from point P to the segment AB (planar metres)."""
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    u = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(px - (ax + u * dx), py - (ay + u * dy))


def distance_to_polyline_m(
    px: float, py: float, xs: list[float], ys: list[float], stop_below: float = -1.0
) -> float:
    """Distance from P to the polyline through (xs, ys); returns early once <= `stop_below`."""
    if len(xs) == 1:
        return math.hypot(px - xs[0], py - ys[0])
    best = math.inf
    for i in range(len(xs) - 1):
        dist = point_segment_distance_m(px, py, xs[i], ys[i], xs[i + 1], ys[i + 1])
        if dist < best:
            best = dist
            if best <= stop_below:
                break
    return best


def _position(track: Track, a: Approach) -> tuple[float, float]:
    i = a.leg
    j = min(i + 1, len(track.t) - 1)
    return (
        track.lat[i] + a.u * (track.lat[j] - track.lat[i]),
        track.lon[i] + a.u * (track.lon[j] - track.lon[i]),
    )


def _first_pair(
    track: Track,
    start: tuple[float, float],
    end: tuple[float, float],
    gate_m: float,
) -> tuple[Approach, Approach] | None:
    """First end pass with a start pass before it, paired with the latest such start pass.

    Pairs ridden over less than 2 x gate are skipped (a track that jitters in and out of the gate
    is not a segment): the next end pass is tried.
    """
    starts = approaches(track, start, gate_m)
    for e in approaches(track, end, gate_m):
        before = [x for x in starts if x.t < e.t and e.d - x.d >= 2 * gate_m]
        if before:
            return before[-1], e
    return None


def reference_from(
    track: Track,
    start: tuple[float, float],
    end: tuple[float, float],
    gate_m: float = GATE_M,
) -> Reference | None:
    """Length and sample points of the first start->end pass of `track`; None if it has none."""
    pair = _first_pair(track, start, end, gate_m)
    if pair is None:
        return None
    s, e = pair
    line = [(s.d, *_position(track, s))]
    line += [(track.d[k], track.lat[k], track.lon[k]) for k in range(s.leg + 1, e.leg + 1)]
    line.append((e.d, *_position(track, e)))
    length = e.d - s.d
    points: list[tuple[float, float]] = [(line[0][1], line[0][2])]
    target = s.d + REF_SPACING_M
    for (d0, la0, lo0), (d1, la1, lo1) in itertools.pairwise(line):
        while target < d1 and target < e.d:
            f = 0.0 if d1 == d0 else (target - d0) / (d1 - d0)
            points.append((la0 + f * (la1 - la0), lo0 + f * (lo1 - lo0)))
            target += REF_SPACING_M
    points.append((line[-1][1], line[-1][2]))
    return Reference(length, tuple(points))


@dataclass(frozen=True)
class _Box:
    lat_lo: float
    lat_hi: float
    lon_lo: float
    lon_hi: float

    def grown(self, metres: float, lat: float) -> _Box:
        dlat = metres / _M_PER_DEG
        dlon = metres / (_M_PER_DEG * max(0.01, math.cos(math.radians(lat))))
        return _Box(self.lat_lo - dlat, self.lat_hi + dlat, self.lon_lo - dlon, self.lon_hi + dlon)

    def contains(self, lat: float, lon: float) -> bool:
        return self.lat_lo <= lat <= self.lat_hi and self.lon_lo <= lon <= self.lon_hi


def _path_ok(track: Track, s: Approach, e: Approach, ref: Reference) -> bool:
    """Every reference point is within PATH_M of the ride path between the passes s and e."""
    lat0, lon0 = ref.points[0]
    cos_lat = math.cos(math.radians(lat0))
    la_s, lo_s = _position(track, s)
    la_e, lo_e = _position(track, e)
    lats = [la_s, *track.lat[s.leg + 1 : e.leg + 1], la_e]
    lons = [lo_s, *track.lon[s.leg + 1 : e.leg + 1], lo_e]
    xs = [(lo - lon0) * cos_lat * _M_PER_DEG for lo in lons]
    ys = [(la - lat0) * _M_PER_DEG for la in lats]
    cursor = 0  # reference points are ordered along the ride: look near the last hit first
    last = len(xs) - 1
    for la, lo in ref.points:
        px, py = (lo - lon0) * cos_lat * _M_PER_DEG, (la - lat0) * _M_PER_DEG
        for i in itertools.chain(range(cursor, last), range(cursor)):
            if point_segment_distance_m(px, py, xs[i], ys[i], xs[i + 1], ys[i + 1]) <= PATH_M:
                cursor = i
                break
        else:
            return False
    return True


def find_efforts(
    track: Track,
    start: tuple[float, float],
    end: tuple[float, float],
    activity_id: str = "",
    gate_m: float = GATE_M,
    reference: Reference | None = None,
) -> list[Effort]:
    """Efforts of `track` on the segment start -> end, in ride order, never overlapping."""
    if len(track.t) < 2:
        return []
    box = _Box(min(track.lat), max(track.lat), min(track.lon), max(track.lon))
    for gate in (start, end):
        if not box.grown(gate_m, gate[0]).contains(*gate):
            return []
    if reference is not None:
        wide = box.grown(PATH_M, reference.points[0][0])
        if not all(wide.contains(la, lo) for la, lo in reference.points):
            return []
    ends = approaches(track, end, gate_m)
    efforts: list[Effort] = []
    last_end_t = -math.inf
    for s in approaches(track, start, gate_m):
        if s.t < last_end_t:
            continue
        for e in ends:
            if e.t <= s.t or e.d - s.d < 2 * gate_m:
                continue  # not after the start, or a gate pair too short to be a segment
            if reference is not None:
                ridden = e.d - s.d
                if ridden > reference.length_m * (1 + LENGTH_TOLERANCE):
                    break  # later end passes are only farther away
                if abs(ridden - reference.length_m) > reference.length_m * LENGTH_TOLERANCE:
                    continue
                if not _path_ok(track, s, e, reference):
                    continue
            efforts.append(
                Effort(
                    activity_id=activity_id,
                    start_t=round(s.t),
                    elapsed_s=round(e.t - s.t),
                    distance_m=round(e.d - s.d),
                )
            )
            last_end_t = e.t
            break
    return efforts
