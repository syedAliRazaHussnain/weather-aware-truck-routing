"""Checks what the browser sends before any planning happens.

Comments like "#5" point to the numbered assumptions in the README.
"""

from datetime import datetime

from rest_framework import serializers

from planner.service import INTERVALS, TripRequest

MAX_LOAD_LB = 150_000  # #2: catches typos like an extra zero


class PlaceSerializer(serializers.Serializer):
    """A place the driver picked: coordinates, not free text (#5)."""

    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    label = serializers.CharField(required=False, allow_blank=True, max_length=200, default="")


class PlanRequestSerializer(serializers.Serializer):
    """The trip form: two places, a local departure time, the load and the interval."""

    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure = serializers.CharField(max_length=32)
    load_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)
    interval_mi = serializers.ChoiceField(choices=INTERVALS, default=25)

    def validate_departure(self, value: str) -> datetime:
        """A plain local time like 2026-11-08T08:00, read in the origin's time zone (#7)."""
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            raise serializers.ValidationError(
                "Use a date and time like 2026-11-08T08:00."
            ) from None
        if moment.tzinfo is not None:
            raise serializers.ValidationError("Send the origin's local time without a time zone.")
        return moment

    def to_trip(self) -> TripRequest:
        """The checked form as a TripRequest for the planner."""
        data = self.validated_data
        return TripRequest(
            origin=(data["origin"]["lat"], data["origin"]["lon"]),
            destination=(data["destination"]["lat"], data["destination"]["lon"]),
            departure_local=data["departure"],
            load_lb=data["load_lb"],
            interval_mi=data["interval_mi"],
            origin_label=data["origin"]["label"],
            destination_label=data["destination"]["label"],
        )


class PlacesQuerySerializer(serializers.Serializer):
    """Autocomplete: what the driver has typed so far, and where the map is looking (#4)."""

    q = serializers.CharField(min_length=2, max_length=100)
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False)
    lon = serializers.FloatField(min_value=-180, max_value=180, required=False)
