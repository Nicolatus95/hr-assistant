"""Tracing tests with a fake LangSmith client: no network is used.

Assumed interfaces (the developer must follow them):

- ``app.tracing.build_tracer(config, env, client=None)``: when tracing is on
  and a key is in ``env``, it uses the injected ``client`` instead of
  creating a real one.
- ``app.main.create_app(config, llm, directory, tracer=tracer)``.
- The traces go to ``config.langsmith_project`` (``session_name`` of each run).
- Tree: ``hr_request`` > ``supervisor`` > ``agent:<name>`` > ``llm_call`` and
  ``tool:<name>``.
- Metadata of ``hr_request``: see section 12 of ``spec/05-reto.md``.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import load_config
from app.llm import FakeLLM, LLMUnavailable
from app.main import create_app
from app.policies import Policies
from app.tracing import build_tracer

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
EMPLOYEES_FILE = DATA_DIR / "employees.json"
PRICES_FILE = DATA_DIR / "model_prices.json"
POLICIES_FILE = DATA_DIR / "policies.json"
TEST_API_KEY = "test-key-0123456789"
CURP = "GARC850101HDFRRL09"
START_KEYS = {
    "request_id",
    "client",
    "environment",
    "agent",
    "agent_route",
    "model",
    "route",
}
END_KEYS = {
    "steps",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "cached_calls",
    "pii_types",
    "output_blocked",
    "stopped",
}


class FakeLangSmith:
    """Records the runs that LangSmith would receive."""

    tracing_queue = None

    def __init__(self):
        self.runs = {}

    def create_run(self, **kwargs):
        """Store a run when it starts."""
        extra = dict(kwargs.get("extra") or {})
        extra["metadata"] = dict(extra.get("metadata") or {})
        self.runs[str(kwargs["id"])] = {**kwargs, "extra": extra}

    def update_run(self, run_id, **kwargs):
        """Merge the closing data of a run (outputs, error, metadata)."""
        run = self.runs[str(run_id)]
        meta = (kwargs.pop("extra", None) or {}).get("metadata") or {}
        run["extra"]["metadata"].update(meta)
        run.update({k: v for k, v in kwargs.items() if v is not None})

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None

    def named(self, name):
        """Return the runs with that name."""
        return [r for r in self.runs.values() if r["name"] == name]

    def parent_name(self, run):
        """Return the name of the parent of a run, or None."""
        parent = self.runs.get(str(run.get("parent_run_id")))
        return parent["name"] if parent else None

    def metadata(self, name):
        """Return the metadata of the only run with that name."""
        (run,) = self.named(name)
        return run["extra"]["metadata"]


def build_service(llm, directory, **env):
    """Create an app with tracing on and a fake client; return both."""
    settings = {
        "EMPLOYEES_PATH": str(EMPLOYEES_FILE),
        "PRICES_PATH": str(PRICES_FILE),
        "POLICIES_PATH": str(POLICIES_FILE),
        "API_KEYS": f"test:{TEST_API_KEY}",
        "LANGSMITH_TRACING": "true",
        "LANGSMITH_PROJECT": "hr-test",
        **env,
    }
    config = load_config(settings)
    fake = FakeLangSmith()
    tracer = build_tracer(config, {"LANGSMITH_API_KEY": "ls-test-key"}, client=fake)
    app = create_app(config, llm, directory, tracer=tracer)
    client = TestClient(app, raise_server_exceptions=False)
    client.headers["X-API-Key"] = TEST_API_KEY
    return client, fake


def fake_model(directory):
    """Return the deterministic model that knows the policies."""
    return FakeLLM(directory, Policies(POLICIES_FILE))


def test_trace_has_the_agent_tree_and_the_metadata(directory):
    client, fake = build_service(fake_model(directory), directory)
    question = f"Mi CURP es {CURP}. Cuantos dias de vacaciones tengo?"
    assert client.post("/ask", json={"question": question}).status_code == 200
    assert fake.parent_name(fake.named("supervisor")[0]) == "hr_request"
    assert fake.parent_name(fake.named("agent:policies")[0]) == "supervisor"
    assert fake.parent_name(fake.named("llm_call")[0]) == "agent:policies"
    assert fake.parent_name(fake.named("tool:get_policy")[0]) == "agent:policies"
    meta = fake.metadata("hr_request")
    assert (START_KEYS | END_KEYS) <= set(meta)
    assert (meta["agent"], meta["pii_types"]) == ("policies", ["CURP"])
    assert meta["output_blocked"] is False
    (root,) = fake.named("hr_request")
    assert root["session_name"] == "hr-test"
    assert {"policies", "development"} <= set(root["tags"])
    everything = json.dumps(fake.runs, default=str)
    assert CURP not in everything
    assert "ls-test-key" not in everything


def test_hidden_inputs_and_outputs_leave_no_text_in_the_trace(directory):
    client, fake = build_service(
        fake_model(directory), directory, HIDE_INPUTS="true", HIDE_OUTPUTS="true"
    )
    client.post("/ask", json={"question": "Cuantos dias de vacaciones tengo?"})
    assert fake.runs
    for run in fake.runs.values():
        payload = json.dumps([run.get("inputs"), run.get("outputs")], default=str)
        assert "vacaciones" not in payload
        assert "12 días" not in payload
    assert "vacaciones" not in json.dumps(fake.metadata("hr_request"))


def test_model_failure_marks_the_request_trace_with_an_error(directory):
    class DownLLM:
        """Model that always fails."""

        def complete(self, _messages, _model=None):
            raise LLMUnavailable("down")

    client, fake = build_service(DownLLM(), directory)
    response = client.post("/ask", json={"question": "Who is EMP-0001?"})
    assert response.status_code == 502
    (root,) = fake.named("hr_request")
    assert root.get("error")
