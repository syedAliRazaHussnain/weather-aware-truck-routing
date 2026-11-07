"""Settings for the test suite: debug mode and a fake API key, so tests never
need real secrets and can never call the real services by accident."""

import os

os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("ORS_API_KEY", "test-key")

from config.settings import *  # noqa: E402, F403
