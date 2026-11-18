"""Pruebas unitarias de las palancas de costo.

Interfaces supuestas (el desarrollador debe seguirlas):

- ``app.router.choose_model(question, config) -> (model, route)``; ``route``
  es ``routing_off``, ``long_question``, ``keyword:<palabra>`` o ``default``.
- ``app.window.trim_history(history, window) -> list`` con los ultimos
  ``window`` mensajes.
- ``app.pricing.Pricing(path)`` con
  ``cost(model, input_tokens, output_tokens, cached=False) -> float`` y
  ``ValueError`` si el modelo no existe.
- ``app.llm.GatewayLLM(config, transport=None)`` con
  ``complete(messages, model) -> LLMResult`` (``text``, ``input_tokens``,
  ``output_tokens``, ``model``, ``cached``) y ``LLMUnavailable`` si falla.
- ``app.metrics.Metrics.record_cost(cost_usd)`` y ``cost_usd`` en el snapshot.
- ``Config`` con ``model_small``, ``model_large``, ``routing``,
  ``router_max_chars``, ``history_window``, ``model_max_tokens``,
  ``model_temperature``, ``cache_ttl_seconds`` y ``prices_path``.
"""

import json

import httpx
import pytest
from conftest import GATEWAY_ENV, PRICES_FILE

from app.config import load_config
from app.llm import GatewayLLM, LLMUnavailable
from app.metrics import Metrics
from app.pricing import Pricing
from app.router import choose_model
from app.window import trim_history

SMALL_MODEL = "@cf/meta/llama-3.1-8b-instruct-fast"
LARGE_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
GATEWAY_URL = (
    "https://gateway.ai.cloudflare.com/v1/acc/gw/workers-ai/v1/chat/completions"
)
MESSAGES = [{"role": "user", "content": "Hola"}]


def _gateway(handler, **env):
    """Crea un GatewayLLM con transporte simulado."""
    config = load_config({**GATEWAY_ENV, **env})
    return GatewayLLM(config, transport=httpx.MockTransport(handler))


def _ok_handler(captured, headers=None):
    """Handler que guarda la peticion y responde con ``usage``."""

    def handler(request):
        captured.append(request)
        body = {
            "choices": [{"message": {"content": '{"answer": "ok"}'}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7},
        }
        return httpx.Response(200, json=body, headers=headers or {})

    return handler


# Router


@pytest.mark.parametrize(
    "word", ["compara", "resume", "explica", "por qué", "analiza", "todos"]
)
def test_each_keyword_routes_to_the_large_model(word):
    """Cada palabra clave de la spec manda la pregunta al modelo capaz."""
    model, route = choose_model(f"Por favor {word} esto", load_config({}))
    assert model == LARGE_MODEL
    assert route.startswith("keyword:")


def test_keywords_ignore_case_and_accents():
    """«POR QUE» y «Por Qué» se tratan igual que «por qué»."""
    config = load_config({})
    for question in ("POR QUE sube?", "Por Qué sube?"):
        assert choose_model(question, config)[0] == LARGE_MODEL


def test_question_at_the_char_limit_stays_small_and_one_more_goes_large():
    """El limite es exacto: 80 caracteres es pequeno, 81 es capaz."""
    config = load_config({})
    assert choose_model("x" * 80, config) == (SMALL_MODEL, "default")
    assert choose_model("x" * 81, config) == (LARGE_MODEL, "long_question")


def test_routing_off_always_uses_the_large_model():
    """Con ROUTING=false incluso una pregunta corta va al modelo capaz."""
    config = load_config({"ROUTING": "false"})
    assert choose_model("Hola", config) == (LARGE_MODEL, "routing_off")


# Window


def test_history_is_trimmed_to_the_last_messages():
    """Solo quedan los ultimos mensajes, no los primeros ni todos."""
    history = [{"role": "user", "content": str(n)} for n in range(10)]
    trimmed = trim_history(history, 4)
    assert [m["content"] for m in trimmed] == ["6", "7", "8", "9"]


# Pricing


def test_cost_is_computed_per_million_tokens():
    """1M de entrada y 1M de salida suman ambos precios del archivo."""
    pricing = Pricing(PRICES_FILE)
    assert pricing.cost(SMALL_MODEL, 1_000_000, 1_000_000) == pytest.approx(0.429)


def test_cached_call_costs_nothing():
    """Una llamada con HIT vale 0 aunque tenga tokens."""
    assert Pricing(PRICES_FILE).cost(LARGE_MODEL, 5000, 500, cached=True) == 0


def test_unknown_model_price_raises_a_clear_error():
    """Un modelo fuera de la tabla falla con ValueError."""
    with pytest.raises(ValueError):
        Pricing(PRICES_FILE).cost("no-such-model", 1, 1)


# Gateway


def test_gateway_sends_url_headers_and_body_from_the_config():
    """La peticion usa la URL, el token, y el cuerpo que pide la spec."""
    captured = []
    llm = _gateway(
        _ok_handler(captured), MODEL_MAX_TOKENS="150", MODEL_TEMPERATURE="0"
    )
    llm.complete(MESSAGES, LARGE_MODEL)
    request = captured[0]
    assert str(request.url) == GATEWAY_URL
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert json.loads(request.content) == {
        "model": LARGE_MODEL,
        "messages": MESSAGES,
        "max_tokens": 150,
        "temperature": 0,
    }


def test_gateway_reads_tokens_and_cache_hit():
    """Los tokens salen de ``usage`` y el HIT marca la llamada cacheada."""
    captured = []
    handler = _ok_handler(captured, {"cf-aig-cache-status": "HIT"})
    result = _gateway(handler).complete(MESSAGES, SMALL_MODEL)
    assert (result.input_tokens, result.output_tokens) == (12, 7)
    assert result.cached is True
    assert result.model == SMALL_MODEL


def test_cache_ttl_header_is_sent_only_when_ttl_is_positive():
    """Con TTL 0 no hay encabezado; con TTL 60 se manda ``60``."""
    off, on = [], []
    _gateway(_ok_handler(off)).complete(MESSAGES, SMALL_MODEL)
    _gateway(_ok_handler(on), CACHE_TTL_SECONDS="60").complete(
        MESSAGES, SMALL_MODEL
    )
    assert "cf-aig-cache-ttl" not in off[0].headers
    assert on[0].headers["cf-aig-cache-ttl"] == "60"


def test_network_error_raises_llm_unavailable():
    """Un fallo de red se convierte en la excepcion propia."""

    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(LLMUnavailable):
        _gateway(handler).complete(MESSAGES, SMALL_MODEL)


def test_error_status_raises_llm_unavailable_without_leaking_the_token():
    """Un 500 del gateway lanza LLMUnavailable sin mostrar el token."""

    def handler(_request):
        return httpx.Response(500, text="upstream error")

    with pytest.raises(LLMUnavailable) as error:
        _gateway(handler).complete(MESSAGES, SMALL_MODEL)
    assert "secret-token" not in str(error.value)


# Config


def test_cost_settings_have_the_documented_defaults():
    """Los valores por omision coinciden con la tabla de la spec."""
    config = load_config({})
    assert config.model_small == SMALL_MODEL
    assert config.model_large == LARGE_MODEL
    assert config.routing is True
    assert config.router_max_chars == 80
    assert config.history_window == 6
    assert config.model_max_tokens == 300
    assert config.model_temperature == 0
    assert config.cache_ttl_seconds == 0


@pytest.mark.parametrize(
    "missing", ["CF_ACCOUNT_ID", "CF_GATEWAY_ID", "CF_API_TOKEN"]
)
def test_gateway_without_a_cloudflare_variable_cannot_start(missing):
    """Con ``gateway`` falta una variable CF_* y la carga falla."""
    env = {key: value for key, value in GATEWAY_ENV.items() if key != missing}
    with pytest.raises(ValueError):
        load_config(env)


# Metrics and API


def test_metrics_accumulate_the_cost():
    """Dos costos registrados se suman en el snapshot."""
    metrics = Metrics(2000)
    metrics.record_cost(0.25)
    metrics.record_cost(0.5)
    assert metrics.snapshot()["cost_usd"] == pytest.approx(0.75)


def test_only_the_history_window_reaches_the_model(
    employees_path, directory
):
    """El modelo recibe los ultimos mensajes del historial mas la pregunta."""
    from fastapi.testclient import TestClient  # pylint: disable=C0415
    from app.llm import FakeLLM  # pylint: disable=import-outside-toplevel
    from app.main import create_app  # pylint: disable=C0415

    seen = []

    class SpyLLM(FakeLLM):
        """Modelo simulado que guarda lo que recibe."""

        def complete(self, messages, model):
            seen.append(list(messages))
            return super().complete(messages, model)

    config = load_config(
        {
            "EMPLOYEES_PATH": str(employees_path),
            "PRICES_PATH": str(PRICES_FILE),
            "HISTORY_WINDOW": "2",
            "API_KEYS": "test:test-key-0123456789",
        }
    )
    client = TestClient(create_app(config, SpyLLM(directory), directory))
    client.headers["X-API-Key"] = "test-key-0123456789"
    history = [{"role": "user", "content": f"m{n}"} for n in range(6)]
    client.post("/ask", json={"question": "Hola", "history": history})
    contents = [m["content"] for m in seen[0]]
    assert contents == ["m4", "m5", "Hola"]
