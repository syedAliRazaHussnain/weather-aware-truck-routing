"""Stand-ins for HTTP, so client tests run offline and never use API quota."""

import json
from pathlib import Path

import requests

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict:
    """A saved API answer from tests/fixtures."""
    return json.loads((FIXTURES / name).read_text())


class FakeResponse:
    """Just enough of requests.Response for the clients."""

    def __init__(self, status_code: int, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeSession:
    """Answers requests from a queue and records what was asked."""

    def __init__(self, *answers):
        self.answers = list(answers)  # FakeResponse objects or exceptions to raise
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)


TIMEOUT = requests.Timeout("timed out")
