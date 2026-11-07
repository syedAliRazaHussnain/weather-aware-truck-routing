"""Choosing up to three different truck routes for one trip.

Pure logic only: the ORS calls are passed in as a function, so everything here
is tested without the network. Comments like "#14" point to the numbered
assumptions in the README.

ORS's free API only returns alternative routes for trips under 100 km. For
longer trips we ask for routes forced through a detour point to the left or
right of the trip's midpoint, and keep the ones that are really different.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from math import cos, floor, hypot, radians

from planner.geo import Point, Step, cumulative_miles, haversine_mi, point_at

MILES_PER_DEGREE_LAT = 69.094

DETOUR_FRACTIONS = (0.15, 0.25, 0.35)  # #14: offset as a share of the trip length
MAX_SLOWDOWN = 1.5  # #15: alternatives may take at most 1.5x the fastest time
SAME_ROAD_MI = 1.0  # #15: closer than this to another route counts as the same road
MAX_OVERLAP = 0.8  # #15: drop a candidate if 80% or more of it is on another route
SAMPLE_EVERY_MI = 0.25  # how finely routes are compared


@dataclass(frozen=True)
class Route:
    """One drivable route: its path, the ORS steps along it, and total driving time."""

    path: list[Point]
    steps: list[Step]
    seconds: float


def detour_point(origin: Point, destination: Point, fraction: float, side: int) -> Point:
    """A point beside the trip's midpoint, `fraction` of the trip length away (#14).

    side=+1 is to the left when facing the destination, side=-1 to the right.
    """
    mid_lat = (origin[0] + destination[0]) / 2
    mid_lon = (origin[1] + destination[1]) / 2
    # A flat map around the midpoint, in miles: good enough to place a via point.
    mi_per_deg_lon = MILES_PER_DEGREE_LAT * cos(radians(mid_lat))
    east = (destination[1] - origin[1]) * mi_per_deg_lon
    north = (destination[0] - origin[0]) * MILES_PER_DEGREE_LAT
    length = hypot(east, north)
    if length == 0:
        raise ValueError("origin and destination are the same place")
    offset = fraction * haversine_mi(origin, destination)
    # Turning (east, north) a quarter turn to the left gives (-north, east).
    left_east, left_north = -north / length, east / length
    return (
        mid_lat + side * left_north * offset / MILES_PER_DEGREE_LAT,
        mid_lon + side * left_east * offset / mi_per_deg_lon,
    )


def detour_points(origin: Point, destination: Point) -> Iterator[Point]:
    """Detour points to try, nearest first, alternating left and right (#14)."""
    for fraction in DETOUR_FRACTIONS:
        for side in (+1, -1):
            yield detour_point(origin, destination, fraction, side)


def resample(path: list[Point], every_mi: float = SAMPLE_EVERY_MI) -> list[Point]:
    """Points spaced evenly along a path, so long straight stretches aren't skipped."""
    miles = cumulative_miles(path)
    count = max(1, round(miles[-1] / every_mi))
    return [point_at(path, miles, miles[-1] * i / count) for i in range(count + 1)]


def overlap_fraction(candidate: list[Point], other: list[Point]) -> float:
    """Share of the candidate's length that runs within SAME_ROAD_MI of the other route."""
    # Bucket the other route's points into a grid of SAME_ROAD_MI squares, so each
    # candidate point only checks its own square and the eight around it.
    ref_lat = sum(lat for lat, _ in other) / len(other)
    cell_lat = SAME_ROAD_MI / MILES_PER_DEGREE_LAT
    cell_lon = cell_lat / max(cos(radians(ref_lat)), 0.01)

    def cell(p: Point) -> tuple[int, int]:
        return floor(p[0] / cell_lat), floor(p[1] / cell_lon)

    grid: dict[tuple[int, int], list[Point]] = {}
    for p in resample(other):
        grid.setdefault(cell(p), []).append(p)

    samples = resample(candidate)
    near = 0
    for p in samples:
        row, col = cell(p)
        neighbours = (
            q for dr in (-1, 0, 1) for dc in (-1, 0, 1) for q in grid.get((row + dr, col + dc), [])
        )
        if any(haversine_mi(p, q) <= SAME_ROAD_MI for q in neighbours):
            near += 1
    return near / len(samples)


def is_acceptable(candidate: Route, chosen: list[Route], fastest: Route) -> bool:
    """True if the candidate is fast enough and different from every route already chosen."""
    if candidate.seconds > MAX_SLOWDOWN * fastest.seconds:
        return False  # #15: too slow to be a fair alternative
    return all(overlap_fraction(candidate.path, r.path) < MAX_OVERLAP for r in chosen)


def pick_alternatives(
    fastest: Route,
    origin: Point,
    destination: Point,
    route_via: Callable[[Point], Route | None],
    wanted: int = 2,
) -> list[Route]:
    """Up to `wanted` distinct alternatives, trying detour points one by one (#14, #15).

    `route_via(point)` asks ORS for a route through that point, and returns None
    if there's no truck road near it. Stops as soon as enough routes are found,
    so a trip costs at most 6 extra routing calls.
    """
    chosen = [fastest]
    for via in detour_points(origin, destination):
        if len(chosen) > wanted:
            break
        candidate = route_via(via)
        if candidate is not None and is_acceptable(candidate, chosen, fastest):
            chosen.append(candidate)
    return chosen[1:]
