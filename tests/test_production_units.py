"""Unit tests for auth, rate limit, compliance, config and the gateway token.

Assumed interfaces (the developer must follow them):

- ``app.auth.parse_api_keys(raw) -> dict`` mapping client name to key; it
  raises ``ValueError`` for a malformed value.
- ``app.ratelimit.RateLimiter(limit, clock)`` with ``check(client) -> int``:
  ``0`` when the request is allowed, otherwise the seconds left in the window.
- ``app.compliance`` rules run inside ``load_config`` and raise ``ValueError``.
- ``Config`` has ``environment``, ``api_keys`` (hidden in repr),
  ``rate_limit_per_minute`` and ``cf_aig_token`` (hidden in repr).
- ``GatewayLLM`` sends ``cf-aig-authorization`` only when ``cf_aig_token``
  has a value.
- ``scripts/smoke.py`` exposes ``main(argv, env, transport=None) -> int``
  (0 when every check passes) and reads the key only from ``SMOKE_API_KEY``.
"""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from app.auth import parse_api_keys
from app.config import load_config
from app.llm import GatewayLLM, LLMUnavailable
from app.ratelimit import RateLimiter

SMOKE_FILE = Path(__file__).resolve().parents[1] / "scripts" / "smoke.py"
LONG_KEY = "k" * 20
API_TOKEN = "api-token-secret-value"
AIG_TOKEN = "aig-token-secret-value"
PRODUCTION = {
    "ENVIRONMENT": "production",
    "MODEL_PROVIDER": "gateway",
    "CF_ACCOUNT_ID": "acc",
    "CF_GATEWAY_ID": "gw",
    "CF_API_TOKEN": API_TOKEN,
    "CF_AIG_TOKEN": AIG_TOKEN,
    "API_KEYS": f"ana:{LONG_KEY}",
}


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


# auth.py


def test_valid_entries_are_parsed_by_client():
    keys = parse_api_keys("ana:key-one-0123456789,bob:key-two-0123456789")
    assert keys == {"ana": "key-one-0123456789", "bob": "key-two-0123456789"}


def test_malformed_entry_error_shows_its_length_but_not_its_value():
    secret_entry = "no-separator-secret"
    with pytest.raises(ValueError) as error:
        parse_api_keys(f"ana:{LONG_KEY},{secret_entry}")
    assert str(len(secret_entry)) in str(error.value)
    assert secret_entry not in str(error.value)


def test_duplicate_client_is_rejected():
    with pytest.raises(ValueError, match="ana"):
        parse_api_keys(f"ana:{LONG_KEY},ana:{'z' * 20}")


# ratelimit.py


def test_requests_over_the_limit_report_the_seconds_left():
    clock = FakeClock()
    limiter = RateLimiter(2, clock)
    assert limiter.check("ana") == 0
    assert limiter.check("ana") == 0
    clock.advance(20)
    assert limiter.check("ana") == 40


def test_window_resets_after_a_minute():
    clock = FakeClock()
    limiter = RateLimiter(1, clock)
    limiter.check("ana")
    assert limiter.check("ana") > 0
    clock.advance(61)
    assert limiter.check("ana") == 0


def test_clients_have_independent_quotas():
    limiter = RateLimiter(1, FakeClock())
    limiter.check("ana")
    assert limiter.check("ana") > 0
    assert limiter.check("bob") == 0


# compliance (applied by load_config)


def test_production_refuses_the_fake_model():
    with pytest.raises(ValueError, match="MODEL_PROVIDER"):
        load_config({**PRODUCTION, "MODEL_PROVIDER": "fake"})


def test_production_refuses_a_short_key_without_printing_it():
    short_key = "abc123XYZ"
    with pytest.raises(ValueError, match="API_KEYS") as error:
        load_config({**PRODUCTION, "API_KEYS": f"ana:{short_key}"})
    assert short_key not in str(error.value)


def test_production_refuses_visible_trace_inputs():
    env = {**PRODUCTION, "LANGSMITH_TRACING": "true", "HIDE_INPUTS": "false"}
    with pytest.raises(ValueError, match="HIDE_"):
        load_config(env)


def test_production_gateway_needs_the_aig_token_and_names_only_the_rule():
    env = {**PRODUCTION, "CF_AIG_TOKEN": ""}
    with pytest.raises(ValueError, match="CF_AIG_TOKEN") as error:
        load_config(env)
    assert API_TOKEN not in str(error.value)


def test_safe_configurations_start():
    production = load_config({**PRODUCTION, "LANGSMITH_TRACING": "true"})
    assert production.environment == "production"
    development = load_config({"MODEL_PROVIDER": "fake", "API_KEYS": ""})
    assert development.environment == "development"


# config.py


def test_new_settings_have_defaults_and_tokens_stay_out_of_repr():
    defaults = load_config({})
    assert defaults.rate_limit_per_minute == 30
    assert defaults.cf_aig_token == ""
    shown = repr(load_config({**PRODUCTION, "RATE_LIMIT_PER_MINUTE": "5"}))
    for secret in (LONG_KEY, API_TOKEN, AIG_TOKEN):
        assert secret not in shown


# llm.py


def gateway(handler, **extra):
    """Build a GatewayLLM over a mock transport."""
    env = {
        "MODEL_PROVIDER": "gateway",
        "CF_ACCOUNT_ID": "acc",
        "CF_GATEWAY_ID": "gw",
        "CF_API_TOKEN": API_TOKEN,
        **extra,
    }
    return GatewayLLM(load_config(env), transport=httpx.MockTransport(handler))


def ok_reply(request):
    """Gateway reply that is valid for any request."""
    assert request is not None
    body = {
        "choices": [{"message": {"content": "{}"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    return httpx.Response(200, json=body)


def test_gateway_sends_both_authorization_headers_with_an_aig_token():
    seen = []

    def handler(request):
        seen.append(request.headers)
        return ok_reply(request)

    gateway(handler, CF_AIG_TOKEN=AIG_TOKEN).complete([])
    assert seen[0]["Authorization"] == f"Bearer {API_TOKEN}"
    assert seen[0]["cf-aig-authorization"] == f"Bearer {AIG_TOKEN}"


def test_gateway_omits_the_aig_header_without_a_token():
    seen = []

    def handler(request):
        seen.append(request.headers)
        return ok_reply(request)

    gateway(handler).complete([])
    assert "cf-aig-authorization" not in seen[0]


def test_gateway_failures_do_not_leak_tokens():
    def rejected(_request):
        return httpx.Response(401, text=f"bad {API_TOKEN} {AIG_TOKEN}")

    def unreachable(request):
        raise httpx.ConnectError(f"down {API_TOKEN} {AIG_TOKEN}", request=request)

    for handler in (rejected, unreachable):
        with pytest.raises(LLMUnavailable) as error:
            gateway(handler, CF_AIG_TOKEN=AIG_TOKEN).complete([])
        assert API_TOKEN not in str(error.value)
        assert AIG_TOKEN not in str(error.value)


# scripts/smoke.py


def load_smoke():
    """Import scripts/smoke.py by path."""
    spec = importlib.util.spec_from_file_location("smoke", SMOKE_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def smoke_server(enforce_key):
    """Mock server; with ``enforce_key`` it answers 401 to /ask without key."""

    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if enforce_key and request.headers.get("X-API-Key") != "smoke-key":
            return httpx.Response(401, json={"detail": "invalid or missing API key"})
        return httpx.Response(200, json={"answer": "hi"})

    return httpx.MockTransport(handler)


def test_smoke_prints_ok_for_each_check_on_a_healthy_service(capsys):
    code = load_smoke().main(
        ["http://svc"], {"SMOKE_API_KEY": "smoke-key"}, smoke_server(True)
    )
    output = capsys.readouterr().out
    assert code == 0
    assert output.count("[OK]") == 3
    assert "[FAIL]" not in output
    assert "smoke-key" not in output


def test_smoke_fails_when_the_service_does_not_enforce_the_key(capsys):
    code = load_smoke().main(
        ["http://svc"], {"SMOKE_API_KEY": "smoke-key"}, smoke_server(False)
    )
    assert code != 0
    assert "[FAIL]" in capsys.readouterr().out


def test_smoke_needs_the_key_in_the_environment_variable(capsys):
    code = load_smoke().main(["http://svc", "smoke-key"], {}, smoke_server(True))
    assert code != 0
    assert "SMOKE_API_KEY" in capsys.readouterr().out
