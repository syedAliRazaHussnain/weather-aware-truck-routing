"""Summarising each route's risk and picking the recommended one.

Pure functions only: no Django, no network calls. The ranking follows the spec's
preference list exactly; comments like "#41" point to the numbered assumptions
in the README.
"""

from dataclasses import dataclass

from planner.risk import Risk


@dataclass(frozen=True)
class RouteSummary:
    """The numbers the ranking compares for one route."""

    label: str  # "A", "B", "C": A is the fastest route
    total_mi: float
    seconds: float  # driving time for the whole route
    severe_mi: float  # Severe checkpoints only (#42)
    high_mi: float
    no_travel_mi: float
    avg_risk: float  # mile-weighted, Low=0 ... No Travel=4 (#41)

    @property
    def has_no_travel(self) -> bool:
        """True if any stretch of this route is No Travel."""
        return self.no_travel_mi > 0


def checkpoint_miles(marks: list[float]) -> list[float]:
    """Miles of road each checkpoint stands for: half the gap on each side (#40)."""
    if len(marks) == 1:
        return [0.0]
    gaps = [b - a for a, b in zip(marks, marks[1:], strict=False)]
    halves = [g / 2 for g in gaps]
    return [halves[0], *(a + b for a, b in zip(halves, halves[1:], strict=False)), halves[-1]]


def summarize(label: str, marks: list[float], levels: list[Risk], seconds: float) -> RouteSummary:
    """Add up one route's miles by risk level, and its mile-weighted average risk."""
    if len(marks) != len(levels):
        raise ValueError("need one risk level per checkpoint")
    covered = checkpoint_miles(marks)
    total = sum(covered)

    def miles_at(level: Risk) -> float:
        return sum(m for m, lv in zip(covered, levels, strict=True) if lv == level)

    weighted = sum(m * int(lv) for m, lv in zip(covered, levels, strict=True))
    return RouteSummary(
        label=label,
        total_mi=total,
        seconds=seconds,
        severe_mi=miles_at(Risk.SEVERE),
        high_mi=miles_at(Risk.HIGH),
        no_travel_mi=miles_at(Risk.NO_TRAVEL),
        avg_risk=weighted / total if total else 0.0,
    )


def rank_key(s: RouteSummary) -> tuple:
    """What routes are sorted by, most important first; smaller is better."""
    return (
        s.has_no_travel,  # #42: any No Travel goes after every route without it
        round(s.no_travel_mi),  # #42: then fewer No Travel miles
        round(s.severe_mi),  # #41: fewest Severe miles (#44: whole miles)
        round(s.high_mi),  # #41: fewest High miles
        round(s.avg_risk, 2),  # #41: lowest average risk (#44: 2 decimals)
        s.seconds,  # #41, #43: shortest time breaks the tie
    )


def rank(summaries: list[RouteSummary]) -> list[RouteSummary]:
    """Routes from best to worst by the spec's preference order."""
    # sorted() is stable: fully tied routes keep their order, fastest first.
    return sorted(summaries, key=rank_key)


def all_no_travel(summaries: list[RouteSummary]) -> bool:
    """True when no route avoids No Travel, so the UI shows the warning (#45)."""
    return bool(summaries) and all(s.has_no_travel for s in summaries)


def format_duration(seconds: float) -> str:
    """Seconds as "53 min" or "1 h 05 min" for the reason line."""
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


def reason(ranked: list[RouteSummary]) -> str:
    """One line on why the top route won: the first rule that beat the fastest route,
    or the runner-up when it is the fastest (#46)."""
    best = ranked[0]
    fastest = min(ranked, key=lambda s: s.seconds)
    if len(ranked) == 1:
        why = "Only route found"
    elif fastest is not best:
        why = _deciding_rule(best, fastest)  # the driver's question: why not the fastest?
    else:
        why = _deciding_rule(best, ranked[1])
    extra = best.seconds - fastest.seconds
    if why.startswith("Same risk as") and fastest is best:
        return f"Same risk as Route {ranked[1].label}, and it's the fastest route."
    when = "fastest route" if extra < 60 else f"{format_duration(extra)} slower than the fastest"
    return f"{why}. {when[0].upper()}{when[1:]}."


def _deciding_rule(best: RouteSummary, other: RouteSummary) -> str:
    """Describe the first ranking rule on which `best` beat `other`."""
    a, b = rank_key(best), rank_key(other)
    on = f"on Route {other.label}"
    if a[0] != b[0]:
        return f"No No Travel stretches ({round(other.no_travel_mi)} mi {on})"
    if a[1] != b[1]:
        return f"{a[1]} No Travel miles vs {b[1]} {on}"
    if a[2] != b[2]:
        return f"{a[2]} Severe miles vs {b[2]} {on}"
    if a[3] != b[3]:
        return f"{a[3]} High miles vs {b[3]} {on}"
    if a[4] != b[4]:
        return f"Lower average risk: {a[4]:.2f} vs {b[4]:.2f} {on}"
    if a[5] != b[5]:
        return f"Same risk as Route {other.label}, and quicker"
    return f"Same risk and time as Route {other.label}"
