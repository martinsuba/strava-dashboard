"""Gate matcher (REQ-004 basic: start/end gates, elapsed includes stops)."""

from __future__ import annotations

import math

from sdash.match import GATE_M, find_efforts
from sdash.tracks import Track, haversine_m

LAT0, LON0 = -47.0, -134.0
M_PER_DEG_LAT = 111_195.0


def lat_at(y_m: float) -> float:
    return LAT0 + y_m / M_PER_DEG_LAT


def lon_at(x_m: float) -> float:
    return LON0 + x_m / (M_PER_DEG_LAT * math.cos(math.radians(LAT0)))


def northbound(
    y0: float,
    y1: float,
    *,
    x: float = 0.0,
    t0: int = 1000,
    speed: float = 5.0,
    step: float = 20.0,
    stop_at: float | None = None,
    stop_s: int = 0,
) -> Track:
    """Ride north along x from y0 to y1, optionally standing still for stop_s at y=stop_at."""
    t, lat, lon, d = [], [], [], []
    y, now, dist = y0, float(t0), 0.0
    stopped = False
    while y <= y1 + 1e-9:
        t.append(round(now))
        lat.append(lat_at(y))
        lon.append(lon_at(x))
        d.append(dist)
        if stop_at is not None and not stopped and y >= stop_at:
            stopped = True
            now += stop_s
            t.append(round(now))
            lat.append(lat_at(y))
            lon.append(lon_at(x))
            d.append(dist)
        y += step
        now += step / speed
        dist += step
    return Track(t=t, lat=lat, lon=lon, d=d)


START = (lat_at(0), lon_at(0))
END = (lat_at(2000), lon_at(0))


def test_gate_constant() -> None:
    assert GATE_M == 30.0


def test_effort_found_with_elapsed_and_distance() -> None:
    (e,) = find_efforts(northbound(-500, 2500), START, END)
    assert abs(e.elapsed_s - 400) <= 1
    assert abs(e.start_t - (1000 + 100)) <= 1
    assert abs(e.distance_m - 2000) <= 25


def test_elapsed_includes_stops() -> None:
    (e,) = find_efforts(northbound(-500, 2500, stop_at=1500, stop_s=60), START, END)
    assert abs(e.elapsed_s - 460) <= 1


def test_ride_that_misses_the_start_gate_has_no_effort() -> None:
    assert find_efforts(northbound(-500, 2500, x=45), START, END) == []


def test_ride_inside_the_gate_offset_is_found() -> None:
    assert len(find_efforts(northbound(-500, 2500, x=20), START, END)) == 1


def test_ride_that_never_reaches_the_end_has_no_effort() -> None:
    assert find_efforts(northbound(-500, 1500), START, END) == []


def test_end_before_start_has_no_effort() -> None:
    southbound = northbound(-500, 2500)
    southbound = Track(
        t=southbound.t,
        lat=list(reversed(southbound.lat)),
        lon=southbound.lon,
        d=southbound.d,
    )
    assert find_efforts(southbound, START, END) == []


def test_track_with_fewer_than_two_points() -> None:
    assert find_efforts(Track(t=[1], lat=[LAT0], lon=[LON0], d=[0.0]), START, END) == []


def _laps(*laps: Track) -> Track:
    t, lat, lon, d = [], [], [], []
    for lap in laps:
        off_t = (t[-1] + 10 - lap.t[0]) if t else 0
        off_d = d[-1] if d else 0.0
        t += [x + off_t for x in lap.t]
        lat += lap.lat
        lon += lap.lon
        d += [x + off_d for x in lap.d]
    return Track(t, lat, lon, d)


def test_two_laps_give_two_efforts() -> None:
    lap = northbound(-500, 2500)
    ride_back = northbound(-500, 2500, x=200)  # a parallel road, outside both gates
    back = Track(t=ride_back.t, lat=list(reversed(ride_back.lat)), lon=ride_back.lon, d=ride_back.d)
    efforts = find_efforts(_laps(lap, back, lap), START, END)
    assert len(efforts) == 2
    assert efforts[0].start_t < efforts[1].start_t
    assert all(abs(e.elapsed_s - 400) <= 1 for e in efforts)


def test_start_equal_to_end_out_and_back_is_not_zero_length() -> None:
    out = northbound(-500, 1000)
    back = Track(t=out.t, lat=list(reversed(out.lat)), lon=out.lon, d=out.d)
    track = _laps(out, back)
    (e,) = find_efforts(track, START, START)
    assert e.elapsed_s > 100 and e.distance_m > 500


def test_sparse_legs_still_find_the_effort() -> None:
    (e,) = find_efforts(northbound(-500, 2500, step=50.0, speed=5.0), START, END)
    assert abs(e.elapsed_s - 400) <= 2


def test_one_pass_is_not_used_as_both_start_and_end() -> None:
    # gates 20 m apart side by side; one ride passes both at the same moment
    east_gate = (lat_at(0), lon_at(20))
    assert find_efforts(northbound(-500, 500, x=10), (lat_at(0), lon_at(0)), east_gate) == []


def test_helper_geometry_sanity() -> None:
    assert abs(haversine_m(*START, *END) - 2000) < 5
