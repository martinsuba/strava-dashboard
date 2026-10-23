"""Find segment efforts in a track.

T-002 scope: start and end gates only (a ride must pass within GATE_M of both, start before
end); elapsed time = time at the end gate - time at the start gate, so stops are included.
The path, length, direction and lap rules (REQ-004) are added in T-005.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sdash.tracks import EARTH_RADIUS_M, Track

GATE_M = 30.0


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


def _closest_on_leg(
    track: Track, i: int, lat0: float, lon0: float, cos_lat: float
) -> tuple[float, float, float]:
    """(distance m, interpolated t, interpolated d) of the point on leg i nearest to the gate."""
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
    return math.hypot(px, py), t, d


def approaches(track: Track, point: tuple[float, float], gate_m: float = GATE_M) -> list[Approach]:
    """One Approach (the closest point) per pass of the track through the gate circle."""
    lat0, lon0 = point
    cos_lat = math.cos(math.radians(lat0))
    found: list[Approach] = []
    best: Approach | None = None
    for i in range(len(track.t) - 1):
        dist, t, d = _closest_on_leg(track, i, lat0, lon0, cos_lat)
        if dist <= gate_m:
            if best is None or dist < best.dist_m:
                best = Approach(t, d, dist)
        elif best is not None:
            found.append(best)
            best = None
    if best is not None:
        found.append(best)
    return found


def find_efforts(
    track: Track,
    start: tuple[float, float],
    end: tuple[float, float],
    activity_id: str = "",
    gate_m: float = GATE_M,
) -> list[Effort]:
    """Efforts of `track` on the segment start -> end, in ride order."""
    ends = approaches(track, end, gate_m)
    efforts: list[Effort] = []
    last_end_t = -math.inf
    for s in approaches(track, start, gate_m):
        if s.t <= last_end_t:
            continue
        e = next((x for x in ends if x.t > s.t), None)
        if e is None:
            break
        efforts.append(
            Effort(
                activity_id=activity_id,
                start_t=round(s.t),
                elapsed_s=round(e.t - s.t),
                distance_m=round(e.d - s.d),
            )
        )
        last_end_t = e.t
    return efforts
