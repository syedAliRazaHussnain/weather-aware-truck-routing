"""Tests for planner.service: the whole plan with fake ORS and weather services.
Comments like "#10" point to README assumptions."""

from datetime import UTC, datetime

import pytest

from planner import service
from planner.clients.errors import (
    MissingWeather,
    NoRoadNearby,
    ServiceBusy,
    ServiceUnavailable,
    TripTooLong,
)
from planner.clients.ors import Place
from planner.service import PlanProblem, TripRequest, plan_trip
from planner.tests.fakes import FakeOrs, FakeWeather, straight_route

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)  # 05:00 in Denver (MST, UTC-7)
WEST, EAST = (40.0, -105.0), (40.0, -103.0)  # ~106 mi, starting in Colorado


def trip(
    departure="2026-11-07T08:00", load_lb=20_000, interval_mi=25, origin=WEST, destination=EAST
):
    """A trip request with sensible defaults."""
    return TripRequest(
        origin=origin,
        destination=destination,
        departure_local=datetime.fromisoformat(departure) if departure else None,
        load_lb=load_lb,
        interval_mi=interval_mi,
    )


def plan(request=None, ors=None, weather=None):
    """Plan with fakes, at a fixed 'now'."""
    return plan_trip(request or trip(), ors or FakeOrs(), weather or FakeWeather(), now=NOW)


def problem_from(request=None, ors=None, weather=None) -> PlanProblem:
    """The PlanProblem a plan raises."""
    with pytest.raises(PlanProblem) as caught:
        plan(request, ors, weather)
    return caught.value


# --- A normal plan -----------------------------------------------------------


def test_a_calm_trip_gives_three_routes_named_fastest_first():
    """#60: A is the fastest; with no risk anywhere, A wins on time."""
    result = plan()
    durations = [r["duration_s"] for r in result["routes"]]
    assert [r["id"] for r in result["routes"]] == ["A", "B", "C"]
    assert durations == sorted(durations)
    assert result["recommended"] == "A"
    assert result["reason"] == "Same risk as Route B, and it's the fastest route."
    assert result["weather_status"] == "ok"


def test_times_are_in_the_origins_local_zone():
    """#7, #8: 8:00 typed for a Colorado origin means 8:00 MST, and ETAs say so."""
    result = plan()
    assert result["timezone"] == "America/Denver"
    assert result["departure"] == "2026-11-07T08:00-07:00"
    assert result["routes"][0]["checkpoints"][0]["eta"] == "2026-11-07T08:00-07:00"


def test_gross_weight_sent_to_routing_is_load_plus_empty_truck():
    """#13: 20,000 lb of cargo is an 55,000 lb truck."""
    ors = FakeOrs()
    plan(ors=ors)
    assert ors.route_calls[0]["gross_lb"] == 55_000


def test_route_lines_are_geojson_lon_lat_and_join_same_coloured_stretches():
    """A calm route is one Low stretch from the first mile to the last."""
    route = plan()["routes"][0]
    features = route["segments"]["features"]
    assert len(features) == 1
    assert features[0]["properties"]["level"] == 0
    assert features[0]["properties"]["to_mi"] == pytest.approx(route["distance_mi"], abs=0.1)
    lon, lat = features[0]["geometry"]["coordinates"][0]
    assert (lat, lon) == WEST


def test_heatmap_has_49_hourly_levels_per_square_from_departure():
    """#47, #48: hour 0 is the departure hour."""
    heatmap = plan()["heatmap"]
    assert heatmap["start"] == "2026-11-07T08:00-07:00"
    props = heatmap["cells"]["features"][0]["properties"]
    assert set(props) == {f"h{h}" for h in range(49)}


def test_weather_window_covers_48_hours_from_departure():
    """#11: enough forecast for the whole slider."""
    weather = FakeWeather()
    plan(weather=weather)
    fetched = weather.fetched[0]
    assert fetched["end"] - fetched["start"] == 48 * 3600


def test_one_plan_never_asks_for_more_than_the_weather_budget():
    """#37: at most 500 locations per plan."""
    weather = FakeWeather()
    plan(weather=weather)
    assert len(weather.fetched[0]["cells"]) <= service.WEATHER_BUDGET


# --- Weather changes the recommendation --------------------------------------


def storm_in_the_middle(lat, lon, unix_time):
    """Heavy rain (Severe) only on the straight road, mid-trip."""
    if 39.95 < lat < 40.05 and -104.3 < lon < -103.7:
        return 5.0, 8.0, 0.6, 0.0
    return 5.0, 8.0, 0.0, 0.0


def test_a_storm_on_the_fastest_road_moves_the_recommendation():
    """#41: Route A drives through Severe rain, so a detour without it wins."""
    result = plan(weather=FakeWeather(storm_in_the_middle))
    route_a = result["routes"][0]
    assert route_a["summary"]["severe_mi"] > 0
    assert result["recommended"] != "A"
    assert "Severe miles vs" in result["reason"]
    assert "slower than the fastest" in result["reason"]


def windy(lat, lon, unix_time):
    """40 mph everywhere: High on its own."""
    return 40.0, 50.0, 0.0, 0.0


def test_a_heavy_load_raises_wind_risk_and_the_popup_says_so():
    """#33: 40 mph is High empty, Severe above 40,000 lb."""
    light = plan(trip(load_lb=10_000), weather=FakeWeather(windy))
    heavy = plan(trip(load_lb=42_000), weather=FakeWeather(windy))
    assert light["routes"][0]["checkpoints"][1]["label"] == "High"
    checkpoint = heavy["routes"][0]["checkpoints"][1]
    assert checkpoint["label"] == "Severe"
    assert checkpoint["load_escalated"] is True
    assert checkpoint["wind_before_load"] == "High"
    assert checkpoint["drivers"] == ["wind"]


def test_every_route_no_travel_still_recommends_one_and_offers_tomorrow():
    """#45: 60 mph everywhere: a warning and [Check tomorrow 6 AM]."""
    result = plan(weather=FakeWeather(lambda lat, lon, t: (60.0, 70.0, 0.0, 0.0)))
    assert result["recommended"] == "A"
    action = result["warning"]["actions"][0]
    assert (action["label"], action["value"]) == ("Check tomorrow 6 AM", "2026-11-08T06:00")


# --- Departure checks ---------------------------------------------------------


def test_a_departure_more_than_an_hour_ago_offers_leave_now():
    """#10: 03:00 when it's 05:00 local: [Leave now] sets the current local time."""
    problem = problem_from(trip(departure="2026-11-07T03:00"))
    assert problem.code == "departure_passed"
    assert problem.actions == [
        {"type": "set_departure", "value": "2026-11-07T05:00", "label": "Leave now"}
    ]


def test_no_departure_means_leave_now_at_the_origin():
    """#10: 'Leave now' is now in the origin's zone, whatever the browser's clock says."""
    assert plan(trip(departure=None))["departure"] == "2026-11-07T05:00-07:00"


def test_a_departure_less_than_an_hour_ago_is_accepted():
    """#10: the 1-hour grace for filling in the form."""
    assert plan(trip(departure="2026-11-07T04:30"))["weather_status"] == "ok"


def test_a_departure_past_the_forecast_offers_the_latest_possible_date():
    """#11: the forecast ends 2026-11-22 23:00 UTC, so with 48 h of slider the latest
    departure is 2026-11-20 23:00 UTC = 16:00 in Denver."""
    problem = problem_from(trip(departure="2026-11-21T08:00"))
    assert problem.code == "beyond_forecast"
    assert problem.actions[0]["value"] == "2026-11-20T16:00"


def test_origin_and_destination_cannot_be_the_same_place():
    """A zero-length trip has nothing to plan."""
    assert problem_from(trip(destination=WEST)).code == "same_place"


# --- Routing problems ---------------------------------------------------------


def test_no_road_near_the_destination_suggests_the_nearest_town():
    """#59: [Use Rawlins, WY (N mi away)] fills in the destination."""
    ors = FakeOrs(error=NoRoadNearby(1), nearest=Place("Rawlins, WY, USA", 40.0, -103.1))
    problem = problem_from(ors=ors)
    assert problem.code == "no_road_nearby"
    assert problem.message == "There's no truck road near your destination."
    use = problem.actions[0]
    assert (use["type"], use["field"]) == ("use_place", "destination")
    assert use["label"].startswith("Use Rawlins, WY, USA (")


def test_a_trip_over_the_routing_limit_suggests_two_legs():
    """#61."""
    problem = problem_from(ors=FakeOrs(error=TripTooLong("over 6,000 km")))
    assert problem.code == "trip_too_long"
    assert "two legs" in problem.actions[0]["label"]
    assert "crosses the sea" in problem.message


def test_a_busy_routing_service_offers_a_retry_countdown():
    """#59: 503 with a 60 s countdown."""
    problem = problem_from(ors=FakeOrs(error=ServiceBusy("routing service")))
    assert (problem.code, problem.status) == ("routing_busy", 503)
    assert problem.actions[0]["retry_after_s"] == 60


def test_fewer_than_three_distinct_routes_are_shown_with_a_note():
    """#15: every detour comes back as the same road."""
    result = plan(ors=FakeOrs(ignore_via=True))
    assert len(result["routes"]) == 1
    assert "Only 1 different route found for this trip." in result["notes"]


def test_short_trips_use_ors_alternatives_first():
    """#14: under ~90 km, ORS's own alternatives, no detour calls."""
    a, b = (40.0, -105.0), (40.0, -104.6)  # ~21 mi
    alternatives = [straight_route([a, b]), straight_route([a, (40.15, -104.8), b])]
    ors = FakeOrs(alternatives=alternatives)
    result = plan(trip(origin=a, destination=b), ors=ors)
    assert ors.alternative_calls == 1
    assert ors.route_calls == []
    assert len(result["routes"]) == 2


def test_short_trips_fall_back_to_detours_if_ors_refuses_alternatives():
    """#14: ORS's limit is approximate, so a refusal isn't an error."""
    a, b = (40.0, -105.0), (40.0, -104.6)
    ors = FakeOrs(alternatives=None)
    plan(trip(origin=a, destination=b), ors=ors)
    assert ors.alternative_calls == 1
    assert len(ors.route_calls) > 1


# --- Weather problems ---------------------------------------------------------


def test_weather_unavailable_still_shows_routes_as_unknown_never_low():
    """#39: routes, distances and times, but no levels, no ranking, and Try again."""
    result = plan(weather=FakeWeather(error=ServiceUnavailable("weather service")))
    assert result["weather_status"] == "unavailable"
    assert result["recommended"] is None
    assert result["heatmap"] is None
    route = result["routes"][0]
    assert route["summary"] is None and route["rank"] is None
    assert route["checkpoints"][0]["level"] is None
    assert route["checkpoints"][0]["label"] == "Weather unknown"
    assert route["segments"]["features"][0]["properties"]["level"] is None
    assert result["problem"]["error"] == "weather_unavailable"
    assert result["problem"]["actions"][0]["type"] == "retry"


def test_empty_forecast_values_are_treated_as_unknown():
    """#39: MissingWeather behaves like an outage, not like calm weather."""
    result = plan(weather=FakeWeather(error=MissingWeather("empty")))
    assert result["weather_status"] == "unavailable"


def test_a_busy_weather_service_offers_a_countdown():
    """#39: rate limit: retry in 60 s."""
    result = plan(weather=FakeWeather(error=ServiceBusy("weather service")))
    assert result["problem"]["error"] == "weather_busy"
    assert result["problem"]["actions"][0]["retry_after_s"] == 60


def test_too_many_checkpoints_offers_bigger_intervals(monkeypatch):
    """#37: with a tiny budget, 10 mi checkpoints don't fit: [Use 25 mi] [Use 50 mi]."""
    monkeypatch.setattr(service, "WEATHER_BUDGET", 5)
    problem = problem_from(trip(interval_mi=10))
    assert problem.code == "too_many_checkpoints"
    assert [a["value"] for a in problem.actions] == [25, 50]


# --- Notes --------------------------------------------------------------------


def test_long_trips_note_that_etas_have_no_rest_stops():
    """#24: over 11 h of driving."""
    result = plan(ors=FakeOrs(mph=8))  # ~106 mi at 8 mph is ~13 h
    assert any("no rest stops" in note for note in result["notes"])


def test_short_trips_have_no_rest_stop_note():
    """#24: a 2-hour trip doesn't need it."""
    assert not any("no rest stops" in note for note in plan()["notes"])
