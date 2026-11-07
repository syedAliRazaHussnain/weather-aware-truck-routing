"""Tests for planner.corridor: which heatmap squares are coloured, how big they are,
and their hourly risk. Comments like "#51" point to README assumptions."""

import pytest

from planner.corridor import (
    CORRIDOR_MI,
    HEATMAP_HOURS,
    START_SQUARE_MI,
    Grid,
    corridor_cells,
    hourly_levels,
    plan_heatmap,
)
from planner.geo import haversine_mi
from planner.risk import Risk, Weather
from planner.routes import resample

# ~106 mi driving east along latitude 40
EAST_ROUTE = [(40.0, -105.0), (40.0, -104.0), (40.0, -103.0)]
GRID_25 = Grid(square_mi=25, ref_lat=40.0)


# --- Squares -----------------------------------------------------------------


def test_squares_are_about_25_miles_on_each_side():
    """#52: a square's edges measure ~25 mi on the ground at its latitude."""
    square = GRID_25.cell_of((40.0, -104.5))  # a square at the grid's own latitude
    south_west, south_east, north_east, _, _ = GRID_25.corners(square)
    assert haversine_mi(south_west, south_east) == pytest.approx(25, rel=0.02)
    assert haversine_mi(south_east, north_east) == pytest.approx(25, rel=0.02)


def test_a_point_falls_inside_its_own_square():
    """cell_of and corners agree."""
    p = (40.123, -104.567)
    south, west = GRID_25.corners(GRID_25.cell_of(p))[0]
    assert south <= p[0] < south + GRID_25.cell_lat
    assert west <= p[1] < west + GRID_25.cell_lon


def test_square_outline_is_closed_for_drawing():
    """GeoJSON polygons repeat the first corner at the end."""
    corners = GRID_25.corners((1, 2))
    assert len(corners) == 5
    assert corners[0] == corners[-1]


# --- Which squares -----------------------------------------------------------


def test_corridor_squares_are_all_near_the_route():
    """#51: every coloured square's centre is within 50 mi of the route."""
    samples = resample(EAST_ROUTE, every_mi=1)
    for cell in corridor_cells([EAST_ROUTE], GRID_25):
        nearest = min(haversine_mi(GRID_25.center(cell), p) for p in samples)
        assert nearest <= CORRIDOR_MI + 0.5


def test_corridor_is_a_strip_not_the_whole_rectangle():
    """#51: about (106 + 100) x 100 mi of strip in 25 mi squares is ~30 squares."""
    assert 20 <= len(corridor_cells([EAST_ROUTE], GRID_25)) <= 40


def test_every_point_on_the_route_is_covered():
    """Even with squares bigger than the corridor, the road itself is never left out."""
    big = Grid(square_mi=120, ref_lat=40.0)
    cells = corridor_cells([EAST_ROUTE], big)
    for p in resample(EAST_ROUTE, every_mi=5):
        assert big.cell_of(p) in cells


def test_routes_sharing_a_road_do_not_double_the_squares():
    """A square near two routes is still one square (and one weather call)."""
    assert corridor_cells([EAST_ROUTE, EAST_ROUTE], GRID_25) == corridor_cells(
        [EAST_ROUTE], GRID_25
    )


# --- Square size and the budget ----------------------------------------------


def test_squares_stay_25_miles_when_the_budget_allows():
    """#52: no reason to go coarser than 25 mi when the squares fit."""
    grid, cells = plan_heatmap([EAST_ROUTE], max_cells=250)
    assert grid.square_mi == START_SQUARE_MI
    assert len(cells) <= 250


def test_squares_grow_until_they_fit_a_small_budget():
    """#37, #52: with room for only 10 squares, they get bigger until 10 or fewer cover it."""
    grid, cells = plan_heatmap([EAST_ROUTE], max_cells=10)
    assert grid.square_mi > START_SQUARE_MI
    assert 0 < len(cells) <= 10


def test_the_heatmap_needs_room_for_at_least_one_square():
    """A zero budget is a bug upstream, so it's refused loudly."""
    with pytest.raises(ValueError):
        plan_heatmap([EAST_ROUTE], max_cells=0)


# --- Hourly levels -----------------------------------------------------------


def test_one_level_per_hour_for_the_whole_slider():
    """#48: 49 hours of weather give 49 levels."""
    calm = [Weather(wind_mph=5, rain_in_hr=0, snow_in_hr=0)] * HEATMAP_HOURS
    assert hourly_levels(calm, load_lb=20_000) == [0] * HEATMAP_HOURS


def test_squares_use_the_drivers_load_like_checkpoints_do():
    """#50: 40 mph wind is High empty, but Severe with 42,000 lb, on the map too."""
    windy = [Weather(wind_mph=40, rain_in_hr=0, snow_in_hr=0)]
    assert hourly_levels(windy, load_lb=0) == [int(Risk.HIGH)]
    assert hourly_levels(windy, load_lb=42_000) == [int(Risk.SEVERE)]
