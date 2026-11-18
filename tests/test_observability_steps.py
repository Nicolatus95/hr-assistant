"""Steps for the observability scenarios (pytest-bdd).

Assumed interfaces (the developer must follow them):

- ``app.main.create_app(config, llm, directory)`` writes one JSON line per
  event to ``sys.stdout`` (resolved when the event is written).
- ``Config`` has ``service_name``, ``slo_p95_ms``, ``langsmith_tracing``,
  ``hide_inputs`` and ``hide_outputs``.
- The page has an element with ``data-testid="request-id"``.
"""

import json
import time

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, scenarios, then, when

from app.config import load_config
from app.llm import FakeLLM
from app.main import create_app

scenarios("features/observability.feature")

QUESTION = "Who is EMP-0001?"
SECRET = "super-secret-failure-detail"


class BoomLLM:
    """Model that always fails with a secret message."""

    def complete(self, messages):
        raise RuntimeError(SECRET)


class SlowLLM:
    """Fake model that takes a few milliseconds per call."""

    def __init__(self, inner):
        self._inner = inner

    def complete(self, messages):
        time.sleep(0.02)
        return self._inner.complete(messages)


class Scene:
    """Mutable holder for the app settings chosen by the Given steps."""

    def __init__(self):
        self.env = {}
        self.llm = None


@pytest.fixture
def scene(capsys):
    """Settings for the scenario; depends on capsys so stdout is captured."""
    assert capsys is not None
    return Scene()


@pytest.fixture
def obs_client(scene, employees_path, directory):
    """Client built lazily from the scene (raises no server exceptions)."""
    env = {
        "EMPLOYEES_PATH": str(employees_path),
        "API_KEYS": "test:test-key-0123456789",
        **scene.env,
    }
    llm = scene.llm(directory) if scene.llm else FakeLLM(directory)
    app = create_app(load_config(env), llm, directory)
    test_client = TestClient(app, raise_server_exceptions=False)
    test_client.headers["X-API-Key"] = "test-key-0123456789"
    return test_client


@pytest.fixture
def log_lines(capsys):
    """Return a function that parses every JSON line written so far."""
    seen = []

    def _read():
        seen.extend(capsys.readouterr().out.splitlines())
        return [json.loads(line) for line in seen if line.startswith("{")]

    return _read


def events_named(log_lines, name):
    """Return the log events with the given name."""
    return [e for e in log_lines() if e["event"] == name]


@given("the model fails with a secret message")
def failing_model(scene):
    """Use a model that raises."""
    scene.llm = lambda _directory: BoomLLM()


@given(parsers.parse("the SLO target is {target:d} ms"))
def slo_target(scene, target):
    """Set the SLO target."""
    scene.env["SLO_P95_MS"] = str(target)


@given(parsers.parse("the SLO target is {target:d} ms and the model is slow"))
def slo_target_slow(scene, target):
    """Set the SLO target and slow the model down."""
    scene.env["SLO_P95_MS"] = str(target)
    scene.llm = lambda directory: SlowLLM(FakeLLM(directory))


@given("tracing is enabled but there is no API key")
def tracing_without_key(scene, monkeypatch):
    """Turn tracing on and make sure no key is present."""
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    scene.env["LANGSMITH_TRACING"] = "true"


@when(parsers.re(r'I ask "(?P<question>[^"]*)"$'), target_fixture="response")
def ask_question(obs_client, question):
    """Send a single question."""
    return obs_client.post("/ask", json={"question": question})


@when(
    parsers.re(r'I ask "(?P<question>[^"]*)" with the request id "(?P<rid>[^"]*)"'),
    target_fixture="response",
)
def ask_with_request_id(obs_client, question, rid):
    """Send a question with a client request id."""
    headers = {"X-Request-ID": rid}
    return obs_client.post("/ask", json={"question": question}, headers=headers)


@when("I request the metrics", target_fixture="metrics")
def request_metrics(obs_client):
    """Call GET /metrics."""
    return obs_client.get("/metrics").json()


@when("I open the home page", target_fixture="response")
def open_home(obs_client):
    """Call GET /."""
    return obs_client.get("/")


@then(parsers.parse("the response status is {code:d}"))
def check_status(response, code):
    """Check the HTTP status code."""
    assert response.status_code == code


@then("the header request id equals the body request id")
def check_ids_match(response):
    """The generated id is in both places and looks like a UUID."""
    header = response.headers["X-Request-ID"]
    assert header == response.json()["request_id"]
    assert len(header) == 36


@then(parsers.parse('the header request id is "{rid}"'))
def check_header_id(response, rid):
    """Check the header id."""
    assert response.headers["X-Request-ID"] == rid


@then(parsers.parse('the body request id is "{rid}"'))
def check_body_id(response, rid):
    """Check the body id."""
    assert response.json()["request_id"] == rid


@then(
    parsers.parse(
        'the log has a "request" event with method, path, status and latency'
    )
)
def check_request_event(log_lines, response):
    """The request event carries the HTTP data and the same id."""
    event = events_named(log_lines, "request")[0]
    assert (event["method"], event["path"], event["status"]) == ("POST", "/ask", 200)
    assert event["latency_ms"] >= 0
    assert event["request_id"] == response.headers["X-Request-ID"]


@then(parsers.parse('the log has an "agent_run" event with the run counters'))
def check_agent_run_event(log_lines):
    """The agent_run event carries counters and no text."""
    event = events_named(log_lines, "agent_run")[0]
    assert event["question_chars"] == len(QUESTION)
    assert event["history_messages"] == 0
    assert event["steps"] == 2
    assert event["tools"] == ["get_employee"]
    assert event["input_tokens"] > 0
    assert event["output_tokens"] > 0
    assert "stopped" in event


@then("every log line has ts, service, event and request_id")
def check_common_fields(log_lines):
    """All events share the required fields."""
    lines = log_lines()
    assert lines
    for line in lines:
        assert {"ts", "service", "event", "request_id"} <= set(line)
        assert line["service"] == "hr-assistant"


@then(parsers.parse('the log has an "audit" event for tool "{tool}" with args'))
def check_audit_event(log_lines, tool):
    """The audit event names the tool and its arguments."""
    event = events_named(log_lines, "audit")[0]
    assert event["action"] == "tool_call"
    assert event["tool"] == tool
    assert event["args"] == {"employee_id": "EMP-0001"}


@then("the log does not contain the question text")
def check_no_question(log_lines):
    """The question text never reaches the log."""
    lines = log_lines()
    assert lines
    assert QUESTION not in json.dumps(lines)


@then("the log does not contain the answer text")
def check_no_answer(log_lines, response):
    """The answer text never reaches the log."""
    answer = response.json()["answer"]
    assert answer not in json.dumps(log_lines())


@then("the error body has the detail \"internal error\" and a request id")
def check_error_body(response):
    """The 500 body hides the failure and names the request."""
    body = response.json()
    assert body["detail"] == "internal error"
    assert body["request_id"] == response.headers["X-Request-ID"]


@then('the log has an "error" event without the secret message')
def check_error_event(log_lines):
    """The error event has the error type but not its message."""
    lines = log_lines()
    event = next(e for e in lines if e["event"] == "error")
    assert "RuntimeError" in json.dumps(event)
    assert SECRET not in json.dumps(lines)


@then("the metrics have the required fields")
def check_metrics_shape(metrics):
    """The metrics body follows the specification."""
    assert isinstance(metrics["pid"], int)
    assert {"requests", "error_rate", "latency_ms", "tokens", "slo"} <= set(metrics)
    assert set(metrics["latency_ms"]) == {"p50", "p95"}
    assert set(metrics["tokens"]) == {"input", "output"}
    assert set(metrics["slo"]) == {"p95_ms_target", "met"}


@then(parsers.parse("the metrics count at least {count:d} request"))
def check_metrics_count(metrics, count):
    """At least the asked question was counted."""
    assert metrics["requests"] >= count
    assert metrics["tokens"]["input"] > 0


@then("the SLO is reported as met")
def check_slo_met(metrics):
    """The p95 is under the target."""
    assert metrics["slo"]["met"] is True


@then("the SLO is reported as not met")
def check_slo_not_met(metrics):
    """The p95 reached the target."""
    assert metrics["slo"]["p95_ms_target"] == 1
    assert metrics["slo"]["met"] is False


@then(parsers.parse('the page contains the test id "{test_id}"'))
def check_page(response, test_id):
    """Check the data-testid attribute."""
    assert f'data-testid="{test_id}"' in response.text
