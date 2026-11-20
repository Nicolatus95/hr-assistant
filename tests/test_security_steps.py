"""Steps for the security scenarios (pytest-bdd).

Assumed interfaces (the developer must follow them):

- Audit events are log lines with ``event == "audit"`` and an ``action``:
  ``pii_detected`` has ``where`` and ``types``; ``output_blocked`` has
  ``reason``.
- ``POST /ask`` returns ``pii_types`` and ``output_blocked``; ``/metrics``
  returns ``requests_by_agent``, ``pii_detections`` and ``outputs_blocked``.
- A blocked answer is exactly ``BLOCK_MESSAGE``.
"""

import json

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/security.feature")

BLOCK_MESSAGE = "No puedo mostrar esa respuesta. Intenta con otra pregunta."


class Scene:
    """Holds what the Given steps decide before the service is built."""

    def __init__(self):
        self.reply = None


@pytest.fixture
def scene(capsys):
    """Scenario settings; depends on capsys so stdout is captured."""
    assert capsys is not None
    return Scene()


@pytest.fixture
def service(scene, client, make_scripted_client):
    """Client with the fake model, or a scripted one if a reply was set."""
    if scene.reply is None:
        return client
    scripted, _llm = make_scripted_client([json.dumps({"answer": scene.reply})])
    return scripted


@given(parsers.parse('the model answers "{text}"'))
def model_answers(scene, text):
    """Make the model reply with a fixed final answer."""
    scene.reply = text


@when(parsers.parse('I ask "{question}"'), target_fixture="response")
def ask_question(service, question):
    """Send one question."""
    return service.post("/ask", json={"question": question})


@when(
    parsers.parse(
        'I ask "{question}" with a history message of {size:d} characters'
    ),
    target_fixture="response",
)
def ask_with_long_history(service, question, size):
    """Send a history whose only message is too long."""
    history = [{"role": "user", "content": "x" * size}]
    return service.post("/ask", json={"question": question, "history": history})


@when(
    parsers.parse('I ask "{question}" with {count:d} history messages'),
    target_fixture="response",
)
def ask_with_many_messages(service, question, count):
    """Send a history with many short messages."""
    history = [{"role": "user", "content": "hola"}] * count
    return service.post("/ask", json={"question": question, "history": history})


@when(parsers.parse('I open "{path}"'), target_fixture="response")
def open_path(service, path):
    """Call an open endpoint."""
    return service.get(path)


@when("I request the metrics", target_fixture="metrics")
def request_metrics(service):
    """Read /metrics with the test key."""
    return service.get("/metrics").json()


@then(parsers.parse("the response status is {code:d}"))
def check_status(response, code):
    """Check the HTTP status code."""
    assert response.status_code == code


@then(parsers.parse('the pii types are "{types}"'))
def check_pii_types(response, types):
    """Check the sorted list of PII types in the response."""
    assert response.json()["pii_types"] == types.split(",")


@then(
    parsers.parse(
        'the audit log has a pii_detected event for "{where}" with types "{types}"'
    )
)
def check_pii_audit(read_log, audits, where, types):
    """The audit says where and which types, in fields other than the value."""
    found = audits(read_log(), "pii_detected")
    assert any(e["where"] == where and e["types"] == types.split(",") for e in found)


@then(parsers.parse('the log and the response do not contain "{secret}"'))
def check_no_leak(read_log, response, secret):
    """A sensitive value is neither logged nor returned."""
    assert secret not in json.dumps(read_log())
    assert secret not in response.text


@then("the security headers are present")
def check_security_headers(response):
    """The three hardening headers are on the response."""
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


@then("the response must not be cached")
def check_no_store(response):
    """POST /ask forbids caching."""
    assert response.headers["Cache-Control"] == "no-store"


@then("the answer is the block message")
def check_block_message(response):
    """The unsafe answer was replaced."""
    assert response.json()["answer"] == BLOCK_MESSAGE


@then("the output was blocked")
def check_output_blocked(response):
    """The response flags the block."""
    assert response.json()["output_blocked"] is True


@then(parsers.parse('the audit log has an output_blocked event with reason "{why}"'))
def check_block_audit(read_log, audits, why):
    """The audit gives the reason, never the text."""
    found = audits(read_log(), "output_blocked")
    assert [e["reason"] for e in found] == [why]


@then(parsers.parse('the requests by agent are "{one}" {n1:d} and "{two}" {n2:d}'))
def check_requests_by_agent(metrics, one, n1, two, n2):
    """Each specialist counted its own requests."""
    assert metrics["requests_by_agent"] == {one: n1, two: n2}


@then("the metrics include the pii and blocked counters")
def check_business_counters(metrics):
    """The other business metrics exist and start at zero."""
    assert metrics["pii_detections"] == 0
    assert metrics["outputs_blocked"] == 0
    assert "cost_usd_by_agent" in metrics
