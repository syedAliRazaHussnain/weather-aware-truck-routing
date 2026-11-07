"""OpenRouteService client: truck routes, place search and nearest-place lookup.

The API key is sent in a header (never in a URL) and never leaves the server.
ORS speaks GeoJSON, which puts longitude first; everything leaving this module is
(lat, lon). Comments like "#14" point to the numbered assumptions in the README.
"""

import re
from dataclasses import dataclass

import requests

from planner.clients.errors import (
    AlternativesNotAllowed,
    NoRoadNearby,
    NoTruckRoute,
    ServiceBusy,
    ServiceUnavailable,
    TripTooLong,
)
from planner.geo import Point, Step
from planner.routes import Route

BASE_URL = "https://api.openrouteservice.org"
SERVICE = "routing service"
LB_PER_TONNE = 2204.62  # ORS takes weight limits in metric tonnes
END_RADIUS_M = 5_000  # #6: origin and destination snap to a truck road within 5 km
VIA_RADIUS_M = 20_000  # #14: detour points snap within 20 km
TIMEOUT_S = 20


@dataclass(frozen=True)
class Place:
    """A search result the driver can pick: its name and position."""

    label: str
    lat: float
    lon: float


def parse_route(feature: dict) -> Route:
    """One ORS GeoJSON route as a Route with (lat, lon) points and global step indexes."""
    path = [(lat, lon) for lon, lat, *_ in feature["geometry"]["coordinates"]]
    steps = [
        Step(start=s["way_points"][0], end=s["way_points"][1], seconds=s.get("duration", 0.0))
        for segment in feature["properties"]["segments"]
        for s in segment["steps"]
    ]
    return Route(
        path=path, steps=steps, seconds=feature["properties"]["summary"].get("duration", 0.0)
    )


def raise_for_ors_error(status: int, body: dict) -> None:
    """Turn an ORS error answer into the matching ClientError."""
    error = body.get("error") if isinstance(body, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    message = error.get("message", "") if isinstance(error, dict) else ""
    if status == 429:
        raise ServiceBusy(SERVICE)
    if code == 2010:  # "Could not find routable point ... of specified coordinate 1"
        found = re.search(r"coordinate (\d+)", message)
        raise NoRoadNearby(int(found.group(1)) if found else 0)
    if code == 2009:
        raise NoTruckRoute(message)
    if code == 2004 and "alternative" in message.lower():
        raise AlternativesNotAllowed(message)
    if code == 2004:  # "approximated route distance must not be greater than 6000000.0 meters"
        raise TripTooLong(message)
    raise ServiceUnavailable(SERVICE)


class OrsClient:
    """Calls OpenRouteService with the server's API key."""

    def __init__(self, api_key: str, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._headers = {"Authorization": api_key}

    def _send(self, method: str, path: str, **kwargs) -> dict:
        """One request, retried once on a timeout or server error; errors become ClientErrors."""
        for attempt in (1, 2):
            try:
                response = self._session.request(
                    method, BASE_URL + path, headers=self._headers, timeout=TIMEOUT_S, **kwargs
                )
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise ServiceUnavailable(SERVICE) from None
                continue
            if response.status_code >= 500 and attempt == 1:
                continue
            try:
                body = response.json()
            except ValueError:
                raise ServiceUnavailable(SERVICE) from None
            if response.status_code != 200:
                raise_for_ors_error(response.status_code, body)
            return body
        raise ServiceUnavailable(SERVICE)

    def _directions(self, points: list[Point], gross_lb: float, **extra) -> list[Route]:
        """Truck directions through the given points, as parsed routes."""
        body = {
            "coordinates": [[lon, lat] for lat, lon in points],
            "units": "mi",
            "instructions": True,
            "options": {
                "vehicle_type": "hgv",
                # #13: gross weight lets ORS avoid weight-restricted roads.
                "profile_params": {"restrictions": {"weight": round(gross_lb / LB_PER_TONNE, 1)}},
            },
            **extra,
        }
        answer = self._send("POST", "/v2/directions/driving-hgv/geojson", json=body)
        return [parse_route(feature) for feature in answer["features"]]

    def truck_route(self, points: list[Point], gross_lb: float) -> Route:
        """The fastest truck route through the points (origin, optional via, destination)."""
        radiuses = [END_RADIUS_M] + [VIA_RADIUS_M] * (len(points) - 2) + [END_RADIUS_M]
        return self._directions(points, gross_lb, radiuses=radiuses)[0]

    def truck_alternatives(self, origin: Point, destination: Point, gross_lb: float) -> list[Route]:
        """Up to 3 routes from ORS's own alternatives (short trips only, #14)."""
        return self._directions(
            [origin, destination],
            gross_lb,
            radiuses=[END_RADIUS_M, END_RADIUS_M],
            alternative_routes={"target_count": 3, "share_factor": 0.6, "weight_factor": 1.5},
        )

    def autocomplete(self, text: str, focus: Point | None = None, size: int = 5) -> list[Place]:
        """Place suggestions for what the driver is typing, ranked near `focus` (#4)."""
        params = {"text": text, "size": size}
        if focus is not None:
            params["focus.point.lat"], params["focus.point.lon"] = focus
        answer = self._send("GET", "/geocode/autocomplete", params=params)
        return [_place(f) for f in answer.get("features", [])]

    def nearest_place(self, point: Point) -> Place | None:
        """The nearest town to a point, to suggest when a point has no road nearby."""
        params = {"point.lat": point[0], "point.lon": point[1], "size": 1, "layers": "locality"}
        features = self._send("GET", "/geocode/reverse", params=params).get("features", [])
        return _place(features[0]) if features else None


def _place(feature: dict) -> Place:
    """A geocoding result as a Place."""
    lon, lat = feature["geometry"]["coordinates"][:2]
    return Place(label=feature["properties"].get("label", ""), lat=lat, lon=lon)
