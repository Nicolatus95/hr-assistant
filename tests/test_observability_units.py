"""Unit tests for the observability modules.

Assumed interfaces (the developer must follow them):

- ``app.clock.SystemClock().now()`` returns a timezone-aware UTC datetime;
  any object with ``now()`` can be injected as a clock.
- ``app.context.request_id_var`` is a ``ContextVar`` with the current id.
- ``app.logging_setup.JsonLogger(service, clock, stream)`` with
  ``emit(event, **fields)`` writing one JSON line with ``ts``, ``service``,
  ``event`` and ``request_id`` (read from ``request_id_var``).
- ``app.metrics.Metrics(slo_p95_ms)`` with ``record_request(latency_ms,
  failed)``, ``record_tokens(input_tokens, output_tokens)`` and
  ``snapshot()`` returning the body of ``GET /metrics``.
- ``app.tracing.build_tracer(config, env)`` returns an object with
  ``enabled`` and ``wrap(func, name)``; disabled means ``wrap`` returns
  ``func`` unchanged and nothing connects to the network.
- ``Agent(llm, directory, max_steps, audit=None, tracer=None)``: ``audit``
  is called as ``audit(tool, args)``; ``AgentResult.stopped`` is ``True``
  only when the step cap ended the run.
"""

import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.agent import Agent
from app.clock import SystemClock
from app.config import load_config
from app.context import request_id_var
from app.logging_setup import JsonLogger
from app.metrics import Metrics
from app.tracing import build_tracer


class FakeClock:
    """Clock frozen at a known instant."""

    def now(self):
        return datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def emit_one(**fields):
    """Emit a single event and return the parsed line."""
    stream = io.StringIO()
    token = request_id_var.set("req-1")
    try:
        JsonLogger("svc", FakeClock(), stream).emit("request", **fields)
    finally:
        request_id_var.reset(token)
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def test_system_clock_returns_utc_time():
    now = SystemClock().now()
    assert now.utcoffset().total_seconds() == 0


def test_log_line_has_the_required_fields():
    line = emit_one(status=200)
    assert line["service"] == "svc"
    assert line["event"] == "request"
    assert line["request_id"] == "req-1"
    assert line["status"] == 200


def test_log_timestamp_is_iso_8601_in_utc_from_the_clock():
    line = emit_one()
    parsed = datetime.fromisoformat(line["ts"].replace("Z", "+00:00"))
    assert parsed == FakeClock().now()


def test_metrics_with_no_data_are_zero_and_meet_the_slo():
    body = Metrics(slo_p95_ms=2000).snapshot()
    assert body["requests"] == 0
    assert body["error_rate"] == 0
    assert body["latency_ms"] == {"p50": 0, "p95": 0}
    assert body["slo"] == {"p95_ms_target": 2000, "met": True}


def test_metrics_percentiles_and_error_rate_with_many_requests():
    metrics = Metrics(slo_p95_ms=2000)
    for latency in range(1, 101):
        metrics.record_request(latency, failed=latency > 90)
    metrics.record_tokens(5, 3)
    body = metrics.snapshot()
    assert body["requests"] == 100
    assert body["error_rate"] == pytest.approx(0.1)
    assert body["latency_ms"]["p50"] == pytest.approx(50, abs=1.5)
    assert body["latency_ms"]["p95"] == pytest.approx(95, abs=1.5)
    assert body["tokens"] == {"input": 5, "output": 3}


def test_slo_is_not_met_when_p95_equals_the_target():
    metrics = Metrics(slo_p95_ms=100)
    metrics.record_request(100, failed=False)
    assert metrics.snapshot()["slo"]["met"] is False
    assert Metrics(slo_p95_ms=101).snapshot()["slo"]["met"] is True


def test_tracing_is_a_no_op_without_an_api_key():
    config = load_config({"LANGSMITH_TRACING": "true"})
    tracer = build_tracer(config, {"LANGSMITH_TRACING": "true"})

    def work():
        return 1

    assert tracer.enabled is False
    assert tracer.wrap(work, "work") is work


def test_the_api_key_never_appears_when_the_tracer_is_shown():
    env = {"LANGSMITH_TRACING": "false", "LANGSMITH_API_KEY": "lsv2-top-secret"}
    tracer = build_tracer(load_config(env), env)
    assert "lsv2-top-secret" not in repr(tracer)
    assert tracer.enabled is False


def test_observability_config_has_safe_defaults():
    config = load_config({})
    assert config.service_name == "hr-assistant"
    assert config.slo_p95_ms == 2000
    assert config.langsmith_tracing is False
    assert config.hide_inputs is True
    assert config.hide_outputs is True


@pytest.mark.parametrize(
    "env",
    [
        {"HIDE_INPUTS": "maybe"},
        {"LANGSMITH_TRACING": "yes please"},
        {"SLO_P95_MS": "0"},
    ],
)
def test_invalid_observability_values_are_rejected(env):
    with pytest.raises(ValueError):
        load_config(env)


def scripted(*texts):
    """Model that replays the given texts and repeats the last one."""
    replies = list(texts)

    def complete(_messages):
        text = replies.pop(0) if len(replies) > 1 else replies[0]
        return SimpleNamespace(text=text, input_tokens=1, output_tokens=1)

    return SimpleNamespace(complete=complete)


def test_agent_audits_each_tool_call(directory):
    calls = []
    tool = {"tool": "get_employee", "args": {"employee_id": "EMP-0004"}}
    llm = scripted(json.dumps(tool), json.dumps({"answer": "ok"}))
    agent = Agent(
        llm, directory, 3, audit=lambda name, args: calls.append((name, args))
    )
    result = agent.run([{"role": "user", "content": "q"}])
    assert calls == [("get_employee", {"employee_id": "EMP-0004"})]
    assert result.stopped is False


def test_agent_reports_stopped_when_it_reaches_the_step_cap(directory):
    tool = {"tool": "get_employee", "args": {"employee_id": "EMP-0001"}}
    agent = Agent(scripted(json.dumps(tool)), directory, 2, audit=lambda *_: None)
    result = agent.run([{"role": "user", "content": "q"}])
    assert result.stopped is True
    assert result.steps == 2
