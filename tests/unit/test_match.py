"""Gate matcher (REQ-004 basic: start/end gates, elapsed includes stops)."""

from __future__ import annotations

import itertools
import math

from sdash.match import (
    GATE_M,
    PATH_M,
    Reference,
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
