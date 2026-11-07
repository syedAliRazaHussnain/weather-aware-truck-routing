"""Tests for planner.risk: every band edge in the spec's tables, the load rules, and
how one checkpoint is classified. Comments like "#30" point to README assumptions."""

from dataclasses import FrozenInstanceError

import pytest

from planner.risk import (
    CheckpointRisk,
    Risk,
    Weather,
    assess,
    rain_risk,
    snow_risk,
    wind_risk,
    wind_risk_for_load,
)

L, M, H, S, NT = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL


# --- Risk levels -------------------------------------------------------------


def test_levels_are_ordered_from_low_to_no_travel():
    """Ordering is what lets max() pick the worst condition (#34)."""
    assert L < M < H < S < NT


def test_max_picks_the_worst_level():
    """The checkpoint rule depends on this (#34)."""
    assert max(H, L, M) == H


def test_levels_score_0_to_4_for_the_average():
    """The mile-weighted average risk uses these numbers (#41)."""
    assert [int(level) for level in Risk] == [0, 1, 2, 3, 4]


def test_labels_are_readable_names():
    """The UI shows these exact names."""
    assert NT.label == "No Travel"
    assert M.label == "Moderate"


# --- Wind --------------------------------------------------------------------


@pytest.mark.parametrize(
    "mph, expected",
    [
        (0, L),
        (24.9, L),  # Low is "<25"
        (25, M),
        (34.9, M),  # #31: still Moderate
        (35, H),
        (44.9, H),
        (45, S),
        (54.9, S),  # #31: still Severe
        (55, NT),  # ">=55" includes 55 itself
        (80, NT),
    ],
)
def test_wind_bands_match_the_spec_table(mph, expected):
    """Every band edge from the spec's wind table, checked on both sides."""
    assert wind_risk(mph) == expected


def test_wind_between_whole_numbers_falls_in_the_lower_band():
    """#31: 34.6 mph sits in the gap between 25-34 and 35-44, so it reads as Moderate."""
    assert wind_risk(34.6) == M


# --- Rain --------------------------------------------------------------------


@pytest.mark.parametrize(
    "inches, expected",
    [
        (0, L),
        (0.099, L),
        (0.10, M),  # "<0.10" is Low, so 0.10 is Moderate
        (0.25, H),  # #30: shared edge goes to the higher band
        (0.49, H),
        (0.50, S),  # #30
        (1.00, S),  # #32: No Travel is strictly above 1.00
        (1.01, NT),
    ],
)
def test_rain_bands_match_the_spec_table(inches, expected):
    """Every rain band edge, including the shared edges and the strict No Travel edge."""
    assert rain_risk(inches) == expected


# --- Snow --------------------------------------------------------------------


@pytest.mark.parametrize(
    "inches, expected",
    [
        (0, L),
        (0.49, L),
        (0.5, M),
        (0.99, M),
        (1.0, H),  # #30
        (2.0, S),  # #30
        (3.0, S),  # #32: No Travel is strictly above 3.0
        (3.01, NT),
    ],
)
def test_snow_bands_match_the_spec_table(inches, expected):
    """Every snow band edge, including the shared edges and the strict No Travel edge."""
    assert snow_risk(inches) == expected


# --- Load rules --------------------------------------------------------------


@pytest.mark.parametrize(
    "mph, load_lb, expected",
    [
        (55, 0, NT),  # >=55 is No Travel even when empty
        (50, 30_000, S),  # #33: exactly 30,000 is not "more than"
        (50, 30_001, NT),
        (45, 30_001, NT),  # bottom of the 45-54 band
        (54.9, 30_001, NT),  # #31: 54.9 is still in 45-54
        (40, 40_000, H),  # #33: exactly 40,000 is not "more than"
        (40, 40_001, S),
        (35, 40_001, S),  # bottom of the 35-44 band
        (44.9, 40_001, S),  # #31: 44.9 is still in 35-44
        (40, 35_000, H),  # #33: the 30,000 rule only applies in 45-54
        (34.9, 80_000, M),  # no load rule below 35 mph
    ],
)
def test_load_rules_raise_wind_risk_only_in_their_band(mph, load_lb, expected):
    """Each load rule at its weight edge and at both ends of its wind band."""
    assert wind_risk_for_load(mph, load_lb) == expected


# --- Data shapes -------------------------------------------------------------


def test_drivers_name_the_condition_that_set_the_level():
    """Rain alone sets High, so only rain is named."""
    r = CheckpointRisk(level=H, wind=L, rain=H, snow=M, wind_before_load=L)
    assert r.drivers == ["rain"]


def test_drivers_name_every_condition_that_ties_for_worst():
    """Wind and rain both High: both are named."""
    r = CheckpointRisk(level=H, wind=H, rain=H, snow=L, wind_before_load=H)
    assert r.drivers == ["wind", "rain"]


def test_low_checkpoint_has_no_drivers():
    """Nothing to explain when everything is Low."""
    r = CheckpointRisk(level=L, wind=L, rain=L, snow=L, wind_before_load=L)
    assert r.drivers == []


def test_load_escalated_compares_wind_before_and_after_load():
    """High raised to Severe by the load reads as escalated; unchanged does not."""
    assert CheckpointRisk(level=S, wind=S, rain=L, snow=L, wind_before_load=H).load_escalated
    assert not CheckpointRisk(level=H, wind=H, rain=L, snow=L, wind_before_load=H).load_escalated


def test_weather_cannot_be_changed_after_creation():
    """frozen=True: a checkpoint's weather can't be edited by accident."""
    w = Weather(wind_mph=10, rain_in_hr=0, snow_in_hr=0)
    with pytest.raises(FrozenInstanceError):
        w.wind_mph = 99


# --- assess: one checkpoint --------------------------------------------------


def test_checkpoint_level_is_the_worst_of_wind_rain_and_snow():
    """#34: Low wind, High rain, Moderate snow gives High, driven by rain."""
    r = assess(Weather(wind_mph=10, rain_in_hr=0.3, snow_in_hr=0.6), load_lb=20_000)
    assert (r.wind, r.rain, r.snow) == (L, H, M)
    assert r.level == H
    assert r.drivers == ["rain"]


def test_heavy_load_raises_wind_and_says_so():
    """#33: 38 mph is High; with 42,000 lb it becomes Severe, raised from High."""
    r = assess(Weather(wind_mph=38, rain_in_hr=0, snow_in_hr=0), load_lb=42_000)
    assert r.level == S
    assert r.wind_before_load == H
    assert r.load_escalated
    assert r.drivers == ["wind"]


def test_load_never_changes_rain_or_snow():
    """The load rules are wind-only: heavy rain stays High whatever the load."""
    light = assess(Weather(wind_mph=0, rain_in_hr=0.3, snow_in_hr=0), load_lb=0)
    heavy = assess(Weather(wind_mph=0, rain_in_hr=0.3, snow_in_hr=0), load_lb=80_000)
    assert light.level == heavy.level == H


def test_calm_checkpoint_is_low_with_nothing_to_explain():
    """No wind, rain or snow: Low, no drivers, not escalated even when heavy."""
    r = assess(Weather(wind_mph=5, rain_in_hr=0, snow_in_hr=0), load_lb=42_000)
    assert r.level == L
    assert r.drivers == []
    assert not r.load_escalated
