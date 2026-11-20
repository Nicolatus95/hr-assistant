"""Configuración del servicio leída desde variables de entorno."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from app.auth import parse_api_keys
from app.compliance import enforce

SUPPORTED_PROVIDERS = ("fake", "gateway")
CF_REQUIRED = ("CF_ACCOUNT_ID", "CF_GATEWAY_ID", "CF_API_TOKEN")


@dataclass(frozen=True)
class Config:  # pylint: disable=too-many-instance-attributes
    """Configuración inmutable del servicio.

    :param model_provider: nombre del modelo a usar.
    :param agent_max_steps: tope de vueltas del bucle del agente.
    :param max_question_chars: largo máximo de la pregunta.
    :param employees_path: ruta del archivo de empleados.
    :param policies_path: ruta del archivo de políticas de RH.
    :param max_history_items: mensajes de historial permitidos por petición.
    :param max_answer_chars: largo máximo de la respuesta.
    :param langsmith_project: proyecto de LangSmith donde van las trazas.
    """

    model_provider: str = "fake"
    agent_max_steps: int = 3
    max_question_chars: int = 2000
    employees_path: Path = Path("data/employees.json")
    service_name: str = "hr-assistant"
    slo_p95_ms: int = 2000
    langsmith_tracing: bool = False
    hide_inputs: bool = True
    hide_outputs: bool = True
    cf_account_id: str = ""
    cf_gateway_id: str = "default"
    cf_api_token: str = field(default="", repr=False)
    model_small: str = "@cf/meta/llama-3.1-8b-instruct-fast"
    model_large: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    routing: bool = True
    router_max_chars: int = 80
    history_window: int = 6
    model_max_tokens: int = 300
    model_temperature: float = 0.0
    cache_ttl_seconds: int = 0
    prices_path: Path = Path("data/model_prices.json")
    gateway_base_url: str = "https://gateway.ai.cloudflare.com/v1"
    gateway_timeout_seconds: float = 30.0
    environment: str = "development"
    api_keys: dict = field(default_factory=dict, repr=False)
    rate_limit_per_minute: int = 30
    cf_aig_token: str = field(default="", repr=False)
    policies_path: Path = Path("data/policies.json")
    max_history_items: int = 20
    max_answer_chars: int = 1500
    langsmith_project: str = "hr-assistant-local"


def _boolean(env: Mapping[str, str], name: str, default: bool) -> bool:
    """Lee un booleano (``true`` o ``false``) de ``env``.

    :raises ValueError: si el valor no es ``true`` ni ``false``.
    """
    raw = env.get(name)
    if raw is None:
        return default
    if raw.lower() not in ("true", "false"):
        raise ValueError(f"{name} must be true or false, got {raw!r}")
    return raw.lower() == "true"


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    """Lee un entero positivo de ``env``.

    :param env: variables de entorno.
    :param name: nombre de la variable.
    :param default: valor por omisión.
    :return: el entero validado.
    :raises ValueError: si no es un entero mayor que cero.
    """
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None
    if value < 1:
        raise ValueError(f"{name} must be greater than 0, got {value}")
    return value


def _non_negative_number(
    env: Mapping[str, str], name: str, default: float, kind=int
) -> float:
    """Lee un número mayor o igual que cero de ``env``.

    :param env: variables de entorno.
    :param name: nombre de la variable.
    :param default: valor por omisión.
    :param kind: tipo numérico, ``int`` o ``float``.
    :return: el número validado.
    :raises ValueError: si no es un número válido o es negativo.
    """
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = kind(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number, got {raw!r}") from None
    if value < 0:
        raise ValueError(f"{name} must not be negative, got {value}")
    return value


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Construye la configuración validada.

    :param env: variables de entorno; si es ``None`` usa ``os.environ``.
    :return: la configuración.
    :raises ValueError: si algún valor es inválido.
    """
    env = os.environ if env is None else env
    provider = env.get("MODEL_PROVIDER", "fake")
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"MODEL_PROVIDER must be one of {SUPPORTED_PROVIDERS}")
    if provider == "gateway":
        missing = [name for name in CF_REQUIRED if not env.get(name)]
        if missing:
            raise ValueError(f"MODEL_PROVIDER=gateway requires {missing}")
    defaults = Config()
    config = Config(
        environment=env.get("ENVIRONMENT") or defaults.environment,
        api_keys=parse_api_keys(env.get("API_KEYS", "")),
        rate_limit_per_minute=_positive_int(
            env, "RATE_LIMIT_PER_MINUTE", defaults.rate_limit_per_minute
        ),
        cf_aig_token=env.get("CF_AIG_TOKEN", ""),
        model_provider=provider,
        cf_account_id=env.get("CF_ACCOUNT_ID", ""),
        cf_gateway_id=env.get("CF_GATEWAY_ID") or defaults.cf_gateway_id,
        cf_api_token=env.get("CF_API_TOKEN", ""),
        model_small=env.get("MODEL_SMALL") or defaults.model_small,
        model_large=env.get("MODEL_LARGE") or defaults.model_large,
        routing=_boolean(env, "ROUTING", defaults.routing),
        router_max_chars=_positive_int(
            env, "ROUTER_MAX_CHARS", defaults.router_max_chars
        ),
        history_window=_positive_int(env, "HISTORY_WINDOW", defaults.history_window),
        model_max_tokens=_positive_int(
            env, "MODEL_MAX_TOKENS", defaults.model_max_tokens
        ),
        model_temperature=_non_negative_number(
            env, "MODEL_TEMPERATURE", defaults.model_temperature, float
        ),
        cache_ttl_seconds=_non_negative_number(
            env, "CACHE_TTL_SECONDS", defaults.cache_ttl_seconds
        ),
        prices_path=Path(env.get("PRICES_PATH") or defaults.prices_path),
        gateway_base_url=(
            env.get("GATEWAY_BASE_URL") or defaults.gateway_base_url
        ).rstrip("/"),
        gateway_timeout_seconds=_non_negative_number(
            env,
            "GATEWAY_TIMEOUT_SECONDS",
            defaults.gateway_timeout_seconds,
            float,
        )
        or defaults.gateway_timeout_seconds,
        agent_max_steps=_positive_int(env, "AGENT_MAX_STEPS", defaults.agent_max_steps),
        max_question_chars=_positive_int(
            env, "MAX_QUESTION_CHARS", defaults.max_question_chars
        ),
        employees_path=Path(env.get("EMPLOYEES_PATH") or defaults.employees_path),
        service_name=env.get("SERVICE_NAME") or defaults.service_name,
        slo_p95_ms=_positive_int(env, "SLO_P95_MS", defaults.slo_p95_ms),
        langsmith_tracing=_boolean(
            env, "LANGSMITH_TRACING", defaults.langsmith_tracing
        ),
        hide_inputs=_boolean(env, "HIDE_INPUTS", defaults.hide_inputs),
        hide_outputs=_boolean(env, "HIDE_OUTPUTS", defaults.hide_outputs),
        policies_path=Path(env.get("POLICIES_PATH") or defaults.policies_path),
        max_history_items=_positive_int(
            env, "MAX_HISTORY_ITEMS", defaults.max_history_items
        ),
        max_answer_chars=_positive_int(
            env, "MAX_ANSWER_CHARS", defaults.max_answer_chars
        ),
        langsmith_project=env.get("LANGSMITH_PROJECT") or defaults.langsmith_project,
    )
    enforce(config)
    return config
