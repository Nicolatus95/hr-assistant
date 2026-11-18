"""Steps for the production access scenarios (pytest-bdd).

Assumed interfaces (the developer must follow them):

- ``Config`` reads ``API_KEYS`` and ``RATE_LIMIT_PER_MINUTE``.
- ``app.main.create_app(config, llm, directory, clock=None)`` accepts an
  injected clock with a ``now()`` method that returns an aware datetime.
- Log events ``request``, ``agent_run`` and ``audit`` carry ``client``.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, scenarios, then, when

from app.config import load_config
from app.llm import FakeLLM
from app.main import create_app

scenarios("features/production.feature")


class FakeClock:
    """Clock that only moves when the test says so."""

    def __init__(self):
        self._now = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def now(self):
        """Return the frozen time."""
        return self._now

    def advance(self, seconds):
        """Move the time forward."""
        self._now += timedelta(seconds=seconds)


class Scene:
    """Mutable holder for the clients and limits chosen by the Given steps."""

    def __init__(self):
        self.clients = {}
        self.env = {}
        self.clock = FakeClock()

    def key_of(self, name):
        """Return the secret key of a client."""
        return self.clients[name]


@pytest.fixture
def scene(capsys):
    """Scenario settings; depends on capsys so stdout is captured."""
    assert capsys is not None
    return Scene()


@pytest.fixture
def service(scene, employees_path, directory):
    """Application built lazily from the scene, with the fake clock."""
    pairs = ",".join(f"{n}:{k}" for n, k in scene.clients.items())
    env = {"EMPLOYEES_PATH": str(employees_path), "API_KEYS": pairs, **scene.env}
    app = create_app(load_config(env), FakeLLM(directory), directory, scene.clock)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def log_lines(capsys):
    """Return a function that parses every JSON line written so far."""
    seen = []

    def _read():
        seen.extend(capsys.readouterr().out.splitlines())
        return [json.loads(line) for line in seen if line.startswith("{")]

    return _read


def raw_log(log_lines):
    """Return the whole log as one text."""
    return json.dumps(log_lines())


@given(parsers.parse('the service knows the client "{name}"'))
def known_client(scene, name):
    """Register a client with a long secret key."""
    scene.clients[name] = f"{name}-secret-key-0123456789"


@given(parsers.parse("the limit is {limit:d} requests per minute"))
def set_limit(scene, limit):
    """Set the rate limit."""
    scene.env["RATE_LIMIT_PER_MINUTE"] = str(limit)


@when(
    parsers.parse('client "{name}" asks "{question}"'),
    target_fixture="response",
)
def client_asks(service, scene, name, question):
    """Ask one question with the key of a client."""
    headers = {"X-API-Key": scene.key_of(name)}
    return service.post("/ask", json={"question": question}, headers=headers)


@when(
    parsers.parse('client "{name}" asks {count:d} times'),
    target_fixture="response",
)
def client_asks_many(service, scene, name, count):
    """Ask the same question several times and keep the last response."""
    headers = {"X-API-Key": scene.key_of(name)}
    response = None
    for _ in range(count):
        response = service.post(
            "/ask", json={"question": "Who is EMP-0001?"}, headers=headers
        )
    return response


@when(parsers.parse('I ask "{question}" without a key'), target_fixture="response")
def ask_without_key(service, question):
    """Ask with no X-API-Key header."""
    return service.post("/ask", json={"question": question})


@when(
    parsers.parse('I ask "{question}" with the key "{key}"'),
    target_fixture="response",
)
def ask_with_key(service, question, key):
    """Ask with an arbitrary key."""
    return service.post(
        "/ask", json={"question": question}, headers={"X-API-Key": key}
    )


@when("I request the metrics without a key", target_fixture="response")
def metrics_without_key(service):
    """Call GET /metrics with no key."""
    return service.get("/metrics")


@when(parsers.parse('I open "{path}" without a key'), target_fixture="response")
def open_path(service, path):
    """Call an open endpoint with no key."""
    return service.get(path)


@when(parsers.parse("the clock advances {seconds:d} seconds"))
def advance_clock(scene, seconds):
    """Move the injected clock forward."""
    scene.clock.advance(seconds)


@then(parsers.parse("the response status is {code:d}"))
def check_status(response, code):
    """Check the HTTP status code."""
    assert response.status_code == code


@then(parsers.parse('the error detail is "{detail}"'))
def check_detail(response, detail):
    """Check the exact detail of the error body."""
    assert response.json()["detail"] == detail


@then(
    parsers.parse("the Retry-After header is between {low:d} and {high:d} seconds")
)
def check_retry_after(response, low, high):
    """Retry-After is an integer number of seconds."""
    assert low <= int(response.headers["Retry-After"]) <= high


@then(
    parsers.parse(
        'the request and agent_run log events carry the client "{name}"'
    )
)
def check_client_in_events(log_lines, name):
    """The request and agent_run events name the client."""
    events = log_lines()
    for event_name in ("request", "agent_run"):
        found = [e for e in events if e["event"] == event_name]
        assert found and all(e["client"] == name for e in found)


@then(parsers.parse('the audit log event carries the client "{name}"'))
def check_client_in_audit(log_lines, name):
    """The audit event names the client."""
    audits = [e for e in log_lines() if e["event"] == "audit"]
    assert audits
    assert all(e["client"] == name for e in audits)


@then(parsers.parse('the log does not contain the key of "{name}"'))
def check_no_client_key(log_lines, scene, name):
    """The secret of a known client is never logged."""
    assert scene.key_of(name) not in raw_log(log_lines)


@then(parsers.parse('the log and the response do not contain "{secret}"'))
def check_no_secret(log_lines, response, secret):
    """A rejected key is not echoed in the log or in the error."""
    assert secret not in raw_log(log_lines)
    assert secret not in response.text
