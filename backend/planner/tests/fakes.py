"""Stand-ins for HTTP and the outside services, so tests run offline and never use API quota."""

import json
from pathlib import Path

import requests

from planner.clients.errors import AlternativesNotAllowed
from planner.clients.weather import HOUR, HourlySeries
from planner.geo import Step, cumulative_miles
from planner.routes import Route

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict:
    """A saved API answer from tests/fixtures."""
    return json.loads((FIXTURES / name).read_text())


class FakeResponse:
    """Just enough of requests.Response for the clients."""

    def __init__(self, status_code: int, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeSession:
    """Answers requests from a queue and records what was asked."""

    def __init__(self, *answers):
        self.answers = list(answers)  # FakeResponse objects or exceptions to raise
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)


TIMEOUT = requests.Timeout("timed out")


# --- Fake outside services for service and API tests -------------------------


def polyline(points, per_leg=40):
    """A path through the given (lat, lon) points, with evenly spaced points on each leg."""
    path = [points[0]]
    for (lat1, lon1), (lat2, lon2) in zip(points, points[1:], strict=False):
        for k in range(1, per_leg + 1):
            f = k / per_leg
            path.append((lat1 + f * (lat2 - lat1), lon1 + f * (lon2 - lon1)))
    return path


def straight_route(points, mph=50.0):
    """A route through the points, driven at a steady speed, as one ORS step."""
    path = polyline(points)
    seconds = cumulative_miles(path)[-1] / mph * HOUR
    return Route(path=path, steps=[Step(0, len(path) - 1, seconds)], seconds=seconds)


class FakeOrs:
    """Stands in for OrsClient: routes are straight lines through the points asked for."""

    def __init__(self, error=None, alternatives=None, mph=50.0, nearest=None, ignore_via=False):
        self.error = error
        self.alternatives = alternatives
        self.mph = mph
        self.nearest = nearest
        self.ignore_via = ignore_via
        self.route_calls = []
        self.alternative_calls = 0

    def truck_route(self, points, gross_lb):
        self.route_calls.append({"points": points, "gross_lb": gross_lb})
        if self.error is not None:
            raise self.error
        if self.ignore_via:
            points = [points[0], points[-1]]
        return straight_route(points, self.mph)

    def truck_alternatives(self, origin, destination, gross_lb):
        self.alternative_calls += 1
        if self.alternatives is None:
            raise AlternativesNotAllowed("over 100 km")
        return self.alternatives

    def nearest_place(self, point):
        return self.nearest


def calm(lat, lon, unix_time):
    """(wind mph, gust mph, rain in/hr, snow in/hr) for a calm day everywhere."""
    return 5.0, 8.0, 0.0, 0.0


class FakeWeather:
    """Stands in for WeatherClient: conditions come from a function of place and time."""

    def __init__(self, conditions=calm, error=None):
        self.conditions = conditions
        self.error = error
        self.fetched = []

    def fetch(self, cells, start, end):
        cells = list(cells)
        self.fetched.append({"cells": cells, "start": start, "end": end})
        if self.error is not None:
            raise self.error
        hours = range(start, end + 1, HOUR)
        result = {}
        for lat, lon in cells:
            rows = [self.conditions(lat, lon, t) for t in hours]
            result[(lat, lon)] = HourlySeries(
                start=start,
                wind_mph=[r[0] for r in rows],
                gust_mph=[r[1] for r in rows],
                rain_in_hr=[r[2] for r in rows],
                snow_in_hr=[r[3] for r in rows],
            )
        return result
