"""Tests for planner.clients.weather, using saved Open-Meteo answers instead of the
network. tests/fixtures/openmeteo_two_locations.json is a real 49-hour answer for
Denver and Salt Lake City. Comments like "#36" point to README assumptions."""

from datetime import UTC, datetime

import pytest

from planner.clients.errors import MissingWeather, ServiceBusy, ServiceUnavailable
from planner.clients.weather import (
    HOUR,
    HourlySeries,
    TTLCache,
    WeatherClient,
    grid_cell,
    last_forecast_hour,
    parse_series,
)
from planner.tests.fakes import TIMEOUT, FakeResponse, fixture

START = 1_794_052_800  # 2026-11-07 12:00 UTC, the first hour in the fixture
END = START + 48 * HOUR


def synthetic_answer(params):
    """An Open-Meteo-shaped answer with 3 calm hours for every location asked for."""
    count = len(params["latitude"].split(","))
    hourly = {
        "time": [START, START + HOUR, START + 2 * HOUR],
        "wind_speed_10m": [5.0, 6.0, 7.0],
        "wind_gusts_10m": [9.0, 10.0, 11.0],
        "rain": [0.0, 0.1, 0.0],
        "showers": [0.0, 0.05, 0.0],
        "snowfall": [0.0, 0.0, 0.0],
    }
    locations = [{"hourly": hourly} for _ in range(count)]
    return locations if count > 1 else locations[0]  # Open-Meteo: one location isn't a list


class FakeGet:
    """Stands in for requests.get: answers from a queue, or synthesises answers."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, url, params, timeout):
        self.calls.append(params)
        if not self.answers:
            return FakeResponse(200, synthetic_answer(params))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


# --- Grid cells and the forecast horizon -------------------------------------


@pytest.mark.parametrize("step, expected", [(0.05, (39.75, -105.0)), (0.1, (39.7, -105.0))])
def test_points_round_to_the_weather_grid(step, expected):
    """#36: Denver rounds to the nearest 0.05 or 0.1 degree."""
    assert grid_cell((39.7392, -104.9903), step) == expected


def test_nearby_points_share_one_cell():
    """#36: two points a few hundred metres apart need only one forecast."""
    assert grid_cell((39.7392, -104.9903), 0.1) == grid_cell((39.7411, -104.9871), 0.1)


def test_forecast_ends_at_the_end_of_the_16th_day_utc():
    """#11: checked against Open-Meteo, which allows up to 2026-11-22 for a Nov 7 request."""
    now = datetime(2026, 11, 7, 12, 30, tzinfo=UTC)
    assert datetime.fromtimestamp(last_forecast_hour(now), UTC) == datetime(
        2026, 11, 22, 23, 0, tzinfo=UTC
    )


# --- Reading a forecast ------------------------------------------------------


def test_a_real_answer_parses_into_49_hours():
    """The real fixture: 49 hours from 12:00 UTC."""
    series = parse_series(fixture("openmeteo_two_locations.json")[0])
    assert series.start == START
    assert len(series.wind_mph) == 49


def test_rain_is_rain_plus_showers():
    """#28: Open-Meteo reports showers separately; both are rain on the road."""
    series = parse_series(synthetic_answer({"latitude": "1"}))
    assert series.rain_in_hr[1] == pytest.approx(0.15)


def test_empty_values_are_an_error_not_calm_weather():
    """#39: a missing number must never be read as Low."""
    location = synthetic_answer({"latitude": "1"})
    location["hourly"]["snowfall"][2] = None
    with pytest.raises(MissingWeather):
        parse_series(location)


def test_weather_is_taken_from_the_nearest_hour():
    """#22: 12:29 uses the 12:00 forecast, 12:31 uses 13:00."""
    series = parse_series(synthetic_answer({"latitude": "1"}))
    assert series.weather_at(START + 29 * 60).wind_mph == 5.0
    assert series.weather_at(START + 31 * 60).wind_mph == 6.0
    assert series.gust_at(START + 31 * 60) == 10.0


def test_a_time_outside_the_forecast_is_an_error():
    """Asking for an hour we didn't fetch is a bug upstream, not calm weather."""
    series = parse_series(synthetic_answer({"latitude": "1"}))
    with pytest.raises(MissingWeather):
        series.weather_at(START + 10 * HOUR)


def test_hours_from_gives_consecutive_hours_for_the_heatmap():
    """#48: the slider reads consecutive hours starting at departure."""
    series = HourlySeries(START, [1, 2, 3, 4], [0] * 4, [0] * 4, [0] * 4)
    assert [w.wind_mph for w in series.hours_from(START + HOUR, 3)] == [2, 3, 4]


# --- Fetching ----------------------------------------------------------------


def test_request_asks_for_spec_units_in_utc():
    """#9: mph, inches and Unix time in UTC, so nothing needs converting."""
    get = FakeGet()
    WeatherClient(http_get=get).fetch([(39.75, -105.0)], START, START + 2 * HOUR)
    params = get.calls[0]
    assert (params["wind_speed_unit"], params["precipitation_unit"]) == ("mph", "inch")
    assert (params["timeformat"], params["timezone"]) == ("unixtime", "GMT")
    assert (params["start_hour"], params["end_hour"]) == ("2026-11-07T12:00", "2026-11-07T14:00")


def test_a_real_two_location_answer_maps_to_the_right_cells():
    """The real fixture's first location is Denver's cell, the second Salt Lake City's."""
    denver, slc = (39.75, -105.0), (40.75, -111.9)
    get = FakeGet(FakeResponse(200, fixture("openmeteo_two_locations.json")))
    result = WeatherClient(http_get=get).fetch([denver, slc], START, END)
    assert set(result) == {denver, slc}
    assert len(result[slc].wind_mph) == 49


def test_150_cells_take_two_requests_of_100_and_50():
    """Batches of 100 locations per request."""
    get = FakeGet()
    cells = [(float(i), 0.0) for i in range(150)]
    result = WeatherClient(http_get=get).fetch(cells, START, START + 2 * HOUR)
    assert len(result) == 150
    assert sorted(len(c["latitude"].split(",")) for c in get.calls) == [50, 100]


def test_the_same_cell_is_only_fetched_once():
    """#37: duplicates cost nothing extra."""
    get = FakeGet()
    WeatherClient(http_get=get).fetch([(1.0, 2.0), (1.0, 2.0), (3.0, 4.0)], START, START + 2 * HOUR)
    assert get.calls[0]["latitude"] == "1.0,3.0"


def test_a_repeat_within_an_hour_comes_from_the_cache():
    """#38: re-planning the same trip (e.g. a different load) makes no weather calls."""
    get = FakeGet()
    client = WeatherClient(http_get=get)
    client.fetch([(1.0, 2.0)], START, START + 2 * HOUR)
    client.fetch([(1.0, 2.0)], START, START + 2 * HOUR)
    assert len(get.calls) == 1


def test_the_cache_expires_after_an_hour():
    """#38: forecasts update about hourly, so older ones are fetched again."""
    now = [0.0]
    get = FakeGet()
    client = WeatherClient(http_get=get, cache=TTLCache(seconds=3600, clock=lambda: now[0]))
    client.fetch([(1.0, 2.0)], START, START + 2 * HOUR)
    now[0] = 3601
    client.fetch([(1.0, 2.0)], START, START + 2 * HOUR)
    assert len(get.calls) == 2


# --- Errors ------------------------------------------------------------------


def test_rate_limiting_is_not_retried():
    """#39: the UI offers a retry with a countdown instead."""
    get = FakeGet(FakeResponse(429, {"error": True}))
    with pytest.raises(ServiceBusy):
        WeatherClient(http_get=get).fetch([(1.0, 2.0)], START, START + 2 * HOUR)
    assert len(get.calls) == 1


def test_a_timeout_is_retried_once():
    """#39: one retry, then success."""
    get = FakeGet(TIMEOUT)
    assert WeatherClient(http_get=get).fetch([(1.0, 2.0)], START, START + 2 * HOUR)
    assert len(get.calls) == 2


def test_two_server_errors_mean_unavailable():
    """#39: a 5xx, a retry, another 5xx: the plan shows 'weather unknown'."""
    get = FakeGet(FakeResponse(500, {}), FakeResponse(503, {}))
    with pytest.raises(ServiceUnavailable):
        WeatherClient(http_get=get).fetch([(1.0, 2.0)], START, START + 2 * HOUR)


def test_an_answer_for_the_wrong_number_of_places_is_rejected():
    """If Open-Meteo answered for fewer places, forecasts could land on the wrong cells."""
    get = FakeGet(FakeResponse(200, [synthetic_answer({"latitude": "1"})]))
    with pytest.raises(ServiceUnavailable):
        WeatherClient(http_get=get).fetch([(1.0, 2.0), (3.0, 4.0)], START, START + 2 * HOUR)
