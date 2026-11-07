"""Tests for planner.clients.ors, using saved ORS answers instead of the network.
Error bodies in tests/fixtures are real ORS responses; the route is a small one
in the exact shape of a real driving-hgv answer."""

import pytest

from planner.clients.errors import (
    AlternativesNotAllowed,
    NoRoadNearby,
    NoTruckRoute,
    ServiceBusy,
    ServiceUnavailable,
    TripTooLong,
)
from planner.clients.ors import END_RADIUS_M, VIA_RADIUS_M, OrsClient, Place, parse_route
from planner.geo import Step
from planner.tests.fakes import TIMEOUT, FakeResponse, FakeSession, fixture

DENVER = (39.7392, -104.9903)
SALT_LAKE_CITY = (40.7608, -111.8910)


def client_with(*answers):
    """An OrsClient whose HTTP answers come from a queue."""
    session = FakeSession(*answers)
    return OrsClient(api_key="test-key", session=session), session


# --- Parsing a route ---------------------------------------------------------


def test_route_points_are_turned_into_lat_lon():
    """ORS sends [lon, lat]; everything after the client is (lat, lon)."""
    route = parse_route(fixture("ors_route_via.json")["features"][0])
    assert route.path[0] == (39.7, -105.0)
    assert route.path[-1] == (39.9, -104.8)


def test_steps_from_every_segment_keep_their_global_indexes():
    """A via point splits the route into 2 segments; step indexes run across both."""
    route = parse_route(fixture("ors_route_via.json")["features"][0])
    assert route.steps == [Step(0, 2, 600), Step(2, 2, 0), Step(2, 3, 420), Step(3, 3, 0)]


def test_route_time_is_the_ors_total():
    """Driving time for the whole route comes from the summary."""
    assert parse_route(fixture("ors_route_via.json")["features"][0]).seconds == 1020


# --- Asking for a truck route ------------------------------------------------


def test_truck_route_request_is_a_truck_with_its_gross_weight():
    """#13: 77,000 lb gross is sent as 34.9 tonnes, so ORS can avoid weight limits."""
    client, session = client_with(FakeResponse(200, fixture("ors_route_via.json")))
    client.truck_route([DENVER, SALT_LAKE_CITY], gross_lb=77_000)
    body = session.calls[0]["json"]
    assert body["options"]["vehicle_type"] == "hgv"
    assert body["options"]["profile_params"]["restrictions"]["weight"] == 34.9
    assert body["coordinates"][0] == [-104.9903, 39.7392]  # back to [lon, lat] for ORS


def test_ends_snap_within_5_km_and_detour_points_within_20_km():
    """#6, #14: a via point gets a wider snapping radius than origin and destination."""
    client, session = client_with(FakeResponse(200, fixture("ors_route_via.json")))
    client.truck_route([DENVER, (40.0, -108.0), SALT_LAKE_CITY], gross_lb=60_000)
    assert session.calls[0]["json"]["radiuses"] == [END_RADIUS_M, VIA_RADIUS_M, END_RADIUS_M]


def test_the_api_key_goes_in_a_header_not_the_url():
    """Keys in URLs end up in logs; a header doesn't."""
    client, session = client_with(FakeResponse(200, fixture("ors_route_via.json")))
    client.truck_route([DENVER, SALT_LAKE_CITY], gross_lb=60_000)
    assert session.calls[0]["headers"]["Authorization"] == "test-key"
    assert "test-key" not in session.calls[0]["url"]


def test_alternatives_ask_ors_for_three_routes():
    """#14: short trips use ORS's own alternatives."""
    client, session = client_with(FakeResponse(200, fixture("ors_route_via.json")))
    client.truck_alternatives(DENVER, SALT_LAKE_CITY, gross_lb=60_000)
    assert session.calls[0]["json"]["alternative_routes"]["target_count"] == 3


# --- Errors, using real ORS error answers ------------------------------------


def test_no_road_near_a_point_says_which_point():
    """Real answer for a point in the Pacific: code 2010, 'specified coordinate 1'."""
    client, _ = client_with(FakeResponse(404, fixture("ors_error_no_road.json")))
    with pytest.raises(NoRoadNearby) as caught:
        client.truck_route([DENVER, (38.0, -125.5)], gross_lb=60_000)
    assert caught.value.index == 1


def test_a_trip_over_the_free_distance_limit_is_too_long():
    """#61: real answer for Lahore to London (over 6,000 km)."""
    client, _ = client_with(FakeResponse(400, fixture("ors_error_too_long.json")))
    with pytest.raises(TripTooLong):
        client.truck_route([(31.52, 74.36), (51.51, -0.13)], gross_lb=60_000)


def test_alternatives_refused_for_a_long_trip_are_reported_separately():
    """#14: real answer when alternatives are asked for over 100 km; the caller falls
    back to detour points instead of failing the plan."""
    client, _ = client_with(FakeResponse(400, fixture("ors_error_alternatives.json")))
    with pytest.raises(AlternativesNotAllowed):
        client.truck_alternatives(DENVER, SALT_LAKE_CITY, gross_lb=60_000)


def test_no_truck_route_between_two_roads():
    """Code 2009: both ends are on roads but nothing truck-legal joins them."""
    body = {"error": {"code": 2009, "message": "Route could not be found"}}
    client, _ = client_with(FakeResponse(404, body))
    with pytest.raises(NoTruckRoute):
        client.truck_route([DENVER, SALT_LAKE_CITY], gross_lb=60_000)


def test_rate_limiting_is_not_retried():
    """Retrying a 429 straight away only makes it worse."""
    client, session = client_with(FakeResponse(429, {"error": "Rate limit exceeded"}))
    with pytest.raises(ServiceBusy):
        client.truck_route([DENVER, SALT_LAKE_CITY], gross_lb=60_000)
    assert len(session.calls) == 1


def test_a_timeout_is_retried_once():
    """#61: one retry, then success."""
    client, session = client_with(TIMEOUT, FakeResponse(200, fixture("ors_route_via.json")))
    assert client.truck_route([DENVER, SALT_LAKE_CITY], gross_lb=60_000).seconds == 1020
    assert len(session.calls) == 2


def test_two_server_errors_mean_unavailable():
    """#61: a 5xx, a retry, another 5xx: give up with a clear error."""
    client, session = client_with(FakeResponse(502, {}), FakeResponse(503, {}))
    with pytest.raises(ServiceUnavailable):
        client.truck_route([DENVER, SALT_LAKE_CITY], gross_lb=60_000)
    assert len(session.calls) == 2


def test_an_answer_that_is_not_json_means_unavailable():
    """An HTML error page from a proxy isn't a route."""
    client, _ = client_with(FakeResponse(200, ValueError("not json")))
    with pytest.raises(ServiceUnavailable):
        client.truck_route([DENVER, SALT_LAKE_CITY], gross_lb=60_000)


# --- Place search ------------------------------------------------------------


def test_autocomplete_returns_labelled_places_in_lat_lon():
    """Real answer for 'springfield' searched from Denver."""
    client, session = client_with(FakeResponse(200, fixture("ors_autocomplete.json")))
    places = client.autocomplete("springfield", focus=DENVER)
    assert places[0] == Place(label="Springfield, MO, USA", lat=37.197274, lon=-93.28074)
    assert session.calls[0]["params"]["focus.point.lat"] == DENVER[0]


def test_nearest_place_names_the_closest_town():
    """Real answer near Rawlins, WY: used for 'Use Rawlins, WY (3 mi away)'."""
    client, _ = client_with(FakeResponse(200, fixture("ors_reverse.json")))
    assert client.nearest_place((41.79, -107.24)).label == "Rawlins, WY, USA"


def test_nearest_place_is_none_when_nothing_is_found():
    """Middle of the ocean: no town to suggest."""
    client, _ = client_with(FakeResponse(200, {"features": []}))
    assert client.nearest_place((0.0, -140.0)) is None
