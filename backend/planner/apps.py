"""Registers the planner app with Django. It has no database models."""

from django.apps import AppConfig


class PlannerConfig(AppConfig):
    """The trip planner: routes, weather risk and recommendations."""

    name = "planner"
