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
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import load_config
from app.directory import Directory
from app.llm import FakeLLM
from app.main import create_app

PRODUCT_DIR = Path(__file__).resolve().parents[1]
EMPLOYEES_FILE = PRODUCT_DIR / "data" / "employees.json"
PRICES_FILE = PRODUCT_DIR / "data" / "model_prices.json"
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

    def _make(**env):
        settings = {
            "EMPLOYEES_PATH": str(employees_path),
            "PRICES_PATH": str(PRICES_FILE),
            "API_KEYS": f"test:{TEST_API_KEY}",
            **env,
        }
        config = load_config(settings)
        test_client = TestClient(create_app(config, FakeLLM(directory), directory))
        test_client.headers["X-API-Key"] = TEST_API_KEY
        return test_client

    return _make


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
