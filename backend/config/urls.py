"""URL routes. The whole API lives under /api/."""

from django.urls import path

from planner import views

urlpatterns = [
    path("api/health", views.health),
    path("api/places", views.places),
    path("api/plan", views.plan),
]
