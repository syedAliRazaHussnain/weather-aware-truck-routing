"""The HTTP API: three thin endpoints that hand over to service.py.

Every error, expected or not, goes back as {"error", "message", "actions"} so
the UI can always show a plain message and buttons (#59).
"""

import logging
from functools import cache

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from planner.clients.errors import ServiceBusy, ServiceUnavailable
from planner.clients.ors import OrsClient
from planner.clients.weather import WeatherClient
from planner.serializers import PlacesQuerySerializer, PlanRequestSerializer
from planner.service import PlanProblem, plan_trip, retry_action, service_problem

log = logging.getLogger(__name__)


@cache
def clients() -> tuple[OrsClient, WeatherClient]:
    """One ORS and one weather client per server process, so the weather cache is shared."""
    if not settings.ORS_API_KEY:
        raise PlanProblem(
            "server_not_configured",
            "The server isn't set up for routing yet.",
            [retry_action()],
            status=503,
        )
    return OrsClient(settings.ORS_API_KEY), WeatherClient()


def problem_response(problem: PlanProblem) -> Response:
    """A PlanProblem as an HTTP response."""
    return Response(problem.to_dict(), status=problem.status)


@api_view(["GET"])
def health(request):
    """Lets the page wake the free server as soon as it opens (#58)."""
    return Response({"status": "ok"})


@api_view(["GET"])
def places(request):
    """Place suggestions as the driver types, ranked near the map view (#4)."""
    query = PlacesQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    data = query.validated_data
    focus = (data["lat"], data["lon"]) if "lat" in data and "lon" in data else None
    try:
        ors, _ = clients()
        found = ors.autocomplete(data["q"], focus=focus)
    except PlanProblem as problem:
        return problem_response(problem)
    except (ServiceBusy, ServiceUnavailable) as error:
        return problem_response(service_problem(error))
    return Response([{"label": p.label, "lat": p.lat, "lon": p.lon} for p in found])


@api_view(["POST"])
def plan(request):
    """Plan a trip: routes, checkpoint risk, heatmap and the recommendation."""
    form = PlanRequestSerializer(data=request.data)
    form.is_valid(raise_exception=True)
    try:
        ors, weather = clients()
        result = plan_trip(form.to_trip(), ors, weather)
    except PlanProblem as problem:
        return problem_response(problem)
    return Response(result)


def api_exception_handler(exc, context):
    """Bad input and unexpected crashes in the same shape as every other problem."""
    if isinstance(exc, ValidationError):
        return Response(
            {
                "error": "invalid_input",
                "message": "Please check the highlighted fields.",
                "fields": exc.detail,
                "actions": [],
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    response = exception_handler(exc, context)
    if response is not None:
        return response
    log.exception("Unexpected error while handling %s", context.get("request"))
    return Response(
        {
            "error": "server_error",
            "message": "Something went wrong on our side. Your trip details are kept.",
            "actions": [retry_action()],
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
