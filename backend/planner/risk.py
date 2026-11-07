"""Weather risk classification for a single checkpoint.

Pure functions only: no Django, no network calls. The thresholds come straight
from the spec's risk table and load rules; comments like "#30" point to the
numbered assumptions in the README.
"""

from dataclasses import dataclass
from enum import IntEnum


class Risk(IntEnum):
    """The five risk levels, ordered so the worst one can be found with max() (#34)."""

    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        """Name for the screen, e.g. Risk.NO_TRAVEL -> "No Travel"."""
        return self.name.replace("_", " ").title()


def wind_risk(mph: float) -> Risk:
    """Classify sustained wind speed (mph) using the spec's wind table."""
    # #31: bands are continuous, so "25-34" means 25 up to (not including) 35.
    if mph >= 55:
        return Risk.NO_TRAVEL  # spec: >=55 mph
    if mph >= 45:
        return Risk.SEVERE  # 45-54
    if mph >= 35:
        return Risk.HIGH  # 35-44
    if mph >= 25:
        return Risk.MODERATE  # 25-34
    return Risk.LOW  # <25


def rain_risk(in_per_hr: float) -> Risk:
    """Classify rain intensity (in/hr) using the spec's rain table."""
    if in_per_hr > 1.00:
        return Risk.NO_TRAVEL  # #32: spec says ">1.00", so 1.00 itself is Severe
    if in_per_hr >= 0.50:
        return Risk.SEVERE  # #30: shared edge 0.50 goes to the higher band
    if in_per_hr >= 0.25:
        return Risk.HIGH  # #30: shared edge 0.25 goes to the higher band
    if in_per_hr >= 0.10:
        return Risk.MODERATE  # spec: "<0.10" is Low, so 0.10 is Moderate
    return Risk.LOW


def snow_risk(in_per_hr: float) -> Risk:
    """Classify snowfall (inches of snow per hour) using the spec's snow table."""
    if in_per_hr > 3.0:
        return Risk.NO_TRAVEL  # #32: spec says ">3.0", so 3.0 itself is Severe
    if in_per_hr >= 2.0:
        return Risk.SEVERE  # #30: shared edge 2.0 goes to the higher band
    if in_per_hr >= 1.0:
        return Risk.HIGH  # #30: shared edge 1.0 goes to the higher band
    if in_per_hr >= 0.5:
        return Risk.MODERATE  # spec: "<0.5" is Low, so 0.5 is Moderate
    return Risk.LOW


def wind_risk_for_load(mph: float, load_lb: float) -> Risk:
    """Wind risk after applying the spec's load rules."""
    # Rules check the wind band, not raw mph, so "45-54" stays defined once in
    # wind_risk and 54.9 mph is still in that band (#31).
    # >=55 mph is already No Travel in wind_risk, for any load.
    level = wind_risk(mph)
    if level == Risk.SEVERE and load_lb > 30_000:
        return Risk.NO_TRAVEL  # #33: 45-54 mph and strictly more than 30,000 lb
    if level == Risk.HIGH and load_lb > 40_000:
        return Risk.SEVERE  # #33: 35-44 mph and strictly more than 40,000 lb
    return level


@dataclass(frozen=True)
class Weather:
    """Conditions at one place and hour, already in spec units."""

    wind_mph: float  # #27: sustained wind at 10 m
    rain_in_hr: float  # #28: rain + showers
    snow_in_hr: float  # #29: inches of snow, not water equivalent


@dataclass(frozen=True)
class CheckpointRisk:
    """A checkpoint's overall level plus the per-condition levels behind it."""

    level: Risk  # #34: the worst of the three
    wind: Risk  # after the load rules
    rain: Risk
    snow: Risk
    wind_before_load: Risk  # wind level from the table alone

    @property
    def load_escalated(self) -> bool:
        """True when the load rules raised the wind level."""
        return self.wind > self.wind_before_load

    @property
    def drivers(self) -> list[str]:
        """Which conditions set the overall level, e.g. ["wind"]. Empty when Low."""
        if self.level == Risk.LOW:
            return []
        by_condition = {"wind": self.wind, "rain": self.rain, "snow": self.snow}
        return [name for name, level in by_condition.items() if level == self.level]


def assess(weather: Weather, load_lb: float) -> CheckpointRisk:
    """Classify one checkpoint: the worst of wind (after load rules), rain and snow."""
    wind_before_load = wind_risk(weather.wind_mph)
    wind = wind_risk_for_load(weather.wind_mph, load_lb)
    rain = rain_risk(weather.rain_in_hr)
    snow = snow_risk(weather.snow_in_hr)
    return CheckpointRisk(
        level=max(wind, rain, snow),  # #34
        wind=wind,
        rain=rain,
        snow=snow,
        wind_before_load=wind_before_load,
    )
