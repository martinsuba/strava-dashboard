"""Synthetic ride scenarios for the REQ-004 matching rules (and reused elsewhere).

Frame: metres around _synth.SYNTH_ORIGIN, x = east, y = north. The segment "Synthetic climb" runs
straight north from A = (0, 0) to B = (0, 2000) (2.0 km). Riders move at 5 m/s, so riding the
segment without stopping takes 400 s.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from _synth import Activity, Point, Ride, build_track, xy_to_latlon

SEGMENT_NAME = "Synthetic climb"
REF_ID = "1000000001"
A = (0.0, 0.0)
B = (0.0, 2000.0)
SEG_LEN = 2000.0
SPEED = 5.0
DAY0 = datetime(2026, 5, 1, 8, 0, 0, tzinfo=UTC)


def latlon(p: tuple[float, float]) -> list[float]:
    lat, lon = xy_to_latlon(*p)
    return [round(lat, 6), round(lon, 6)]


def segment(
    name: str = SEGMENT_NAME,
    ref: str = REF_ID,
    start: tuple[float, float] = A,
    end: tuple[float, float] = B,
) -> dict[str, Any]:
    return {"name": name, "ref_activity": ref, "start": latlon(start), "end": latlon(end)}


def ride(
    activity_id: str,
    waypoints: list[tuple[float, float]],
    *,
    day: int = 0,
    name: str | None = None,
    type: str = "Ride",
    fmt: str = "gpx",
    **track_kw: Any,
) -> Ride:
    start = DAY0 + timedelta(days=day)
    pts: list[Point] = build_track(
        waypoints, start=start, speed_mps=track_kw.pop("speed", SPEED), **track_kw
    )
    act = Activity(
        id=activity_id, date=start, name=name or f"Synthetic ride {activity_id[-3:]}", type=type
    )
    return Ride(act, pts, fmt=fmt)


def reference_ride(**kw: Any) -> Ride:
    """The segment's reference activity: exactly A -> B."""
    return ride(REF_ID, [A, B], name="Synthetic reference ride", **kw)


# Scenario rides (activity 1000000002 unless noted). Lead-in/out of 500 m beyond the gates.
def normal_with_stop() -> Ride:
    """A -> B with a 60 s stop halfway: elapsed = 400 + 60 = 460 s."""
    return ride("1000000002", [(0, -500), (0, 2500)], day=1, stops=[(1500.0, 60)])


EXPECTED_NORMAL_ELAPSED = 460


def detour() -> Ride:
    """Passes A and B, but via (150, 1000): 2022 m (within +-10 %), mid reference points ~148 m away."""
    return ride("1000000002", [(0, -500), A, (150, 1000), B, (0, 2500)], day=1)


def loop_detour() -> Ride:
    """Passes A and B and stays on the reference path, but rides a 150 m square loop halfway and
    returns to the segment: 2600 m ridden (+30 %), so only the +-10 % length rule rejects it."""
    loop = [(0, 1000), (150, 1000), (150, 1150), (0, 1150), (0, 1000)]
    return ride("1000000002", [(0, -500), A, *loop, B, (0, 2500)], day=1)


def reverse() -> Ride:
    return ride("1000000002", [(0, 2500), (0, -500)], day=1)


def two_laps() -> Ride:
    """A -> B, back south on a parallel road 500 m east, A -> B again."""
    return ride(
        "1000000002",
        [(0, -500), A, B, (500, 2000), (500, 0), A, B, (0, 2500)],
        day=1,
    )


def sparse() -> Ride:
    """Smart recording: one point per 50 m (every 10 s); nearest points 20 m from the gates."""
    return ride("1000000002", [(0, -500), (0, 2500)], day=1, spacing_m=50.0, first_offset_m=20.0)


# Out-and-back: start == end == A, turn at C = (0, 1000); reference A -> C -> A (2000 m, 400 s).
C = (0.0, 1000.0)


def out_and_back_reference() -> Ride:
    return ride(REF_ID, [A, C, A], name="Synthetic out-and-back reference")


def out_and_back_ride() -> Ride:
    return ride("1000000002", [(0, -500), A, C, A, (0, -500)], day=1)


def hike_reference() -> Ride:
    """A non-ride reference activity (Hike, walking pace)."""
    return ride(REF_ID, [A, B], name="Synthetic hike", type="Hike", speed=1.2)
