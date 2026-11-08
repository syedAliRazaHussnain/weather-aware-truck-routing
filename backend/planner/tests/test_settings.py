"""Production settings, loaded in a fresh process so the test settings don't interfere."""

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def _load_settings(env: dict) -> dict:
    """Import config.settings in a clean subprocess with only `env` set, and return a few values."""
    code = (
        "import json; from config import settings as s; "
        "print(json.dumps({'hosts': s.ALLOWED_HOSTS, 'debug': s.DEBUG, "
        "'cors': s.CORS_ALLOWED_ORIGINS}))"
    )
    base = {"PATH": os.environ["PATH"], "ORS_API_KEY": "", "DJANGO_SECRET_KEY": "x"}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env=base | env,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": result.returncode,
        "stderr": result.stderr,
        **(json.loads(result.stdout) if result.returncode == 0 else {}),
    }


def test_render_domain_is_allowed_without_typing_it():
    """On Render, the service's own domain is added to the allowed hosts automatically."""
    loaded = _load_settings({"RENDER_EXTERNAL_HOSTNAME": "weather-routing-api.onrender.com"})
    assert "weather-routing-api.onrender.com" in loaded["hosts"]


def test_debug_is_off_unless_asked_for():
    """Production runs with DEBUG off when DJANGO_DEBUG isn't set."""
    assert _load_settings({})["debug"] is False


def test_cors_origins_come_from_the_environment():
    """The Vercel URL set on Render becomes the allowed CORS origin."""
    loaded = _load_settings({"CORS_ALLOWED_ORIGINS": "https://a.vercel.app, https://b.example"})
    assert loaded["cors"] == ["https://a.vercel.app", "https://b.example"]


def test_server_refuses_to_start_without_a_secret_key():
    """Without DJANGO_SECRET_KEY outside debug, the server refuses to start."""
    loaded = _load_settings({"DJANGO_SECRET_KEY": ""})
    assert loaded["returncode"] != 0
    assert "DJANGO_SECRET_KEY" in loaded["stderr"]
