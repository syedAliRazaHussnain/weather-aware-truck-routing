"""Tests for planner.geo: road distance, driving time, and where checkpoints go.
Comments like "#17" point to README assumptions."""

import pytest

from planner.geo import (
    Step,
    checkpoint_marks,
    checkpoints,
    cumulative_miles,
    cumulative_seconds,
    haversine_mi,
    point_at,
    slice_path,
    time_at,
)

DENVER = (39.7392, -104.9903)
SALT_LAKE_CITY = (40.7608, -111.8910)
ONE_DEGREE_LAT_MI = 69.094  # one degree of latitude, north-south


# --- Distance ----------------------------------------------------------------


def test_distance_from_a_point_to_itself_is_zero():
    """No movement, no miles."""
    assert haversine_mi(DENVER, DENVER) == 0


def test_one_degree_of_latitude_is_about_69_miles():
    """A known fact about the Earth, so the formula and radius are right."""
    assert haversine_mi((0, 0), (1, 0)) == pytest.approx(ONE_DEGREE_LAT_MI, abs=0.01)


def test_denver_to_salt_lake_city_is_about_371_miles_in_a_straight_line():
    """Real cities: the straight line is ~371 mi (the road is ~491 mi, see #16)."""
    assert haversine_mi(DENVER, SALT_LAKE_CITY) == pytest.approx(370.6, abs=0.5)


def test_distance_is_the_same_in_both_directions():
    """A to B equals B to A."""
    assert haversine_mi(DENVER, SALT_LAKE_CITY) == haversine_mi(SALT_LAKE_CITY, DENVER)


def test_miles_add_up_along_the_path():
    """#16: three points 1 degree apart, driven north, give 0, 69 and 138 miles."""
    miles = cumulative_miles([(0, 0), (1, 0), (2, 0)])
    assert miles == pytest.approx([0, ONE_DEGREE_LAT_MI, 2 * ONE_DEGREE_LAT_MI], abs=0.01)


# --- Driving time ------------------------------------------------------------


def test_each_step_is_driven_at_its_own_average_speed():
    """#21: 3 highway miles at 1 min/mi, then 2 city miles at 4 min/mi."""
    miles = [0, 1, 2, 3, 4, 5]
    steps = [Step(start=0, end=3, seconds=180), Step(start=3, end=5, seconds=480)]
    assert cumulative_seconds(miles, steps) == pytest.approx([0, 60, 120, 180, 420, 660])


def test_time_follows_distance_when_path_points_are_unevenly_spaced():
    """Within a step, a 3 mi gap takes three times as long as a 1 mi gap."""
    miles = [0, 1, 4]
    assert cumulative_seconds(miles, [Step(0, 2, 400)]) == pytest.approx([0, 100, 400])


def test_a_step_with_no_length_still_counts_its_time():
    """A zero-length step (e.g. at a via point) adds its time to the next move."""
    miles = [0, 1, 2]
    steps = [Step(0, 1, 60), Step(1, 1, 30), Step(1, 2, 60)]
    assert cumulative_seconds(miles, steps) == pytest.approx([0, 60, 150])


def test_total_driving_time_equals_the_sum_of_the_steps():
    """No time is lost or invented: the last point's time is the trip duration."""
    miles = [0, 2, 5, 9]
    steps = [Step(0, 1, 100), Step(1, 3, 250), Step(3, 3, 0)]
    assert cumulative_seconds(miles, steps)[-1] == pytest.approx(350)


# --- Checkpoint marks --------------------------------------------------------


def test_marks_count_from_the_origin_and_end_at_the_destination():
    """#17, #18: a 491 mi route at 25 mi gives 0, 25 ... 475, then 491 (21 marks)."""
    marks = checkpoint_marks(491, 25)
    assert len(marks) == 21
    assert marks[:3] == [0, 25, 50]
    assert marks[-2:] == [475, 491]


def test_destination_is_not_repeated_when_it_lands_on_a_mark():
    """#18: a 50 mi route at 25 mi gives 0, 25, 50, with no second 50."""
    assert checkpoint_marks(50, 25) == [0, 25, 50]


def test_a_trip_shorter_than_the_interval_still_gets_both_ends():
    """#18: a 10 mi trip at 25 mi still checks the origin and the destination."""
    assert checkpoint_marks(10, 25) == [0, 10]


@pytest.mark.parametrize("interval", [0, -25])
def test_interval_must_be_positive(interval):
    """A zero or negative interval would never finish, so it's refused."""
    with pytest.raises(ValueError):
        checkpoint_marks(100, interval)


# --- Locating a mile ---------------------------------------------------------


def test_a_mile_between_two_path_points_is_placed_on_the_line_between_them():
    """#19: the Part 3 example. Mile 25 sits halfway between 24.6 mi (31.0 min)
    and 25.4 mi (32.0 min), so it gets the halfway position and 31.5 min."""
    path = [(40.0, -105.0), (40.0, -104.9)]
    miles = [24.6, 25.4]
    assert point_at(path, miles, 25) == pytest.approx((40.0, -104.95))
    assert time_at(miles, [1860, 1920], 25) == pytest.approx(1890)


def test_a_mile_exactly_on_a_path_point_uses_that_point():
    """No interpolation needed when the mile matches a point."""
    path = [(0, 0), (1, 0), (2, 0)]
    miles = [0, 10, 20]
    assert point_at(path, miles, 10) == (1, 0)
    assert time_at(miles, [0, 600, 1200], 10) == 600


def test_miles_outside_the_route_are_held_at_its_ends():
    """Rounding can ask for a hair past the end; we return the end, not an error."""
    path = [(0, 0), (1, 0)]
    miles = [0, 10]
    assert point_at(path, miles, -1) == (0, 0)
    assert point_at(path, miles, 10.0001) == (1, 0)
    assert time_at(miles, [0, 600], 10.0001) == 600


# --- Checkpoints for a whole route -------------------------------------------


def test_route_checkpoints_start_at_the_origin_and_end_at_the_destination():
    """#17, #18: a ~138 mi route north at 50 mi gives 4 checkpoints, first and last
    exactly at the ends, with the last one's time equal to the whole trip."""
    path = [(0, 0), (1, 0), (2, 0)]
    steps = [Step(0, 2, 7200)]  # 2 hours for the whole route
    cps = checkpoints(path, steps, interval_mi=50)
    assert [round(c.mile, 2) for c in cps] == [0, 50, 100, round(2 * ONE_DEGREE_LAT_MI, 2)]
    assert (cps[0].lat, cps[0].lon, cps[0].seconds) == (0, 0, 0)
    assert (cps[-1].lat, cps[-1].lon) == (2, 0)
    assert cps[-1].seconds == pytest.approx(7200)


def test_checkpoint_times_never_go_backwards():
    """Later miles are always reached later."""
    path = [(0, 0), (0.5, 0), (1, 0), (2, 0)]
    steps = [Step(0, 2, 3600), Step(2, 3, 1800)]
    times = [c.seconds for c in checkpoints(path, steps, interval_mi=10)]
    assert times == sorted(times)


def test_a_route_needs_at_least_two_points():
    """One point is not a route."""
    with pytest.raises(ValueError):
        checkpoints([(0, 0)], [], interval_mi=25)


# --- Slicing the route for coloured segments --------------------------------


def test_slice_contains_its_end_points_and_the_path_points_inside():
    """Mile 5 to 15 on a 0/10/20 path: interpolated ends plus the point at mile 10."""
    path = [(0, 0), (1, 0), (2, 0)]
    piece = slice_path(path, [0, 10, 20], from_mi=5, to_mi=15)
    assert piece == pytest.approx([(0.5, 0), (1, 0), (1.5, 0)])


def test_slices_that_meet_share_the_same_point():
    """Neighbouring coloured segments join without a gap on the map."""
    path = [(0, 0), (1, 0), (2, 0)]
    first = slice_path(path, [0, 10, 20], from_mi=0, to_mi=12.5)
    second = slice_path(path, [0, 10, 20], from_mi=12.5, to_mi=20)
    assert first[-1] == second[0]
