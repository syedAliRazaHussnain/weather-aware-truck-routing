"""Tests for planner.recommend: miles per checkpoint, route summaries, the ranking
order and the reason line. Comments like "#41" point to README assumptions."""

import pytest

from planner.recommend import (
    RouteSummary,
    all_no_travel,
    checkpoint_miles,
    format_duration,
    rank,
    reason,
    summarize,
)
from planner.risk import Risk

L, M, H, S, NT = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL
HOUR = 3600


def summary(label, hours, severe=0, high=0, no_travel=0, avg=0.0, total=500):
    """A route summary with only the numbers a test cares about."""
    return RouteSummary(
        label=label,
        total_mi=total,
        seconds=hours * HOUR,
        severe_mi=severe,
        high_mi=high,
        no_travel_mi=no_travel,
        avg_risk=avg,
    )


# --- Miles per checkpoint ----------------------------------------------------


def test_each_checkpoint_covers_half_the_gap_on_each_side():
    """#40: the 491 mi example. Ends cover 12.5 and 8 mi, the middle ones 25,
    mile 475 covers 20.5."""
    marks = [i * 25 for i in range(20)] + [491]
    miles = checkpoint_miles(marks)
    assert miles[0] == 12.5
    assert miles[1:-2] == [25] * 18
    assert miles[-2] == 20.5
    assert miles[-1] == 8


def test_covered_miles_add_up_to_the_route_length():
    """#40: nothing is counted twice or left out."""
    assert sum(checkpoint_miles([0, 25, 50, 75, 91])) == 91


def test_a_two_checkpoint_trip_splits_the_road_in_half():
    """A 10 mi trip: origin and destination cover 5 mi each."""
    assert checkpoint_miles([0, 10]) == [5, 5]


# --- Summaries ---------------------------------------------------------------


def test_summary_adds_miles_by_level_and_weights_the_average_by_miles():
    """Low, Severe, High at miles 0/10/20 cover 5, 10 and 5 mi: Severe 10, High 5,
    average (0*5 + 3*10 + 2*5) / 20 = 2.0."""
    s = summarize("A", marks=[0, 10, 20], levels=[L, S, H], seconds=HOUR)
    assert (s.severe_mi, s.high_mi, s.no_travel_mi) == (10, 5, 0)
    assert s.avg_risk == pytest.approx(2.0)
    assert s.total_mi == 20


def test_severe_miles_do_not_include_no_travel_miles():
    """#42: No Travel is counted on its own, not as Severe."""
    s = summarize("A", marks=[0, 10, 20], levels=[NT, S, L], seconds=HOUR)
    assert (s.no_travel_mi, s.severe_mi) == (5, 10)
    assert s.has_no_travel


def test_a_summary_needs_one_level_per_checkpoint():
    """A mismatch would silently shift every level onto the wrong miles."""
    with pytest.raises(ValueError):
        summarize("A", marks=[0, 10, 20], levels=[L, L], seconds=HOUR)


# --- Ranking -----------------------------------------------------------------


def test_the_design_example_ranks_c_then_b_then_a():
    """#41, Part 5: A has 50 Severe miles so it's last; B and C tie on Severe and
    High miles, and C wins on lower average risk."""
    a = summary("A", 10.2, severe=50, high=25, avg=0.62)
    b = summary("B", 11.67, severe=0, high=75, avg=1.10)
    c = summary("C", 11.08, severe=0, high=75, avg=0.90)
    assert [s.label for s in rank([a, b, c])] == ["C", "B", "A"]


def test_fewer_severe_miles_beats_a_much_faster_route():
    """#43, on purpose: the spec's order puts risk before time, so 0 Severe miles
    in 14.5 h beats 25 Severe miles in 10 h. The UI shows the extra time."""
    fast = summary("X", 10, severe=25)
    safe = summary("Y", 14.5, severe=0)
    assert rank([fast, safe])[0].label == "Y"


def test_any_no_travel_ranks_after_every_route_without_it():
    """#42: 5 No Travel miles is worse than 100 Severe miles."""
    no_travel = summary("A", 10, no_travel=5)
    severe = summary("B", 12, severe=100)
    assert [s.label for s in rank([no_travel, severe])] == ["B", "A"]


def test_among_no_travel_routes_fewer_no_travel_miles_wins():
    """#42: when every route has No Travel, the least of it goes first."""
    worse = summary("A", 10, no_travel=30)
    better = summary("B", 12, no_travel=10, severe=40)
    assert rank([worse, better])[0].label == "B"


def test_high_miles_decide_when_severe_miles_tie():
    """#41: second rule."""
    a = summary("A", 10, severe=25, high=50)
    b = summary("B", 11, severe=25, high=25)
    assert rank([a, b])[0].label == "B"


def test_shortest_time_breaks_a_full_risk_tie():
    """#41: last rule."""
    slow = summary("A", 12, severe=25, high=25, avg=1.0)
    quick = summary("B", 11, severe=25, high=25, avg=1.0)
    assert rank([slow, quick])[0].label == "B"


def test_tiny_differences_in_miles_do_not_decide_the_winner():
    """#44: 8.0 vs 8.3 Severe miles round to the same 8, so time decides."""
    a = summary("A", 12, severe=8.0)
    b = summary("B", 10, severe=8.3)
    assert rank([a, b])[0].label == "B"


def test_average_risk_is_compared_to_two_decimals():
    """#44: 0.901 and 0.899 both round to 0.90, so time decides."""
    a = summary("A", 12, avg=0.899)
    b = summary("B", 10, avg=0.901)
    assert rank([a, b])[0].label == "B"


def test_all_no_travel_is_flagged_only_when_every_route_has_it():
    """#45: the warning appears only when there's no way around No Travel."""
    assert all_no_travel([summary("A", 10, no_travel=5), summary("B", 11, no_travel=1)])
    assert not all_no_travel([summary("A", 10, no_travel=5), summary("B", 11)])
    assert not all_no_travel([])


# --- The reason line ---------------------------------------------------------


@pytest.mark.parametrize(
    "seconds, text",
    [(53 * 60, "53 min"), (65 * 60, "1 h 05 min"), (125 * 60, "2 h 05 min"), (30, "0 min")],
)
def test_durations_read_naturally(seconds, text):
    """The reason line shows time the way a driver says it."""
    assert format_duration(seconds) == text


def test_reason_explains_why_not_the_fastest_route():
    """#46: the design example. C is slower than A, so the reason says why A lost:
    its 50 Severe miles. Then how much slower C is."""
    a = summary("A", 10.2, severe=50, high=25, avg=0.62)
    b = summary("B", 11.67, severe=0, high=75, avg=1.10)
    c = summary("C", 11.083, severe=0, high=75, avg=0.90)
    assert reason(rank([a, b, c])) == (
        "0 Severe miles vs 50 on Route A. 53 min slower than the fastest."
    )


def test_reason_compares_with_the_runner_up_when_the_winner_is_fastest():
    """#46: nothing to explain about time, so the reason says why B lost."""
    a = summary("A", 10, severe=0, avg=0.90)
    b = summary("B", 11, severe=0, avg=1.10)
    assert reason(rank([a, b])) == "Lower average risk: 0.90 vs 1.10 on Route B. Fastest route."


def test_reason_for_a_severe_mile_win():
    """#46: the first rule that differs is Severe miles."""
    fast = summary("A", 10, severe=50)
    safe = summary("B", 11, severe=0)
    assert (
        reason(rank([fast, safe]))
        == "0 Severe miles vs 50 on Route A. 1 h 00 min slower than the fastest."
    )


def test_reason_when_the_winner_is_also_the_fastest():
    """No 'slower' note when the best route is the quickest one."""
    best = summary("A", 10, high=10)
    other = summary("B", 11, high=30)
    assert reason(rank([best, other])) == "10 High miles vs 30 on Route B. Fastest route."


def test_reason_when_avoiding_no_travel_decided():
    """#42: the strongest reason of all."""
    clear = summary("B", 12)
    blocked = summary("A", 10, no_travel=20)
    assert reason(rank([clear, blocked])).startswith("No No Travel stretches (20 mi on Route A)")


def test_reason_when_only_time_decided():
    """Same risk numbers: the quicker one wins and the reason says so."""
    a = summary("A", 10, severe=25)
    b = summary("B", 11, severe=25)
    assert reason(rank([a, b])) == "Same risk as Route B, and quicker. Fastest route."


def test_reason_with_a_single_route():
    """When only one route exists there's nothing to compare."""
    assert reason([summary("A", 10)]) == "Only route found. Fastest route."
