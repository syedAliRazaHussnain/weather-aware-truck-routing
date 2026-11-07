"""Problems talking to outside services, named by what they mean for the trip.

service.py turns each one into a plain message and one-tap actions for the
driver (see "When something goes wrong" in the README).
"""


class ClientError(Exception):
    """Base class: something an outside service couldn't do for us."""


class NoRoadNearby(ClientError):
    """A point has no truck road within the snapping radius (#6)."""

    def __init__(self, index: int):
        super().__init__(f"no truck road near point {index}")
        self.index = index  # which point in the request: 0 = origin, last = destination


class NoTruckRoute(ClientError):
    """Both ends are on roads, but no truck-legal route joins them."""


class TripTooLong(ClientError):
    """The trip is longer than the free routing service allows (#61)."""


class AlternativesNotAllowed(ClientError):
    """ORS refused alternative routes for this distance, so detours are used (#14)."""


class ServiceBusy(ClientError):
    """The service is rate-limiting us; retrying straight away would make it worse."""

    def __init__(self, service: str):
        super().__init__(f"{service} is busy")
        self.service = service


class ServiceUnavailable(ClientError):
    """The service didn't answer properly, even after one retry."""

    def __init__(self, service: str):
        super().__init__(f"{service} is unavailable")
        self.service = service


class MissingWeather(ClientError):
    """A forecast came back with empty values; never treated as Low (#39)."""
