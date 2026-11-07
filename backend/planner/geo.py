"""Distances, travel times and checkpoints along a route.

Pure functions only: no Django, no network calls. A route arrives as a list of
path points plus the ORS steps that say how long each stretch takes to drive.
Comments like "#16" point to the numbered assumptions in the README.

Points are (lat, lon) tuples in degrees. ORS sends [lon, lat]; the ORS client
swaps them before anything here sees them.
"""

from bisect import bisect_right
from dataclasses import dataclass
from itertools import pairwise
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_MI = 3958.8

Point = tuple[float, float]  # (lat, lon) in degrees


@dataclass(frozen=True)
class Step:
    """One ORS instruction: driving from path point `start` to `end` takes `seconds`."""

    start: int
    end: int
    seconds: float


@dataclass(frozen=True)
class Checkpoint:
    """A place on the route where weather is checked, and when the truck gets there."""

    mile: float  # along the road from the origin (#16)
    lat: float
    lon: float
    seconds: float  # driving time from departure (#20, #23: no rest stops)


def haversine_mi(a: Point, b: Point) -> float:
    """Distance in miles between two points over the Earth's surface."""
    lat1, lon1, lat2, lon2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * asin(sqrt(h))


def cumulative_miles(path: list[Point]) -> list[float]:
    """Miles driven from the origin to each path point, summed along the road (#16)."""
    miles = [0.0]
    for prev, point in pairwise(path):
        miles.append(miles[-1] + haversine_mi(prev, point))
    return miles


def cumulative_seconds(miles: list[float], steps: list[Step]) -> list[float]:
    """Driving time from departure to each path point, using each ORS step's duration."""
    # Each step's time is spread over its points in proportion to distance, i.e. the
    # truck moves at that step's average speed (#21).
    added = [0.0] * len(miles)  # time to reach point k from point k-1
    carry = 0.0  # time from a step with no length, added at the next point that moves
    for step in steps:
        if step.end <= step.start:
            carry += step.seconds
            continue
        span = miles[step.end] - miles[step.start]
        points = step.end - step.start
        for k in range(step.start + 1, step.end + 1):
            share = (miles[k] - miles[k - 1]) / span if span > 0 else 1 / points
            added[k] += step.seconds * share
        added[step.start + 1] += carry
        carry = 0.0
    added[-1] += carry

    seconds = [0.0]
    for k in range(1, len(miles)):
        seconds.append(seconds[-1] + added[k])
    return seconds


def checkpoint_marks(total_mi: float, interval_mi: float) -> list[float]:
    """Miles where checkpoints go: 0, N, 2N ... plus the destination (#17, #18)."""
    if interval_mi <= 0:
        raise ValueError("interval_mi must be positive")
    marks = [i * interval_mi for i in range(int(total_mi // interval_mi) + 1)]
    if total_mi - marks[-1] > 1e-6:  # destination, unless it already landed on a mark
        marks.append(total_mi)
    return marks


def _bracket(miles: list[float], mile: float) -> tuple[int, float]:
    """Which two path points a mile falls between (i and i+1), and how far along (0-1)."""
    if mile <= miles[0]:
        return 0, 0.0
    if mile >= miles[-1]:  # rounding can ask for a hair past the end
        return len(miles) - 2, 1.0
    i = bisect_right(miles, mile) - 1  # miles[i] <= mile < miles[i + 1]
    return i, (mile - miles[i]) / (miles[i + 1] - miles[i])


def point_at(path: list[Point], miles: list[float], mile: float) -> Point:
    """The position at a given mile, between the two nearest path points."""
    # #19: on the straight line between neighbouring path points, which are only
    # tens of metres apart.
    i, f = _bracket(miles, mile)
    (lat1, lon1), (lat2, lon2) = path[i], path[i + 1]
    return (lat1 + f * (lat2 - lat1), lon1 + f * (lon2 - lon1))


def time_at(miles: list[float], seconds: list[float], mile: float) -> float:
    """The driving time at a given mile, between the two nearest path points."""
    i, f = _bracket(miles, mile)
    return seconds[i] + f * (seconds[i + 1] - seconds[i])


def checkpoints(path: list[Point], steps: list[Step], interval_mi: float) -> list[Checkpoint]:
    """Every checkpoint on one route, with its mile, position and driving time."""
    if len(path) < 2:
        raise ValueError("a route needs at least two path points")
    miles = cumulative_miles(path)
    seconds = cumulative_seconds(miles, steps)
    result = []
    for mark in checkpoint_marks(miles[-1], interval_mi):
        lat, lon = point_at(path, miles, mark)
        secs = time_at(miles, seconds, mark)
        result.append(Checkpoint(mile=mark, lat=lat, lon=lon, seconds=secs))
    return result


def slice_path(path: list[Point], miles: list[float], from_mi: float, to_mi: float) -> list[Point]:
    """The piece of the route between two miles, for drawing one coloured segment."""
    start = point_at(path, miles, from_mi)
    end = point_at(path, miles, to_mi)
    inside = [p for p, m in zip(path, miles, strict=True) if from_mi < m < to_mi]
    return [start, *inside, end]
