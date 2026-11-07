"""Tests for the HTTP API: request checks, response shapes and error format.
Planning itself is covered in test_service.py; here the outside services are fakes."""

from datetime import UTC, datetime

import pytest
from rest_framework.test import APIClient

from planner import views
from planner.clients.errors import ServiceBusy
from planner.clients.ors import Place
from planner.tests.fakes import FakeOrs, FakeWeather

GOOD_TRIP = {
    "origin": {"lat": 40.0, "lon": -105.0, "label": "Somewhere, CO"},
    "destination": {"lat": 40.0, "lon": -103.0, "label": "Elsewhere, CO"},
    "departure": "2030-01-01T08:00",
    "load_lb": 20_000,
    "interval_mi": 25,
}


class PlacesOrs(FakeOrs):
    """A fake ORS that also answers place searches."""

    def __init__(self, places=None, error=None):
        super().__init__()
        self.places = places or []
        self.search_error = error
        self.searches = []

    def autocomplete(self, text, focus=None, size=5):
        self.searches.append({"text": text, "focus": focus})
        if self.search_error:
            raise self.search_error
        return self.places


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def fake_clients(monkeypatch):
    """Swap the real clients for fakes for one test."""

    def install(ors=None, weather=None):
        ors, weather = ors or PlacesOrs(), weather or FakeWeather()
        monkeypatch.setattr(views, "clients", lambda: (ors, weather))
        return ors, weather

    return install


@pytest.fixture
def fixed_now(monkeypatch):
    """Plans run as if it were 2030-01-01 12:00 UTC, so GOOD_TRIP's departure is valid."""
    real = views.plan_trip
    monkeypatch.setattr(
        views,
        "plan_trip",
        lambda req, ors, wx: real(req, ors, wx, now=datetime(2030, 1, 1, 12, tzinfo=UTC)),
    )


# --- Health ------------------------------------------------------------------


def test_health_answers_ok(api):
    """#58: the page pings this to wake the free server."""
    response = api.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- Plan --------------------------------------------------------------------


def test_a_good_trip_returns_routes_and_a_recommendation(api, fake_clients, fixed_now):
    """The happy path through HTTP."""
    fake_clients()
    response = api.post("/api/plan", GOOD_TRIP, format="json")
    assert response.status_code == 200
    body = response.json()
    assert body["recommended"] == "A"
    assert [r["id"] for r in body["routes"]] == ["A", "B", "C"]


def test_missing_fields_come_back_named_for_the_form(api, fake_clients):
    """Bad input uses the same error shape as every other problem."""
    fake_clients()
    response = api.post(
        "/api/plan", {k: v for k, v in GOOD_TRIP.items() if k != "destination"}, format="json"
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "invalid_input"
    assert "destination" in body["fields"]


@pytest.mark.parametrize(
    "field, value",
    [
        ("departure", "2030-01-01T08:00+05:00"),  # #7: local time, no zone
        ("departure", "tomorrow morning"),
        ("interval_mi", 30),  # #1: 10, 25 or 50 only
        ("load_lb", -1),
        ("load_lb", 1_500_000),  # #2: an extra zero or two
    ],
)
def test_out_of_range_values_are_refused(api, fake_clients, field, value):
    """Each one names the field that needs fixing."""
    fake_clients()
    response = api.post("/api/plan", {**GOOD_TRIP, field: value}, format="json")
    assert response.status_code == 400
    assert field in response.json()["fields"]


def test_departure_is_optional_and_means_now(api, fake_clients, fixed_now):
    """#10: the form's default 'Leave now' sends no departure."""
    fake_clients()
    trip = {k: v for k, v in GOOD_TRIP.items() if k != "departure"}
    response = api.post("/api/plan", trip, format="json")
    assert response.status_code == 200
    assert response.json()["departure"].startswith("2030-01-01T05:00")


def test_interval_defaults_to_25_miles(api, fake_clients, fixed_now):
    """#1: the toggle is optional."""
    fake_clients()
    trip = {k: v for k, v in GOOD_TRIP.items() if k != "interval_mi"}
    response = api.post("/api/plan", trip, format="json")
    assert response.status_code == 200
    miles = [c["mile"] for c in response.json()["routes"][0]["checkpoints"]]
    assert miles[1] == 25


def test_plan_problems_keep_their_status_message_and_actions(api, fake_clients, fixed_now):
    """#59: a busy routing service is a 503 with a retry button."""
    fake_clients(ors=FakeOrs(error=ServiceBusy("routing service")))
    response = api.post("/api/plan", GOOD_TRIP, format="json")
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "routing_busy"
    assert body["actions"][0]["type"] == "retry"


def test_an_unexpected_crash_is_a_friendly_500(api, monkeypatch, fake_clients):
    """#59: even a bug shows a plain message and Try again, never a stack trace."""
    fake_clients()

    def broken(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(views, "plan_trip", broken)
    response = api.post("/api/plan", GOOD_TRIP, format="json")
    assert response.status_code == 500
    assert response.json()["error"] == "server_error"
    assert "Your trip details are kept" in response.json()["message"]


def test_without_an_api_key_the_server_says_it_isnt_set_up(api, settings):
    """A missing ORS key is a clear 503, not a crash."""
    settings.ORS_API_KEY = ""
    views.clients.cache_clear()
    try:
        response = api.post("/api/plan", GOOD_TRIP, format="json")
    finally:
        views.clients.cache_clear()
    assert response.status_code == 503
    assert response.json()["error"] == "server_not_configured"


# --- Places ------------------------------------------------------------------


def test_places_returns_labelled_coordinates_ranked_near_the_map(api, fake_clients):
    """#4: suggestions are biased to where the map is looking."""
    ors, _ = fake_clients(ors=PlacesOrs(places=[Place("Denver, CO, USA", 39.74, -104.99)]))
    response = api.get("/api/places", {"q": "denv", "lat": 39.7, "lon": -105.0})
    assert response.status_code == 200
    assert response.json() == [{"label": "Denver, CO, USA", "lat": 39.74, "lon": -104.99}]
    assert ors.searches[0]["focus"] == (39.7, -105.0)


def test_places_needs_at_least_two_letters(api, fake_clients):
    """One letter would return noise and waste quota."""
    fake_clients()
    response = api.get("/api/places", {"q": "d"})
    assert response.status_code == 400
    assert "q" in response.json()["fields"]


def test_a_busy_search_service_is_a_friendly_503(api, fake_clients):
    """Same error shape as plans."""
    fake_clients(ors=PlacesOrs(error=ServiceBusy("routing service")))
    response = api.get("/api/places", {"q": "denver"})
    assert response.status_code == 503
    assert response.json()["error"] == "routing_busy"
