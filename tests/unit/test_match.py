"""Gate matcher (REQ-004 basic: start/end gates, elapsed includes stops)."""

from __future__ import annotations

import itertools
import math

from sdash.match import (
    _M_PER_DEG,
    GATE_M,
    PATH_M,
    Approach,
    Reference,
    _Box,
    _closest_on_leg,
    _first_pair,
    _path_ok,
    _position,
    approaches,
    distance_to_polyline_m,
    find_efforts,
    point_segment_distance_m,
    reference_from,
)
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


# ---- T-005: full REQ-004 rules (length, path, direction, laps, bounding box) ----


def walk(waypoints: list[tuple[float, float]], *, step: float = 20.0, t0: int = 1000) -> Track:
    """Ride through (x, y) waypoints in metres at 5 m/s, a point every `step` metres."""
    t, lat, lon, d = [], [], [], []
    now, dist = float(t0), 0.0
    for (x0, y0), (x1, y1) in itertools.pairwise(waypoints):
        length = math.hypot(x1 - x0, y1 - y0)
        n = max(1, round(length / step))
        for k in range(n):
            f = k / n
            t.append(round(now + f * length / 5.0))
            lat.append(lat_at(y0 + f * (y1 - y0)))
            lon.append(lon_at(x0 + f * (x1 - x0)))
            d.append(dist + f * length)
        now += length / 5.0
        dist += length
    t.append(round(now))
    lat.append(lat_at(waypoints[-1][1]))
    lon.append(lon_at(waypoints[-1][0]))
    d.append(dist)
    return Track(t, lat, lon, d)


def ref_ab() -> Reference:
    ref = reference_from(walk([(0, 0), (0, 2000)]), START, END)
    assert ref is not None
    return ref


def efforts_of(track: Track) -> list:
    return find_efforts(track, START, END, "x", reference=ref_ab())


def test_path_limit_constant() -> None:
    assert PATH_M == 60.0


def test_point_segment_distance() -> None:
    assert point_segment_distance_m(5, 5, 0, 0, 10, 0) == 5  # beside the segment
    assert point_segment_distance_m(-3, 4, 0, 0, 10, 0) == 5  # beyond the A end
    assert point_segment_distance_m(13, 4, 0, 0, 10, 0) == 5  # beyond the B end
    assert point_segment_distance_m(3, 4, 0, 0, 0, 0) == 5  # degenerate segment


def test_distance_to_polyline_uses_segments_not_points() -> None:
    xs, ys = [0.0, 1000.0], [0.0, 0.0]  # two points 1 km apart
    assert distance_to_polyline_m(500, 10, xs, ys) == 10


def test_reference_from_length_and_points() -> None:
    ref = ref_ab()
    assert abs(ref.length_m - 2000) <= 2
    assert 38 <= len(ref.points) <= 45  # every ~50 m, including both ends
    assert reference_from(walk([(0, 0), (0, 1000)]), START, END) is None


def test_reference_ride_matches_itself() -> None:
    (e,) = efforts_of(walk([(0, -500), (0, 2500)]))
    assert abs(e.elapsed_s - 400) <= 1


def test_path_59m_off_matches_and_61m_off_does_not() -> None:
    # the detour apex is 59 / 61 m beside the road; the nearest reference points sit ~25 m from
    # the apex projection, so the polyline distance (not the vertex distance) decides
    for apex, expected in ((59, 1), (61, 0)):
        track = walk([(0, -500), (0, 0), (apex, 1000), (0, 2000), (0, 2500)])
        found = efforts_of(track)
        assert len(found) == expected, (apex, found)


def test_length_within_9_percent_matches_beyond_11_percent_does_not() -> None:
    # a spur out and back on the line adds length without leaving the reference path
    def with_spur(extra: float) -> Track:
        return walk([(0, -500), (0, 0), (0, 1000), (0, 1000 - extra), (0, 1000), (0, 2000)])

    assert len(efforts_of(with_spur(90))) == 1  # +180 m = +9 %
    assert efforts_of(with_spur(110)) == []  # +220 m = +11 %


def test_too_short_ride_between_gates_does_not_match() -> None:
    # gates are 2000 m apart on the reference; a shortcut ride covers ~1800 m (-10 % limit 1800)
    short_end = (lat_at(1700), lon_at(0))
    ref = reference_from(walk([(0, 0), (0, 2000)]), START, END)
    assert ref is not None
    assert find_efforts(walk([(0, -500), (0, 1700)]), START, short_end, reference=ref) == []


def test_reversed_ride_has_no_effort_even_with_reference() -> None:
    assert efforts_of(walk([(0, 2500), (0, -500)])) == []


def test_lap_pairing_a_b_back_a_b_gives_two_correct_efforts() -> None:
    track = walk([(0, -500), (0, 2000), (0, 0), (0, 2500)])  # A->B, B->A same road, A->B
    found = efforts_of(track)
    assert len(found) == 2, found
    for e in found:
        assert abs(e.elapsed_s - 400) <= 2
        assert abs(e.distance_m - 2000) <= 25
    assert found[0].start_t + found[0].elapsed_s <= found[1].start_t


def test_lap_pairing_without_reference_is_still_per_pass() -> None:
    track = walk([(0, -500), (0, 2000), (0, 0), (0, 2500)])
    found = find_efforts(track, START, END, "x")
    assert len(found) == 2
    assert all(abs(e.elapsed_s - 400) <= 2 for e in found)


def test_failed_pair_does_not_consume_the_end_pass() -> None:
    # first start pass leads into a 3 km loop before B (fails length); the second start pass is fine
    loop = [(0, -500), (0, 0), (600, 0), (600, 800), (0, 800), (0, 0), (0, 2500)]
    found = efforts_of(walk(loop))
    assert len(found) == 1
    assert abs(found[0].elapsed_s - 400) <= 2


def test_efforts_never_overlap_in_time() -> None:
    track = walk([(0, -500), (0, 2000), (0, 0), (0, 2000), (0, 0), (0, 2500)])
    found = efforts_of(track)
    assert len(found) == 3
    for a, b in itertools.pairwise(found):
        assert a.start_t + a.elapsed_s <= b.start_t


def test_out_and_back_segment_needs_the_full_distance() -> None:
    c = (0, 1000)
    ref = reference_from(walk([(0, 0), c, (0, 0)]), START, START)
    assert ref is not None and abs(ref.length_m - 2000) <= 2
    good = find_efforts(
        walk([(0, -500), (0, 0), c, (0, 0), (0, -500)]), START, START, "x", reference=ref
    )
    assert len(good) == 1 and good[0].distance_m > 1900
    # turns at 500 m: only 1000 m ridden, and the reference apex is 500 m away
    short = find_efforts(
        walk([(0, -500), (0, 0), (0, 500), (0, 0), (0, -500)]), START, START, "x", reference=ref
    )
    assert short == []


def test_sparse_ride_matches_with_polyline_distance() -> None:
    # one point per 50 m, with a 25 m lateral jog so a vertex-only check would see > 25 m anyway;
    # every reference point must still be within 60 m of the polyline
    track = walk([(0, -500), (30, 1000), (0, 2500)], step=50.0)
    assert len(efforts_of(track)) == 1


def test_sparse_ride_with_very_long_legs_still_matches() -> None:
    track = Track(
        t=[1000, 1100, 1500, 1600],
        lat=[lat_at(y) for y in (-500, 0, 2000, 2500)],
        lon=[lon_at(0)] * 4,
        d=[0.0, 500.0, 2500.0, 3000.0],
    )
    (e,) = efforts_of(track)
    assert e.elapsed_s == 400


def test_gate_exactly_at_the_30m_boundary() -> None:
    inside = find_efforts(walk([(29.5, -500), (29.5, 2500)]), START, END, "x", reference=ref_ab())
    outside = find_efforts(walk([(30.5, -500), (30.5, 2500)]), START, END, "x", reference=ref_ab())
    assert len(inside) == 1
    assert outside == []


def test_bounding_box_prefilter_keeps_true_matches_and_drops_far_rides() -> None:
    near = walk([(0, -500), (0, 2500)])
    assert len(efforts_of(near)) == 1
    far = walk([(5000, -500), (5000, 2500)])
    assert efforts_of(far) == []
    # ride bbox only just contains the reference path (well inside the 60 m margin)
    narrow = walk([(55, -25), (55, 1000), (55, 2025)])
    assert len(efforts_of(narrow)) == 0  # gates 55 m away
    edge = walk([(25, -25), (25, 1000), (25, 2025)])
    assert len(efforts_of(edge)) == 1


def test_consecutive_loop_laps_when_start_equals_end_give_every_lap() -> None:
    lap = [(0, 0), (500, 0), (500, 500), (0, 500)]
    ref = reference_from(walk([*lap, (0, 0)]), START, START)
    assert ref is not None and abs(ref.length_m - 2000) <= 5
    found = find_efforts(walk([*lap, *lap, *lap, (0, 0)]), START, START, "x", reference=ref)
    assert len(found) == 3, found
    for e in found:
        assert abs(e.elapsed_s - 400) <= 3 and abs(e.distance_m - 2000) <= 25


def test_hill_repeats_turning_inside_the_gate_give_every_repeat() -> None:
    up_down = [(0, 0), (0, 1000)]
    ref = reference_from(walk([*up_down, (0, 0)]), START, START)
    assert ref is not None
    found = find_efforts(
        walk([*up_down, *up_down, *up_down, (0, 0)]), START, START, "x", reference=ref
    )
    assert len(found) == 3, found
    assert all(abs(e.elapsed_s - 400) <= 3 for e in found)


def test_reference_passing_the_start_gate_twice_uses_the_tightest_pair() -> None:
    loop = [(0, 0), (800, 0), (800, 800), (0, 800), (0, 0)]  # 3200 m back through A
    ref = reference_from(walk([*loop, (0, 2000)]), START, END)
    assert ref is not None
    assert abs(ref.length_m - 2000) <= 25
    assert len(find_efforts(walk([(0, -500), (0, 2500)]), START, END, "x", reference=ref)) == 1


# --- T-013: jitter at the gate must not produce a tiny out-and-back pair -------------------------


def _path(xy: list[tuple[float, float]], *, t0: int = 1000, step_s: int = 2) -> Track:
    """A track through the given (x east, y north) points in metres, one point per `step_s`."""
    d = [0.0]
    for (xa, ya), (xb, yb) in itertools.pairwise(xy):
        d.append(d[-1] + math.hypot(xb - xa, yb - ya))
    return Track(
        t=[t0 + i * step_s for i in range(len(xy))],
        lat=[lat_at(y) for _, y in xy],
        lon=[lon_at(x) for x, _ in xy],
        d=d,
    )


# Starts on the gate point, steps out of the 30 m gate and straight back in (a second pass 34 m
# further on), then rides 1 km north on x = 29 and back on x = 60, which passes the gate a third time.
JITTER = [(0, 0), (31, 0), (31, 1), (29, 0)]
OUT_AND_BACK = [*JITTER, (29, 1000), (60, 1000), (60, 10), (29, 0)]


def test_reference_skips_gate_pairs_shorter_than_two_gates() -> None:
    ref = reference_from(_path(OUT_AND_BACK), START, START)
    assert ref is not None
    assert 2000 <= ref.length_m <= 2100, ref.length_m


def test_reference_without_any_long_enough_pair_is_none() -> None:
    assert reference_from(_path(JITTER), START, START) is None


def test_ride_with_jitter_at_the_gate_gets_one_full_effort() -> None:
    efforts = find_efforts(_path([*OUT_AND_BACK, (29, -200)]), START, START, "r")
    assert len(efforts) == 1, efforts
    assert efforts[0].distance_m > 2000


def test_a_start_end_pair_shorter_than_two_gates_is_never_an_effort() -> None:
    near_end = (lat_at(40), lon_at(0))  # 40 m north of the start: ridden 40 m < 2 x gate
    assert find_efforts(northbound(-500, 500), START, near_end) == []


# --- T-018: targeted tests for mutation survivors ------------------------------------------------


def test_point_segment_distance_uses_both_coordinates_and_projection() -> None:
    # Offset segment, point beside its middle: only the true projection gives exactly 3.
    assert point_segment_distance_m(5, 7, 2, 4, 8, 4) == 3
    # Slanted segment (3-4-5): the foot of the perpendicular is inside the segment.
    assert math.isclose(
        point_segment_distance_m(0, 5, 0, 0, 10, 10), 5 / math.sqrt(2) * 1.0, abs_tol=1e-9
    )
    # Beyond B on a segment that does not start at the origin: the distance is to B.
    assert point_segment_distance_m(14, 7, 2, 3, 10, 3) == math.hypot(4, 4)
    # Beyond A on a segment that does not start at the origin: the distance is to A.
    assert point_segment_distance_m(-1, 7, 2, 3, 10, 3) == math.hypot(3, 4)
    # Degenerate segment away from the origin.
    assert point_segment_distance_m(6, 8, 3, 4, 3, 4) == 5
    # A vertical segment (dy only).
    assert point_segment_distance_m(4, 1, 1, 0, 1, 10) == 3


def test_distance_to_polyline_single_point() -> None:
    assert distance_to_polyline_m(4, 6, [1.0], [2.0]) == 5


def test_distance_to_polyline_takes_the_nearest_segment() -> None:
    # Staircase: distances from (15, 0) are 10.3 (top), 5.4 (vertical riser), 2 (low step).
    xs, ys = [0.0, 10.0, 10.0, 20.0], [9.0, 9.0, 2.0, 2.0]
    assert distance_to_polyline_m(15, 0, xs, ys) == 2
    # Nearest segment first, in the middle, and last; later ones farther do not replace it.
    assert distance_to_polyline_m(0, 0, [0.0, 10.0, 20.0], [1.0, 5.0, 8.0]) == 1
    assert distance_to_polyline_m(0, 0, [0.0, 0.0, 0.0, 0.0], [1.0, 5.0, 9.0, 20.0]) == 1
    assert distance_to_polyline_m(25, 0, [0.0, 10.0, 10.0, 30.0], [8.0, 8.0, 1.0, 1.0]) == 1
    assert distance_to_polyline_m(15, 0, [0.0, 30.0, 30.0], [8.0, 8.0, 3.0]) == 8


def test_distance_to_polyline_stops_early_once_below_the_threshold() -> None:
    # Distances from (5, 0): 5 (top), 5.39 (riser), 2 (low step, last).
    xs, ys = [0.0, 10.0, 10.0, 0.0], [5.0, 5.0, 2.0, 2.0]
    assert distance_to_polyline_m(5, 0, xs, ys) == 2  # default: full scan
    assert distance_to_polyline_m(5, 0, xs, ys, stop_below=5) == 5  # <= : stops at the first
    assert distance_to_polyline_m(5, 0, xs, ys, stop_below=4.99) == 2
    assert distance_to_polyline_m(5, 0, xs, ys, stop_below=100) == 5
    # The default threshold never stops the scan: an exact hit on the first segment is returned.
    assert distance_to_polyline_m(5, 5, xs, ys) == 0


def _leg_track() -> Track:
    """Two legs: 100 m north in 20 s (x = 0), then a stationary leg (same spot, 10 s later)."""
    return Track(
        t=[100, 120, 130],
        lat=[lat_at(0), lat_at(100), lat_at(100)],
        lon=[lon_at(0)] * 3,
        d=[0.0, 100.0, 100.0],
    )


def test_closest_on_leg_interpolates_distance_time_and_position() -> None:
    gate = (lat_at(25), lon_at(30))  # 30 m east of the leg, 25 m along it
    dist, t, d, u = _closest_on_leg(_leg_track(), 0, gate[0], gate[1], math.cos(math.radians(LAT0)))
    assert math.isclose(dist, 30.0, rel_tol=1e-3)
    assert math.isclose(u, 0.25, rel_tol=1e-3)
    assert math.isclose(t, 105.0, rel_tol=1e-3)
    assert math.isclose(d, 25.0, rel_tol=1e-3)


def test_closest_on_leg_clamps_to_the_leg_ends() -> None:
    cos_lat = math.cos(math.radians(LAT0))
    beyond = (lat_at(150), lon_at(0))  # 50 m past the end of leg 0
    dist, t, d, u = _closest_on_leg(_leg_track(), 0, beyond[0], beyond[1], cos_lat)
    assert (u, t, d) == (1.0, 120.0, 100.0)
    assert math.isclose(dist, 50.0, rel_tol=1e-3)
    before = (lat_at(-40), lon_at(0))
    dist, t, d, u = _closest_on_leg(_leg_track(), 0, before[0], before[1], cos_lat)
    assert (u, t, d) == (0.0, 100.0, 0.0)
    assert math.isclose(dist, 40.0, rel_tol=1e-3)


def test_closest_on_leg_of_zero_length_uses_the_start_of_the_leg() -> None:
    gate = (lat_at(100), lon_at(10))
    dist, t, d, u = _closest_on_leg(_leg_track(), 1, gate[0], gate[1], math.cos(math.radians(LAT0)))
    assert (u, t, d) == (0.0, 120.0, 100.0)
    assert math.isclose(dist, 10.0, rel_tol=1e-3)


def test_approaches_includes_a_point_exactly_on_the_gate_radius() -> None:
    track = northbound(0, 100, step=20)
    vertex = (track.lat[2], track.lon[2])
    (a,) = approaches(track, vertex, gate_m=0.0)  # a zero-radius gate: only an exact hit counts
    assert a.dist_m == 0.0
    assert a.d == 40.0


def test_approaches_keeps_the_first_of_two_equally_close_points_in_one_pass() -> None:
    # Gate at (0, 0), a straight track along lat 0.0625 (binary-exact numbers): the vertex at
    # lon 0 is the closest point of both legs, at exactly the same distance. The earlier leg
    # (reached at u = 1) is kept.
    track = Track(t=[0, 10, 20], lat=[0.0625] * 3, lon=[-0.5, 0.0, 0.5], d=[0.0, 100.0, 200.0])
    (a,) = approaches(track, (0.0, 0.0), gate_m=10_000.0)
    assert (a.leg, a.u, a.t, a.d) == (0, 1.0, 10.0, 100.0)


def test_position_interpolates_between_the_leg_points() -> None:
    track = northbound(0, 60, step=20)  # 4 points
    la, lo = _position(track, Approach(t=0, d=0, dist_m=0, leg=1, u=0.5))
    assert math.isclose(la, (track.lat[1] + track.lat[2]) / 2, abs_tol=1e-12)
    assert lo == track.lon[1]
    # On the last leg, and (defensively) on the last point itself.
    la, _ = _position(track, Approach(t=0, d=0, dist_m=0, leg=2, u=0.5))
    assert math.isclose(la, (track.lat[2] + track.lat[3]) / 2, abs_tol=1e-12)
    assert _position(track, Approach(t=0, d=0, dist_m=0, leg=3, u=0.0)) == (
        track.lat[3],
        track.lon[3],
    )


def test_position_interpolates_longitude_too() -> None:
    track = Track(t=[0, 1], lat=[-47.0, -46.0], lon=[-135.0, -133.0], d=[0.0, 1.0])
    assert _position(track, Approach(t=0, d=0, dist_m=0, leg=0, u=0.25)) == (-46.75, -134.5)


def test_box_grown_converts_metres_to_degrees() -> None:
    box = _Box(-47.0, -46.0, -134.0, -133.0).grown(111_195.0, 0.0)
    assert math.isclose(box.lat_lo, -48.0, abs_tol=1e-3)
    assert math.isclose(box.lat_hi, -45.0, abs_tol=1e-3)
    assert math.isclose(box.lon_lo, -135.0, abs_tol=1e-3)  # at the equator 1 deg lon = 1 deg lat
    at_60 = _Box(0.0, 0.0, 0.0, 0.0).grown(111_195.0, 60.0)
    assert math.isclose(at_60.lon_hi, 2.0, abs_tol=1e-3)  # longitude degrees are twice as wide


def test_box_contains_is_inclusive_on_every_edge_and_needs_both_axes() -> None:
    box = _Box(1.0, 2.0, 10.0, 20.0)
    for lat, lon in [(1, 10), (1, 20), (2, 10), (2, 20), (1.5, 15)]:
        assert box.contains(lat, lon)
    for lat, lon in [(0.9, 15), (2.1, 15), (1.5, 9.9), (1.5, 20.1), (0.9, 9.9), (1.5, 25), (5, 15)]:
        assert not box.contains(lat, lon)


def test_first_pair_uses_the_given_gate_radius() -> None:
    track = northbound(-100, 400, step=5)
    start, end = (lat_at(0), lon_at(0)), (lat_at(60), lon_at(0))
    # 60 m apart: a pair for gate 30 (>= 2 x 30), none for gate 40 (needs 80 m).
    assert _first_pair(track, start, end, 30.0) is not None
    assert _first_pair(track, start, end, 40.0) is None
    # With a 10 m gate the passes are tight: the start pass is near y = 0, the end near y = 60.
    pair = _first_pair(track, start, end, 10.0)
    assert pair is not None
    assert abs(pair[0].d - 100) <= 5 and abs(pair[1].d - 160) <= 5


def test_first_pair_gap_of_exactly_two_gates_counts_and_three_gates_is_not_needed() -> None:
    track = northbound(0, 30, step=10)  # vertices exactly at 0, 10, 20, 30 m
    start, end = (track.lat[0], track.lon[0]), (track.lat[2], track.lon[2])
    pair = _first_pair(track, start, end, 10.0)  # 20 m apart == 2 x gate
    assert pair is not None
    assert (pair[0].d, pair[1].d) == (0.0, 20.0)
    assert _first_pair(track, start, end, 10.5) is None


def test_first_pair_gap_is_a_difference_not_a_sum() -> None:
    far_in = (lat_at(500), lon_at(0))
    near = (lat_at(540), lon_at(0))  # 40 m < 60 m apart, though 1040 m from the origin
    assert _first_pair(northbound(0, 1000), far_in, near, GATE_M) is None
    assert reference_from(northbound(0, 1000), far_in, near) is None
    # Between two and three gates apart is enough.
    ok = (lat_at(580), lon_at(0))
    assert _first_pair(northbound(0, 1000), far_in, ok, GATE_M) is not None


def test_first_pair_needs_the_start_pass_strictly_before_the_end_pass() -> None:
    # A jump of 200 m within the same second: the end pass has the same time as the start pass.
    track = Track(
        t=[0, 10, 10, 20],
        lat=[lat_at(-100), lat_at(100), lat_at(300), lat_at(500)],
        lon=[lon_at(0)] * 4,
        d=[0.0, 200.0, 400.0, 600.0],
    )
    assert _first_pair(track, (lat_at(100), lon_at(0)), (lat_at(300), lon_at(0)), GATE_M) is None


def test_first_pair_passes_the_gate_radius_to_both_gates() -> None:
    track = northbound(-500, 2500, x=20)  # rides 20 m east of x = 0
    on_line = (lat_at(0), lon_at(20))
    off_line = (lat_at(2000), lon_at(0))  # 20 m from the ride: inside 30 m, outside 10 m
    on_line_end = (lat_at(2000), lon_at(20))
    off_line_start = (lat_at(0), lon_at(0))
    assert _first_pair(track, off_line_start, on_line_end, 30.0) is not None
    assert _first_pair(track, off_line_start, on_line_end, 10.0) is None  # start gate missed
    assert _first_pair(track, on_line, off_line, 30.0) is not None
    assert _first_pair(track, on_line, off_line, 10.0) is None  # end gate missed


def test_reference_points_follow_the_ride_around_a_bend() -> None:
    # Sparse corners only: the reference must include the corners that lie between the gates and
    # sample every 50 m along the path from the start pass to the end pass, nothing else.
    ride = _path([(0, -100), (0, 0), (0, 100), (200, 100), (200, 300), (200, 400)])
    start = (lat_at(0), lon_at(0))
    end = (lat_at(230), lon_at(200))
    ref = reference_from(ride, start, end)
    assert ref is not None
    assert math.isclose(ref.length_m, 430.0, abs_tol=0.05)
    expected = [  # (x east, y north) in metres
        (0, 0),
        (0, 50),
        (0, 100),
        (50, 100),
        (100, 100),
        (150, 100),
        (200, 100),
        (200, 150),
        (200, 200),
        (200, 230),
    ]
    assert len(ref.points) == len(expected), ref.points
    for (la, lo), (x, y) in zip(ref.points, expected, strict=True):
        assert math.isclose(la, lat_at(y), abs_tol=1e-7)  # 1e-7 deg ~ 1 cm
        assert math.isclose(lo, lon_at(x), abs_tol=1e-7)


def test_reference_points_with_gates_in_the_middle_of_legs() -> None:
    # Start pass inside the first leg, end pass inside a leg that runs east: the start and end
    # points are the gate passes themselves, the corners between them are all included.
    ride = _path([(0, -100), (0, 110), (200, 110), (200, 310), (400, 310), (400, 500)])
    ref = reference_from(ride, (lat_at(10), lon_at(0)), (lat_at(310), lon_at(310)))
    assert ref is not None
    assert math.isclose(ref.length_m, 610.0, abs_tol=0.05)
    expected = [  # (x east, y north) in metres
        (0, 10),
        (0, 60),
        (0, 110),
        (50, 110),
        (100, 110),
        (150, 110),
        (200, 110),
        (200, 160),
        (200, 210),
        (200, 260),
        (200, 310),
        (250, 310),
        (300, 310),
        (310, 310),
    ]
    assert len(ref.points) == len(expected), ref.points
    for (la, lo), (x, y) in zip(ref.points, expected, strict=True):
        assert math.isclose(la, lat_at(y), abs_tol=1e-7)
        assert math.isclose(lo, lon_at(x), abs_tol=1e-7)


def test_reference_points_start_on_a_later_east_bound_leg() -> None:
    # The start pass is in leg 2 (of 5) and heads east: no vertex before the pass may be included.
    ride = _path([(-300, 0), (-200, 0), (-100, 0), (100, 0), (100, 200), (100, 400)])
    ref = reference_from(ride, (lat_at(0), lon_at(0)), (lat_at(230), lon_at(100)))
    assert ref is not None
    assert math.isclose(ref.length_m, 330.0, abs_tol=0.05)
    expected = [
        (0, 0),
        (50, 0),
        (100, 0),
        (100, 50),
        (100, 100),
        (100, 150),
        (100, 200),
        (100, 230),
    ]
    assert len(ref.points) == len(expected), ref.points
    for (la, lo), (x, y) in zip(ref.points, expected, strict=True):
        assert math.isclose(la, lat_at(y), abs_tol=1e-7)
        assert math.isclose(lo, lon_at(x), abs_tol=1e-7)


def test_path_ok_tolerance_is_inclusive_at_exactly_the_path_limit() -> None:
    # Binary-exact setup at lat 0 / lon 0 so that the reference point is exactly PATH_M from the
    # ride: ride along the equator, reference point PATH_M north of its start.
    lat = PATH_M / _M_PER_DEG
    while lat * _M_PER_DEG > PATH_M:
        lat = math.nextafter(lat, 0.0)
    while lat * _M_PER_DEG < PATH_M:
        lat = math.nextafter(lat, 1.0)
    assert lat * _M_PER_DEG == PATH_M
    track = Track(t=[0, 100], lat=[0.0, 0.0], lon=[0.0, 0.01], d=[0.0, 1000.0])
    s = Approach(t=0, d=0, dist_m=0, leg=0, u=0.0)
    e = Approach(t=100, d=1000, dist_m=0, leg=0, u=1.0)
    on_limit = Reference(1000.0, ((0.0, 0.0), (lat, 0.0)))
    beyond = Reference(1000.0, ((0.0, 0.0), (math.nextafter(lat, 1.0), 0.0)))
    assert _path_ok(track, s, e, on_limit)
    assert not _path_ok(track, s, e, beyond)


def test_path_ok_follows_a_reference_with_a_bend() -> None:
    # The reference's own start is the origin; its later points lie east of it. The ride is the
    # same L shape: every point matches. Cutting the corner by 100 m does not.
    bend = [(0, 0), (0, 500), (500, 500)]
    track = walk(bend)
    start, end = (lat_at(0), lon_at(0)), (lat_at(500), lon_at(500))
    ref = reference_from(track, start, end)
    assert ref is not None
    assert efforts_for(track, start, end, ref)
    cut = walk([(0, 0), (500, 500)])  # the diagonal strays up to ~350 m from the L
    assert not efforts_for(cut, start, end, ref)


def efforts_for(track: Track, start: tuple[float, float], end: tuple[float, float], ref: Reference):
    return find_efforts(track, start, end, "x", reference=ref)


def test_path_ok_reference_points_need_not_be_in_ride_order() -> None:
    # The search for the nearest ride segment wraps around: a reference point that lies behind
    # the previous hit is still found.
    track = northbound(-100, 2100)
    points = tuple((lat_at(y), lon_at(0)) for y in (0, 1500, 500, 2000))
    ref = Reference(2000.0, points)
    s = approaches(track, START)[0]
    e = approaches(track, END)[0]
    assert _path_ok(track, s, e, ref)
    far = Reference(2000.0, (*points, (lat_at(500), lon_at(300))))
    assert not _path_ok(track, s, e, far)


# ---- find_efforts: defaults, thresholds and loop control ----------------------------------------


def test_find_efforts_default_activity_id_is_empty_and_given_id_is_kept() -> None:
    track = northbound(-500, 2500)
    assert [e.activity_id for e in find_efforts(track, START, END)] == [""]
    assert [e.activity_id for e in find_efforts(track, START, END, "act-7")] == ["act-7"]


def test_find_efforts_on_a_two_point_track() -> None:
    track = Track(
        t=[1000, 1400], lat=[lat_at(-500), lat_at(2500)], lon=[lon_at(0)] * 2, d=[0.0, 3000.0]
    )
    (e,) = find_efforts(track, START, END)
    assert e.start_t == 1000 + round(500 / 3000 * 400)
    assert e.elapsed_s == round(2000 / 3000 * 400)
    assert e.distance_m == 2000


def test_find_efforts_gate_radius_applies_to_start_and_end_gates() -> None:
    track = northbound(-500, 2500, x=20)  # rides 20 m east of the gate line
    off_start, off_end = (lat_at(0), lon_at(0)), (lat_at(2000), lon_at(0))
    on_start, on_end = (lat_at(0), lon_at(20)), (lat_at(2000), lon_at(20))
    assert len(find_efforts(track, off_start, off_end)) == 1  # default 30 m gates
    assert len(find_efforts(track, off_start, off_end, gate_m=30.0)) == 1
    assert find_efforts(track, off_start, on_end, gate_m=10.0) == []  # start gate missed
    assert find_efforts(track, on_start, off_end, gate_m=10.0) == []  # end gate missed
    assert len(find_efforts(track, on_start, on_end, gate_m=10.0)) == 1


def test_find_efforts_passes_inside_a_running_effort_do_not_start_new_ones() -> None:
    # Up through the start gate, back down through it, up again to the end gate (one effort),
    # then down and up once more (a second effort). The start passes in between are skipped, not
    # the rest of the ride.
    track = walk([(0, -100), (0, 1000), (0, -100), (0, 2100), (0, -100), (0, 2100)])
    efforts = find_efforts(track, START, END)
    assert len(efforts) == 2, efforts
    assert efforts[0].start_t < efforts[1].start_t
    assert efforts[0].start_t + efforts[0].elapsed_s <= efforts[1].start_t


def test_find_efforts_same_second_start_and_end_is_no_effort() -> None:
    # A jump of 200 m within one second: the end pass has the start pass's time.
    track = Track(
        t=[0, 10, 10, 20],
        lat=[lat_at(-100), lat_at(100), lat_at(300), lat_at(500)],
        lon=[lon_at(0)] * 4,
        d=[0.0, 200.0, 400.0, 600.0],
    )
    assert find_efforts(track, (lat_at(100), lon_at(0)), (lat_at(300), lon_at(0))) == []


def test_find_efforts_gate_pair_of_exactly_two_gates_counts() -> None:
    track = northbound(0, 30, step=10)  # vertices exactly at 0, 10, 20, 30 m
    start, end = (track.lat[0], track.lon[0]), (track.lat[2], track.lon[2])
    (e,) = find_efforts(track, start, end, gate_m=10.0)  # 20 m apart == 2 x gate
    assert e.distance_m == 20
    assert find_efforts(track, start, end, gate_m=10.5) == []


def test_find_efforts_gate_pair_between_two_and_three_gates_counts() -> None:
    end_80m = (lat_at(80), lon_at(0))  # 80 m ridden: >= 2 x 30, < 3 x 30
    (e,) = find_efforts(northbound(-500, 500), START, end_80m)
    assert abs(e.distance_m - 80) <= 2


def _flat_track(d_end: float) -> Track:
    """Three points 100 m apart going north whose odometer reads 0, d_end, 2 * d_end."""
    return Track(
        t=[0, 30, 60],
        lat=[lat_at(0), lat_at(100), lat_at(200)],
        lon=[lon_at(0)] * 3,
        d=[0.0, d_end, 2 * d_end],
    )


def _flat_efforts(ref_length: float, ridden: float) -> list:
    start, end = (lat_at(0), lon_at(0)), (lat_at(100), lon_at(0))
    ref = Reference(ref_length, (start, end))
    return find_efforts(_flat_track(ridden), start, end, "x", reference=ref)


def test_length_tolerance_is_inclusive_at_exactly_ten_percent() -> None:
    assert len(_flat_efforts(1000.0, 1100.0)) == 1  # exactly +10 %
    assert len(_flat_efforts(1000.0, 900.0)) == 1  # exactly -10 %
    assert len(_flat_efforts(117.5, 117.5 * (1 + 0.10))) == 1  # +10 %, fractional length
    assert _flat_efforts(1000.0, 1100.5) == []
    assert _flat_efforts(1000.0, 899.5) == []


def test_length_far_below_the_reference_is_no_effort() -> None:
    assert _flat_efforts(1000.0, 500.0) == []
    assert _flat_efforts(1000.0, 800.0) == []


def test_too_short_first_end_pass_does_not_stop_the_search() -> None:
    # The reference is 2500 m long though the gates are 2000 m apart. The first end pass is
    # ridden over 2000 m (too short); the ride then goes on and returns to the end gate after
    # 2500 m, which matches.
    straight = reference_from(walk([(0, 0), (0, 2000)]), START, END)
    assert straight is not None
    ref = Reference(2500.0, straight.points)
    track = walk([(0, -100), (0, 2000), (0, 2250), (0, 2000), (0, 2100)])
    (e,) = find_efforts(track, START, END, "x", reference=ref)
    assert abs(e.distance_m - 2500) <= 5


def test_path_failing_first_end_pass_does_not_stop_the_search() -> None:
    # A reference point 70 m east of the end gate is not within 60 m of the ride at the first end
    # pass. The ride then detours through that point and comes back to the gate: that pass
    # (ridden 2140 m, within 10 % of 2000 m) matches.
    straight = reference_from(walk([(0, 0), (0, 2000)]), START, END)
    assert straight is not None
    ref = Reference(2000.0, (*straight.points, (lat_at(2000), lon_at(70))))
    direct = walk([(0, -100), (0, 2000), (0, 2100)])
    assert find_efforts(direct, START, END, "x", reference=ref) == []
    detour = walk([(0, -100), (0, 2000), (70, 2000), (0, 2000), (0, 2100)])
    (e,) = find_efforts(detour, START, END, "x", reference=ref)
    assert abs(e.distance_m - 2140) <= 5
