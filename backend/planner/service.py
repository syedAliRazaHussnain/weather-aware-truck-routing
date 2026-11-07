"""Planning one trip: the eight steps from the design, in order.

This is the only module that knows the order of the steps (see
docs/ARCHITECTURE.md, diagram 4). It calls the pure modules and the two clients,
and turns every failure into a PlanProblem: a plain message plus one-tap actions
for the driver, never a bare error. Comments like "#10" point to the numbered
assumptions in the README.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from math import ceil
from zoneinfo import ZoneInfo

from tzfpy import get_tz

from planner.clients.errors import (
    AlternativesNotAllowed,
    ClientError,
    MissingWeather,
    NoRoadNearby,
    NoTruckRoute,
    ServiceBusy,
    ServiceUnavailable,
    TripTooLong,
)
from planner.clients.weather import HOUR, grid_cell, last_forecast_hour
from planner.corridor import HEATMAP_HOURS, START_SQUARE_MI, hourly_levels, plan_heatmap
from planner.geo import Checkpoint, Point, checkpoints, cumulative_miles, haversine_mi, slice_path
from planner.recommend import RouteSummary, all_no_travel, rank, reason, summarize
from planner.risk import CheckpointRisk, assess
from planner.routes import Route, is_acceptable, pick_alternatives

EMPTY_TRUCK_LB = 35_000  # #13
DEPARTURE_GRACE_S = HOUR  # #10
WEATHER_BUDGET = 500  # #37: locations per plan
GRID_STEPS = (0.05, 0.1)  # #36: finest weather grid that fits the budget
SHORT_TRIP_MI = 56  # #14: about 90 km in a straight line
LONG_TRIP_S = 11 * HOUR  # #24
FAR_AHEAD_S = 72 * HOUR  # #26
INTERVALS = (10, 25, 50)  # #1
CHECK_AGAIN_HOUR = 6  # #45: "Check tomorrow 6 AM"
SAME_PLACE_MI = 0.1


@dataclass(frozen=True)
class TripRequest:
    """What the driver asked for, already checked by the serializer."""

    origin: Point
    destination: Point
    departure_local: datetime | None  # origin's local time, no zone (#7); None = now
    load_lb: float  # cargo load, already in lb (#2, #33)
    interval_mi: float = 25  # #1
    origin_label: str = ""
    destination_label: str = ""


@dataclass
class PlanProblem(Exception):
    """Something the driver can fix or retry, with buttons that help them do it (#59)."""

    code: str
    message: str
    actions: list[dict] = field(default_factory=list)
    status: int = 400

    def to_dict(self) -> dict:
        """The JSON the API sends for this problem."""
        return {"error": self.code, "message": self.message, "actions": self.actions}


# --- Small helpers -------------------------------------------------------------


def local_iso(unix_time: float, tz: ZoneInfo) -> str:
    """A moment as the origin's local time with its offset, e.g. 2026-11-08T08:31-07:00."""
    return datetime.fromtimestamp(unix_time, tz).isoformat(timespec="minutes")


def form_time(moment: datetime) -> str:
    """A local time in the form's own format, for actions that change the departure."""
    return moment.strftime("%Y-%m-%dT%H:%M")


def nearest_hour(unix_time: float) -> int:
    """Round a moment to the nearest whole hour (#22, #47)."""
    return round(unix_time / HOUR) * HOUR


def retry_action(after_s: int | None = None) -> dict:
    """A [Try again] button, optionally with a countdown."""
    action = {"type": "retry", "label": "Try again"}
    if after_s:
        action["retry_after_s"] = after_s
    return action


def service_problem(error: ServiceBusy | ServiceUnavailable) -> PlanProblem:
    """A busy or unavailable outside service, with a retry button."""
    if isinstance(error, ServiceBusy):
        return PlanProblem(
            f"{error.service.split()[0]}_busy",
            f"The {error.service} is busy right now.",
            [retry_action(60)],
            status=503,
        )
    return PlanProblem(
        f"{error.service.split()[0]}_unavailable",
        f"We couldn't reach the {error.service}. Your trip details are kept.",
        [retry_action()],
        status=502,
    )


# --- Step 2: routes ------------------------------------------------------------


def find_routes(ors, origin: Point, destination: Point, gross_lb: float) -> list[Route]:
    """Up to three different truck routes, fastest first (#14, #15)."""
    if haversine_mi(origin, destination) < SHORT_TRIP_MI:
        try:
            candidates = sorted(
                ors.truck_alternatives(origin, destination, gross_lb), key=lambda r: r.seconds
            )
        except AlternativesNotAllowed:
            candidates = []
        if candidates:
            chosen = [candidates[0]]
            for candidate in candidates[1:]:
                if is_acceptable(candidate, chosen, candidates[0]):
                    chosen.append(candidate)
            return chosen

    fastest = ors.truck_route([origin, destination], gross_lb)

    def route_via(point: Point) -> Route | None:
        try:
            return ors.truck_route([origin, point, destination], gross_lb)
        except ClientError:
            return None  # no road near the detour point, or ORS hiccup: try the next one

    return [fastest, *pick_alternatives(fastest, origin, destination, route_via)]


def routing_problem(error: ClientError, ors, request: TripRequest) -> PlanProblem:
    """A routing failure as a message the driver can act on (#59)."""
    if isinstance(error, NoRoadNearby):
        which = "origin" if error.index == 0 else "destination"
        point = request.origin if which == "origin" else request.destination
        actions = []
        try:
            place = ors.nearest_place(point)
        except ClientError:
            place = None
        if place is not None:
            away = round(haversine_mi(point, (place.lat, place.lon)))
            actions.append(
                {
                    "type": "use_place",
                    "field": which,
                    "label": f"Use {place.label} ({away} mi away)",
                    "place": {"label": place.label, "lat": place.lat, "lon": place.lon},
                }
            )
        actions.append({"type": "edit_field", "field": which, "label": "Pick another point"})
        return PlanProblem("no_road_nearby", f"There's no truck road near your {which}.", actions)
    if isinstance(error, TripTooLong):
        return PlanProblem(
            "trip_too_long",
            "This trip is too long for the free routing service (about 3,700 mi at most), "
            "or it crosses the sea, where there's no truck route.",
            [
                {
                    "type": "edit_field",
                    "field": "destination",
                    "label": "Pick a closer destination, or plan it in two legs",
                }
            ],
        )
    if isinstance(error, NoTruckRoute):
        return PlanProblem(
            "no_truck_route",
            "We couldn't find a truck route between these places.",
            [
                {"type": "edit_field", "field": "load", "label": "Check the load weight"},
                {"type": "edit_field", "field": "destination", "label": "Try a nearby destination"},
            ],
        )
    if isinstance(error, ServiceBusy | ServiceUnavailable):
        return service_problem(error)
    return PlanProblem(
        "routing_unavailable", "We couldn't plan a route.", [retry_action()], status=502
    )


# --- Steps 4 and 6: weather cells, risk and the heatmap --------------------------


def choose_grid(
    routes_checkpoints: list[list[Checkpoint]], interval_mi: float
) -> tuple[float, set]:
    """The finest weather grid whose checkpoint cells fit the budget (#36, #37)."""
    for step in GRID_STEPS:
        cells = {grid_cell((c.lat, c.lon), step) for cps in routes_checkpoints for c in cps}
        if len(cells) <= WEATHER_BUDGET:
            return step, cells
    bigger = [i for i in INTERVALS if i > interval_mi]
    raise PlanProblem(
        "too_many_checkpoints",
        f"This trip is too long for {interval_mi:g}-mile checkpoints on the free weather service.",
        [{"type": "set_interval", "value": i, "label": f"Use {i} mi"} for i in bigger],
    )


def segments_geojson(route: Route, marks: list[float], risks: list[CheckpointRisk | None]) -> dict:
    """The route cut into stretches coloured by each checkpoint's level (#40)."""
    # Checkpoint i covers the road from halfway back to halfway forward, the same
    # stretch its miles are counted over in the ranking.
    bounds = [marks[0], *((a + b) / 2 for a, b in pairwise(marks)), marks[-1]]
    stretches: list[list] = []  # [level, from_mi, to_mi], joined when the colour repeats
    for i, risk in enumerate(risks):
        level = None if risk is None else int(risk.level)
        if stretches and stretches[-1][0] == level:
            stretches[-1][2] = bounds[i + 1]
        else:
            stretches.append([level, bounds[i], bounds[i + 1]])
    miles = cumulative_miles(route.path)
    features = []
    for level, from_mi, to_mi in stretches:
        points = slice_path(route.path, miles, from_mi, to_mi)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "level": level,
                    "from_mi": round(from_mi, 2),
                    "to_mi": round(to_mi, 2),
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[round(lon, 5), round(lat, 5)] for lat, lon in points],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def checkpoint_json(
    cp: Checkpoint, departure: int, tz: ZoneInfo, risk: CheckpointRisk | None, weather: dict | None
) -> dict:
    """One checkpoint for the map popup."""
    data = {
        "mile": round(cp.mile, 1),
        "lat": round(cp.lat, 5),
        "lon": round(cp.lon, 5),
        "eta": local_iso(departure + cp.seconds, tz),
        "level": None,
        "label": "Weather unknown",
        "drivers": [],
        "load_escalated": False,
        "wind_before_load": None,
        "weather": weather,
    }
    if risk is not None:
        data.update(
            level=int(risk.level),
            label=risk.level.label,
            drivers=risk.drivers,
            load_escalated=risk.load_escalated,
            wind_before_load=risk.wind_before_load.label,
        )
    return data


# --- The whole plan --------------------------------------------------------------


def plan_trip(request: TripRequest, ors, weather, now: datetime | None = None) -> dict:
    """Plan a trip end to end and return the JSON-ready result (diagram 4)."""
    now = now or datetime.now(UTC)
    now_unix = now.timestamp()

    # 1. Check input and the departure window.
    if haversine_mi(request.origin, request.destination) < SAME_PLACE_MI:
        raise PlanProblem(
            "same_place",
            "The origin and destination are the same place.",
            [
                {
                    "type": "edit_field",
                    "field": "destination",
                    "label": "Pick a different destination",
                }
            ],
        )
    tz_name = get_tz(request.origin[1], request.origin[0]) or "UTC"  # #8: offline lookup
    tz = ZoneInfo(tz_name)
    if request.departure_local is None:  # #10: "leave now", at the origin
        departure = int(now_unix)
    else:
        departure = int(request.departure_local.replace(tzinfo=tz).timestamp())  # #7, #9
    if departure < now_unix - DEPARTURE_GRACE_S:
        raise PlanProblem(
            "departure_passed",
            "That departure time has passed.",
            [
                {
                    "type": "set_departure",
                    "value": form_time(now.astimezone(tz)),
                    "label": "Leave now",
                }
            ],
        )
    start = nearest_hour(departure)  # #47: slider hour 0
    horizon = last_forecast_hour(now)
    if start + 48 * HOUR > horizon:
        raise beyond_forecast(horizon, 48 * HOUR, tz)

    # 2. Up to three truck routes.
    gross_lb = request.load_lb + EMPTY_TRUCK_LB  # #13
    try:
        routes = sorted(
            find_routes(ors, request.origin, request.destination, gross_lb), key=lambda r: r.seconds
        )
    except ClientError as error:
        raise routing_problem(error, ors, request) from error
    labels = "ABC"  # #60: A is the fastest

    # 3. Checkpoints and ETAs.
    route_cps = [checkpoints(r.path, r.steps, request.interval_mi) for r in routes]
    end = max(start + 48 * HOUR, ceil((departure + max(r.seconds for r in routes)) / HOUR) * HOUR)
    if end > horizon:
        raise beyond_forecast(horizon, end - start, tz)

    # 4. Weather cells, then the heatmap gets what's left of the budget.
    step, cells = choose_grid(route_cps, request.interval_mi)
    heat_budget = WEATHER_BUDGET - len(cells)
    grid, squares = (
        plan_heatmap([r.path for r in routes], heat_budget) if heat_budget > 0 else (None, set())
    )
    square_cells = {sq: grid_cell(grid.center(sq), step) for sq in squares}
    all_cells = cells | set(square_cells.values())

    # 5. Fetch weather. A failure still shows the routes, never as safe (#39).
    try:
        forecasts = weather.fetch(all_cells, start, end)
        weather_problem = None
    except (ServiceBusy, ServiceUnavailable) as error:
        forecasts, weather_problem = None, service_problem(error)
    except MissingWeather:
        forecasts = None
        weather_problem = PlanProblem(
            "weather_unavailable", "Some forecasts came back empty.", [retry_action()], status=502
        )
    if weather_problem is not None:
        weather_problem.message += " We can't rate these routes yet."

    # 6. Risk per checkpoint, and 49 hourly levels per heatmap square.
    routes_json, summaries = [], []
    for label, route, cps in zip(labels, routes, route_cps, strict=False):
        risks: list[CheckpointRisk | None] = []
        cps_json = []
        for cp in cps:
            risk, conditions = None, None
            if forecasts is not None:
                series = forecasts[grid_cell((cp.lat, cp.lon), step)]
                at = departure + cp.seconds
                w = series.weather_at(at)
                risk = assess(w, request.load_lb)
                conditions = {
                    "wind_mph": round(w.wind_mph, 1),
                    "gust_mph": round(series.gust_at(at), 1),
                    "rain_in_hr": round(w.rain_in_hr, 2),
                    "snow_in_hr": round(w.snow_in_hr, 2),
                }
            risks.append(risk)
            cps_json.append(checkpoint_json(cp, departure, tz, risk, conditions))
        marks = [cp.mile for cp in cps]
        summary = None
        if forecasts is not None:
            summary = summarize(label, marks, [r.level for r in risks], route.seconds)
            summaries.append(summary)
        routes_json.append(
            {
                "id": label,
                "distance_mi": round(marks[-1], 1),
                "duration_s": round(route.seconds),
                "summary": summary_json(summary),
                "segments": segments_geojson(route, marks, risks),
                "checkpoints": cps_json,
            }
        )

    heatmap = None
    if forecasts is not None and squares:
        features = []
        for sq in sorted(squares):
            levels = hourly_levels(
                forecasts[square_cells[sq]].hours_from(start, HEATMAP_HOURS), request.load_lb
            )
            props = {f"h{h}": level for h, level in enumerate(levels)}
            ring = [[round(lon, 5), round(lat, 5)] for lat, lon in grid.corners(sq)]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": props,
                }
            )
        heatmap = {
            "start": local_iso(start, tz),
            "hours": HEATMAP_HOURS,
            "square_mi": round(grid.square_mi, 1),
            "cells": {"type": "FeatureCollection", "features": features},
        }

    # 7. Rank and explain.
    recommended, why, warning = None, None, None
    if summaries:
        ranked = rank(summaries)
        recommended, why = ranked[0].label, reason(ranked)
        order = {s.label: i + 1 for i, s in enumerate(ranked)}
        for r in routes_json:
            r["rank"] = order[r["id"]]
        if all_no_travel(summaries):
            warning = no_safe_route_warning(departure, tz)
    else:
        for r in routes_json:
            r["rank"] = None

    # 8. Notes and the response.
    notes = []
    if len(routes) < 3:
        notes.append(
            f"Only {len(routes)} different route{'s' if len(routes) > 1 else ''} "
            "found for this trip."
        )
    if max(r.seconds for r in routes) > LONG_TRIP_S:
        notes.append(
            "ETAs assume no rest stops. Re-plan after each rest for up-to-date ETAs and weather."
        )
    if departure + max(r.seconds for r in routes) - now_unix > FAR_AHEAD_S:
        notes.append("Forecasts this far ahead can change a lot. Check again closer to departure.")
    if grid is not None and grid.square_mi > START_SQUARE_MI:
        notes.append(
            f"Heatmap squares are {grid.square_mi:.0f} mi across "
            "to stay within the free weather limit."
        )

    return {
        "timezone": tz_name,
        "departure": local_iso(departure, tz),
        "weather_status": "ok" if forecasts is not None else "unavailable",
        "recommended": recommended,
        "reason": why,
        "warning": warning,
        "problem": weather_problem.to_dict() if weather_problem else None,
        "notes": notes,
        "routes": routes_json,
        "heatmap": heatmap,
    }


def summary_json(summary: RouteSummary | None) -> dict | None:
    """A route summary for the route card, or None when weather is unknown."""
    if summary is None:
        return None
    return {
        "severe_mi": round(summary.severe_mi),
        "high_mi": round(summary.high_mi),
        "no_travel_mi": round(summary.no_travel_mi),
        "avg_risk": round(summary.avg_risk, 2),
    }


def beyond_forecast(horizon: int, window_s: int, tz: ZoneInfo) -> PlanProblem:
    """The weather window ends after the last forecast hour (#11)."""
    latest = datetime.fromtimestamp(horizon - window_s, tz).replace(minute=0)
    return PlanProblem(
        "beyond_forecast",
        "Forecasts only reach 16 days ahead.",
        [
            {
                "type": "set_departure",
                "value": form_time(latest),
                "label": "Plan for the latest possible date",
            }
        ],
    )


def no_safe_route_warning(departure: int, tz: ZoneInfo) -> dict:
    """Every route has No Travel: say so and offer to check tomorrow morning (#45)."""
    tomorrow = (datetime.fromtimestamp(departure, tz) + timedelta(days=1)).replace(
        hour=CHECK_AGAIN_HOUR, minute=0
    )
    return {
        "message": "Every route has a No Travel stretch at this departure time.",
        "advice": "If you can wait or are resting, check again later.",
        "actions": [
            {"type": "set_departure", "value": form_time(tomorrow), "label": "Check tomorrow 6 AM"}
        ],
    }
