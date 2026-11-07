"""Open-Meteo client: hourly forecasts for many places at once, cached for an hour.

Open-Meteo charges one call per location, so points are rounded to a grid and
each cell is fetched once (#36, #37). All times are Unix seconds in UTC (#9).
Comments like "#28" point to the numbered assumptions in the README.
"""

import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import requests

from planner.clients.errors import MissingWeather, ServiceBusy, ServiceUnavailable
from planner.geo import Point
from planner.risk import Weather

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
SERVICE = "weather service"
VARIABLES = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"
BATCH_SIZE = 100  # locations per request
PARALLEL_REQUESTS = 4
CACHE_SECONDS = 3600  # #38
FORECAST_DAYS = 16  # #11
TIMEOUT_S = 20
HOUR = 3600

Cell = tuple[float, float]  # a rounded (lat, lon)


def grid_cell(point: Point, step_deg: float) -> Cell:
    """Round a point to the weather grid, so nearby points share one forecast (#36)."""
    return (
        round(round(point[0] / step_deg) * step_deg, 4),
        round(round(point[1] / step_deg) * step_deg, 4),
    )


def last_forecast_hour(now: datetime) -> int:
    """The last hour Open-Meteo forecasts: the end of the 16th day, UTC (#11)."""
    day_start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((day_start + timedelta(days=FORECAST_DAYS) - timedelta(hours=1)).timestamp())


@dataclass(frozen=True)
class HourlySeries:
    """One cell's forecast, hour by hour from `start` (Unix seconds, on the hour)."""

    start: int
    wind_mph: list[float]
    gust_mph: list[float]
    rain_in_hr: list[float]  # #28: rain + showers
    snow_in_hr: list[float]  # #29

    def index_at(self, unix_time: float) -> int:
        """Which hour is nearest to a moment (#22)."""
        i = round((unix_time - self.start) / HOUR)
        if not 0 <= i < len(self.wind_mph):
            raise MissingWeather(f"no forecast for {unix_time}")
        return i

    def weather_at(self, unix_time: float) -> Weather:
        """Conditions in the hour nearest to a moment, for a checkpoint ETA."""
        i = self.index_at(unix_time)
        return Weather(
            wind_mph=self.wind_mph[i], rain_in_hr=self.rain_in_hr[i], snow_in_hr=self.snow_in_hr[i]
        )

    def gust_at(self, unix_time: float) -> float:
        """Wind gust in the nearest hour; shown in popups only (#27)."""
        return self.gust_mph[self.index_at(unix_time)]

    def hours_from(self, unix_time: float, count: int) -> list[Weather]:
        """`count` consecutive hours starting at the hour nearest to a moment (heatmap)."""
        first = self.index_at(unix_time)
        return [self.weather_at(self.start + (first + k) * HOUR) for k in range(count)]


def parse_series(location: dict) -> HourlySeries:
    """One location from an Open-Meteo answer; any empty value is an error (#39)."""
    hourly = location["hourly"]
    for name in ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall"):
        if any(value is None for value in hourly[name]):
            raise MissingWeather(f"{name} has empty hours")
    return HourlySeries(
        start=hourly["time"][0],
        wind_mph=hourly["wind_speed_10m"],
        gust_mph=hourly["wind_gusts_10m"],
        rain_in_hr=[r + s for r, s in zip(hourly["rain"], hourly["showers"], strict=True)],
        snow_in_hr=hourly["snowfall"],
    )


class TTLCache:
    """A small thread-safe cache whose entries expire after `seconds` (#38)."""

    def __init__(self, seconds: float = CACHE_SECONDS, clock: Callable[[], float] = time.monotonic):
        self._seconds = seconds
        self._clock = clock
        self._items: dict = {}
        self._lock = threading.Lock()

    def get(self, key):
        """The cached value, or None if it's missing or expired."""
        with self._lock:
            item = self._items.get(key)
            if item is None or self._clock() - item[0] > self._seconds:
                self._items.pop(key, None)
                return None
            return item[1]

    def put(self, key, value) -> None:
        """Store a value from now."""
        with self._lock:
            self._items[key] = (self._clock(), value)


def _iso_hour(unix_time: int) -> str:
    """Unix seconds as the hour format Open-Meteo expects, e.g. 2026-11-08T15:00."""
    return datetime.fromtimestamp(unix_time, UTC).strftime("%Y-%m-%dT%H:%M")


class WeatherClient:
    """Fetches hourly forecasts for many grid cells, using the cache first."""

    def __init__(self, http_get: Callable = requests.get, cache: TTLCache | None = None):
        self._get = http_get
        self._cache = cache if cache is not None else TTLCache()

    def fetch(self, cells: Iterable[Cell], start: int, end: int) -> dict[Cell, HourlySeries]:
        """Forecasts for every cell from hour `start` to hour `end` (Unix seconds, UTC)."""
        wanted = list(dict.fromkeys(cells))  # unique, in order
        found: dict[Cell, HourlySeries] = {}
        missing = []
        for cell in wanted:
            cached = self._cache.get((cell, start, end))
            if cached is None:
                missing.append(cell)
            else:
                found[cell] = cached
        batches = [missing[i : i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
        with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:
            for batch, series in zip(
                batches, pool.map(lambda b: self._fetch_batch(b, start, end), batches), strict=True
            ):
                for cell, one in zip(batch, series, strict=True):
                    self._cache.put((cell, start, end), one)
                    found[cell] = one
        return found

    def _fetch_batch(self, cells: list[Cell], start: int, end: int) -> list[HourlySeries]:
        """One Open-Meteo request for up to 100 cells, retried once on a timeout or 5xx (#39)."""
        params = {
            "latitude": ",".join(str(lat) for lat, _ in cells),
            "longitude": ",".join(str(lon) for _, lon in cells),
            "hourly": VARIABLES,
            "wind_speed_unit": "mph",  # spec units, so no conversions here
            "precipitation_unit": "inch",
            "timeformat": "unixtime",
            "timezone": "GMT",
            "start_hour": _iso_hour(start),
            "end_hour": _iso_hour(end),
        }
        for attempt in (1, 2):
            try:
                response = self._get(FORECAST_URL, params=params, timeout=TIMEOUT_S)
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise ServiceUnavailable(SERVICE) from None
                continue
            if response.status_code == 429:
                raise ServiceBusy(SERVICE)  # #39: not retried
            if response.status_code >= 500 and attempt == 1:
                continue
            if response.status_code != 200:
                raise ServiceUnavailable(SERVICE)
            body = response.json()
            locations = body if isinstance(body, list) else [body]  # one location isn't a list
            if len(locations) != len(cells):
                raise ServiceUnavailable(SERVICE)
            return [parse_series(location) for location in locations]
        raise ServiceUnavailable(SERVICE)
