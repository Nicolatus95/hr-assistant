"""Unit tests for the findings fixed after the QA review."""

import httpx
import pytest
from conftest import EMPLOYEES_FILE, GATEWAY_ENV, PRICES_FILE

from app.config import Config, load_config
from app.llm import FakeLLM, GatewayLLM
from app.main import create_app
from app.pricing import Pricing


def _config(**overrides):
    """Build a Config that points at the sample data files."""
    return Config(employees_path=EMPLOYEES_FILE, prices_path=PRICES_FILE, **overrides)


@pytest.mark.parametrize("field", ["model_small", "model_large"])
def test_startup_fails_when_a_configured_model_has_no_price(field):
    """A model missing from the price table stops create_app with ValueError."""
    config = _config(**{field: "unknown-model"})
    with pytest.raises(ValueError):
        create_app(config)


def test_startup_succeeds_when_both_models_have_a_price():
    """The default models are in the price table, so the app is built."""
    assert create_app(_config(), FakeLLM(None)) is not None


def test_require_accepts_a_priced_model():
    """The fake model has a price, so require does not raise."""
    Pricing(PRICES_FILE).require("fake")


def test_require_rejects_a_model_without_a_price():
    """A model outside the table is reported with ValueError."""
    with pytest.raises(ValueError):
        Pricing(PRICES_FILE).require("no-such-model")


def test_gateway_settings_are_read_from_the_environment():
    """GATEWAY_TIMEOUT_SECONDS and GATEWAY_BASE_URL reach the Config."""
    config = load_config(
        {
            **GATEWAY_ENV,
            "GATEWAY_TIMEOUT_SECONDS": "7.5",
            "GATEWAY_BASE_URL": "https://gateway.example.test/v9/",
        }
    )
    assert config.gateway_timeout_seconds == 7.5
    assert config.gateway_base_url == "https://gateway.example.test/v9"


def test_gateway_settings_have_defaults():
    """Without variables the gateway keeps a timeout and a base URL."""
    config = load_config(GATEWAY_ENV)
    assert config.gateway_timeout_seconds > 0
    assert config.gateway_base_url.startswith("https://")


def test_gateway_llm_uses_the_configured_url_and_timeout():
    """GatewayLLM posts to the configured base URL with the configured timeout."""
    seen = []

    def handler(request):
        seen.append(str(request.url))
        body = {
            "choices": [{"message": {"content": '{"answer": "ok"}'}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        return httpx.Response(200, json=body)

    config = load_config(
        {
            **GATEWAY_ENV,
            "GATEWAY_TIMEOUT_SECONDS": "7.5",
            "GATEWAY_BASE_URL": "https://gateway.example.test/v9",
        }
    )
    llm = GatewayLLM(config, transport=httpx.MockTransport(handler))
    llm.complete([{"role": "user", "content": "Hola"}])
    assert seen == [
        "https://gateway.example.test/v9/acc/gw/workers-ai/v1/chat/completions"
    ]
    # pylint: disable-next=protected-access
    assert llm._client.timeout.read == 7.5
