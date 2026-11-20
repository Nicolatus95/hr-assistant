"""Shared fixtures for the HR Assistant tests.

Assumed interfaces (the developer must follow them):

- ``app.config.load_config(env: Mapping[str, str]) -> Config`` raising
  ``ValueError`` (or a subclass) on invalid values.
- ``app.directory.Directory(path)`` with ``get_employee`` and
  ``search_by_department``.
- ``app.llm.FakeLLM(directory)`` with ``complete(messages)`` returning an
  object with ``text``, ``input_tokens`` and ``output_tokens``.
- ``app.agent.Agent(llm, directory, max_steps)`` with ``run(messages)``
  returning an object with ``answer``, ``steps``, ``tools_used``,
  ``input_tokens`` and ``output_tokens``.
- ``app.main.create_app(config, llm, directory)``.

Session 5 additions (the developer must follow them):

- ``app.policies.Policies(path)`` with ``get_policy(topic)`` and
  ``list_policies()``.
- ``app.llm.FakeLLM(directory, policies=None)`` knows the policy keywords
  (older tests still call ``FakeLLM(directory)``).
- ``app.main.create_app(config, llm, directory, clock=None, tracer=None,
  policies=None)``; ``tracer`` is an ``app.tracing.Tracer``.
- Audit events are log lines with ``event == "audit"`` and an ``action``.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import load_config
from app.directory import Directory
from app.llm import FakeLLM
from app.main import create_app
from app.policies import Policies

PRODUCT_DIR = Path(__file__).resolve().parents[1]
EMPLOYEES_FILE = PRODUCT_DIR / "data" / "employees.json"
PRICES_FILE = PRODUCT_DIR / "data" / "model_prices.json"
POLICIES_FILE = PRODUCT_DIR / "data" / "policies.json"
TEST_API_KEY = "test-key-0123456789"
GATEWAY_ENV = {
    "MODEL_PROVIDER": "gateway",
    "CF_ACCOUNT_ID": "acc",
    "CF_GATEWAY_ID": "gw",
    "CF_API_TOKEN": "secret-token",
}


@pytest.fixture
def employees_path():
    """Path of the sample employees file."""
    return EMPLOYEES_FILE


@pytest.fixture
def directory(employees_path):
    """Directory loaded with the sample employees."""
    return Directory(employees_path)


@pytest.fixture
def make_client(employees_path, directory):
    """Build a test client with the given environment overrides."""

    def _make(tracer=None, **env):
        settings = {
            "EMPLOYEES_PATH": str(employees_path),
            "PRICES_PATH": str(PRICES_FILE),
            "POLICIES_PATH": str(POLICIES_FILE),
            "API_KEYS": f"test:{TEST_API_KEY}",
            **env,
        }
        config = load_config(settings)
        llm = FakeLLM(directory, Policies(POLICIES_FILE))
        extra = {"tracer": tracer} if tracer is not None else {}
        test_client = TestClient(
            create_app(config, llm, directory, **extra),
            raise_server_exceptions=False,
        )
        test_client.headers["X-API-Key"] = TEST_API_KEY
        return test_client

    return _make


class ScriptedLLM:
    """Model that replays prepared replies and records what it received."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages, model=None):
        """Return the next reply; the last one repeats forever."""
        self.calls.append(list(messages))
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return SimpleNamespace(
            text=text, input_tokens=10, output_tokens=2, model=model or "fake"
        )


@pytest.fixture
def scripted_llm():
    """Clase ScriptedLLM, para construir modelos con respuestas preparadas."""
    return ScriptedLLM


@pytest.fixture
def make_scripted_client(employees_path, directory):
    """Build ``(client, llm)`` where the model replays the given texts."""

    def _make(replies, **env):
        settings = {
            "EMPLOYEES_PATH": str(employees_path),
            "PRICES_PATH": str(PRICES_FILE),
            "POLICIES_PATH": str(POLICIES_FILE),
            "API_KEYS": f"test:{TEST_API_KEY}",
            **env,
        }
        llm = ScriptedLLM(replies)
        app = create_app(load_config(settings), llm, directory)
        test_client = TestClient(app, raise_server_exceptions=False)
        test_client.headers["X-API-Key"] = TEST_API_KEY
        return test_client, llm

    return _make


@pytest.fixture
def read_log(capsys):
    """Return a function that parses every JSON log line written so far."""
    seen = []

    def _read():
        seen.extend(capsys.readouterr().out.splitlines())
        return [json.loads(line) for line in seen if line.startswith("{")]

    return _read


@pytest.fixture
def audits():
    """Return a function that filters audit events by action."""

    def _filter(events, action):
        return [
            e for e in events if e["event"] == "audit" and e.get("action") == action
        ]

    return _filter


@pytest.fixture
def make_gateway_client(employees_path, directory):
    """Construye un cliente con GatewayLLM sobre un transporte simulado.

    Recibe un ``handler(request) -> httpx.Response``; no usa red.
    """

    def _make(handler, **env):
        # Se importan aqui para que un fallo de import no rompa todo el modulo.
        import httpx  # pylint: disable=import-outside-toplevel
        from app.llm import GatewayLLM  # pylint: disable=import-outside-toplevel

        settings = {
            "EMPLOYEES_PATH": str(employees_path),
            "PRICES_PATH": str(PRICES_FILE),
            **GATEWAY_ENV,
            "API_KEYS": f"test:{TEST_API_KEY}",
            **env,
        }
        config = load_config(settings)
        llm = GatewayLLM(config, transport=httpx.MockTransport(handler))
        test_client = TestClient(create_app(config, llm, directory))
        test_client.headers["X-API-Key"] = TEST_API_KEY
        return test_client

    return _make


@pytest.fixture
def client(make_client):
    """Test client with the default configuration."""
    return make_client()
