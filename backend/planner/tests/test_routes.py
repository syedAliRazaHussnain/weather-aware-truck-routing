"""Tests for planner.routes: detour points, how different two routes are, and picking
alternatives. Comments like "#15" point to README assumptions."""

import pytest

from planner.geo import haversine_mi
from planner.routes import (
    Route,
    detour_point,
    detour_points,
    is_acceptable,
    overlap_fraction,
    pick_alternatives,
    resample,
)

WEST, EAST = (40.0, -105.0), (40.0, -104.0)  # ~53 mi apart, driving east
DENVER, SALT_LAKE_CITY = (39.7392, -104.9903), (40.7608, -111.8910)  # driving west
MIDPOINT = (40.0, -104.5)
THREE_MILES_NORTH = 3 / 69.094  # in degrees of latitude


def route(path, hours=1.0):
    """A test route with no ORS steps, just a path and a driving time."""
    return Route(path=path, steps=[], seconds=hours * 3600)


# --- Detour points -----------------------------------------------------------


def test_left_detour_is_north_when_driving_east():
    """Facing east, your left hand points north."""
    lat, lon = detour_point(WEST, EAST, fraction=0.15, side=+1)
    assert lat > 40.0
    assert lon == pytest.approx(-104.5, abs=0.01)


def test_left_detour_is_south_when_driving_west():
    """Facing west (Denver to Salt Lake City), your left hand points south."""
    mid_lat = (DENVER[0] + SALT_LAKE_CITY[0]) / 2
    lat, _ = detour_point(DENVER, SALT_LAKE_CITY, fraction=0.15, side=+1)
    assert lat < mid_lat


def test_detour_sits_the_given_share_of_the_trip_away_from_the_midpoint():
    """#14: 15% of a ~53 mi trip puts the via point ~7.9 mi off the midpoint."""
    point = detour_point(WEST, EAST, fraction=0.15, side=+1)
    trip = haversine_mi(WEST, EAST)
    assert haversine_mi(MIDPOINT, point) == pytest.approx(0.15 * trip, rel=0.01)


def test_detour_is_as_far_from_the_origin_as_from_the_destination():
    """It sits on the line through the midpoint at right angles to the trip."""
    point = detour_point(DENVER, SALT_LAKE_CITY, fraction=0.25, side=-1)
    assert haversine_mi(DENVER, point) == pytest.approx(
        haversine_mi(SALT_LAKE_CITY, point), rel=0.01
    )


def test_left_and_right_detours_mirror_each_other():
    """Same distance from the midpoint, opposite sides."""
    left = detour_point(WEST, EAST, fraction=0.25, side=+1)
    right = detour_point(WEST, EAST, fraction=0.25, side=-1)
    assert left[0] - 40.0 == pytest.approx(40.0 - right[0])


def test_detours_are_tried_nearest_first_alternating_sides():
    """#14: 15% left, 15% right, 25% left, 25% right, 35% left, 35% right."""
    points = list(detour_points(WEST, EAST))
    assert len(points) == 6
    offsets = [haversine_mi(MIDPOINT, p) for p in points]
    for pair in (0, 2, 4):  # each fraction is used on both sides
        assert offsets[pair] == pytest.approx(offsets[pair + 1], rel=0.01)
    assert offsets[0] < offsets[2] < offsets[4]
    sides = ["north" if p[0] > 40.0 else "south" for p in points]
    assert sides == ["north", "south"] * 3


def test_origin_and_destination_must_differ():
    """There is no 'beside the trip' for a trip of zero length."""
    with pytest.raises(ValueError):
        detour_point(WEST, WEST, fraction=0.15, side=+1)


# --- Comparing routes --------------------------------------------------------


def test_resampling_spaces_points_evenly_and_keeps_both_ends():
    """A 53 mi straight line with only 2 points becomes points 0.25 mi apart."""
    samples = resample([WEST, EAST])
    assert samples[0] == pytest.approx(WEST)
    assert samples[-1] == pytest.approx(EAST)
    gaps = [haversine_mi(a, b) for a, b in zip(samples, samples[1:], strict=False)]
    assert max(gaps) <= 0.26


def test_a_route_overlaps_itself_completely():
    """The same road is 100% overlap."""
    assert overlap_fraction([WEST, EAST], [WEST, EAST]) == pytest.approx(1.0)


def test_a_parallel_road_three_miles_away_does_not_overlap():
    """#15: more than 1 mi apart counts as a different road."""
    north_road = [(40.0 + THREE_MILES_NORTH, -105.0), (40.0 + THREE_MILES_NORTH, -104.0)]
    assert overlap_fraction(north_road, [WEST, EAST]) == 0.0


def test_a_route_sharing_its_first_half_overlaps_about_half():
    """Shares ~26 mi of road, then turns north for ~35 mi: under half its length."""
    turns_north = [WEST, MIDPOINT, (40.5, -104.5)]
    assert 0.4 < overlap_fraction(turns_north, [WEST, EAST]) < 0.5


# --- Accepting a candidate ---------------------------------------------------


def test_a_different_route_within_1_5x_the_time_is_accepted():
    """#15: different road, 1.2x the fastest time."""
    fastest = route([WEST, EAST], hours=1.0)
    north_road = route([WEST, (40.3, -104.5), EAST], hours=1.2)
    assert is_acceptable(north_road, [fastest], fastest)


def test_exactly_1_5x_the_time_is_still_accepted():
    """#15: only routes taking MORE than 1.5x are dropped."""
    fastest = route([WEST, EAST], hours=1.0)
    assert is_acceptable(route([WEST, (40.3, -104.5), EAST], hours=1.5), [fastest], fastest)


def test_a_route_over_1_5x_the_time_is_dropped():
    """#15: a big detour that takes 1.6x the time isn't a fair alternative."""
    fastest = route([WEST, EAST], hours=1.0)
    assert not is_acceptable(route([WEST, (40.3, -104.5), EAST], hours=1.6), [fastest], fastest)


def test_a_route_mostly_on_the_same_road_is_dropped():
    """#15: a candidate that's 80% or more on an already chosen route adds nothing."""
    fastest = route([WEST, EAST], hours=1.0)
    almost_same = route([WEST, (40.001, -104.5), EAST], hours=1.0)
    assert not is_acceptable(almost_same, [fastest], fastest)


def test_a_candidate_must_differ_from_every_chosen_route_not_just_the_fastest():
    """A third route that copies the second one is dropped."""
    fastest = route([WEST, EAST], hours=1.0)
    second = route([WEST, (40.3, -104.5), EAST], hours=1.2)
    copy_of_second = route([WEST, (40.3, -104.5), EAST], hours=1.2)
    assert not is_acceptable(copy_of_second, [fastest, second], fastest)


# --- Picking alternatives ----------------------------------------------------


def test_picking_skips_duplicates_and_missing_roads_and_stops_when_it_has_two():
    """Tries detours in order: a duplicate (dropped), no road (skipped), then two
    distinct routes, and stops there without asking for more."""
    fastest = route([WEST, EAST])
    answers = [
        route([WEST, (40.0005, -104.5), EAST]),  # same road as the fastest
        None,  # no truck road near this detour point
        route([WEST, (40.3, -104.5), EAST], hours=1.2),  # north
        route([WEST, (39.7, -104.5), EAST], hours=1.3),  # south
        route([WEST, (40.5, -104.5), EAST], hours=1.4),  # never asked for
    ]
    calls = []

    def route_via(point):
        calls.append(point)
        return answers[len(calls) - 1]

    picked = pick_alternatives(fastest, WEST, EAST, route_via)
    assert [r.seconds / 3600 for r in picked] == [1.2, 1.3]
    assert len(calls) == 4


def test_picking_returns_fewer_when_no_distinct_route_exists():
    """#15: every detour comes back on the same road, so no alternatives, after
    trying all 6 detour points."""
    fastest = route([WEST, EAST])
    calls = []

    def route_via(point):
        calls.append(point)
        return route([WEST, EAST])

    assert pick_alternatives(fastest, WEST, EAST, route_via) == []
    assert len(calls) == 6
