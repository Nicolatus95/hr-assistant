"""Interfaz del modelo y modelo simulado determinista."""

import json
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Config
from app.directory import Directory
from app.policies import Policies
from app.text import normalize

TOOL_PREFIX = "Resultado de la herramienta: "
HELP_MESSAGE = "Pregúntame por un empleado (EMP-0001) o un departamento."
_EMPLOYEE_ID = re.compile(r"EMP-\d{4}")


@dataclass(frozen=True)
class LLMResult:
    """Respuesta del modelo.

    :param text: objeto JSON como texto.
    :param input_tokens: tokens de entrada aproximados.
    :param output_tokens: tokens de salida aproximados.
    """

    text: str
    input_tokens: int
    output_tokens: int
    model: str = ""
    cached: bool = False


class LLMUnavailable(Exception):
    """El modelo real no respondió o respondió con error."""


class LLM(Protocol):
    """Interfaz que debe cumplir cualquier modelo."""

    def complete(self, messages: list[dict], model: str | None = None) -> LLMResult:
        """Responde a la conversación.

        :param messages: lista de mensajes ``{"role", "content"}``.
        :param model: nombre del modelo que debe responder; opcional.
        :return: el resultado con texto JSON y conteo de tokens.
        """


class FakeLLM:
    """Modelo simulado sin red, decide con reglas sobre el último mensaje.

    :param directory: directorio, para conocer los departamentos.
    :param policies: políticas, para conocer sus palabras clave; opcional.
    """

    def __init__(self, directory: Directory, policies: Policies | None = None) -> None:
        self._directory = directory
        self._policies = policies

    def _respond(self, messages: list[dict], model: str | None = None) -> LLMResult:
        """Aplica las reglas del modelo simulado.

        :param messages: lista de mensajes de la conversación.
        :param model: nombre con el que se calcula el precio; ``fake`` si falta.
        :return: el resultado con texto JSON y conteo de tokens.
        """
        last = messages[-1]["content"] if messages else ""
        body = self._decide(last)
        text = json.dumps(body, ensure_ascii=False)
        input_tokens = sum(len(m["content"].split()) for m in messages)
        output_tokens = len(body["answer"].split()) if "answer" in body else 0
        return LLMResult(text, input_tokens, output_tokens, model or "fake")

    # Se expone como atributo para que las subclases de prueba, que exigen
    # ``model``, no choquen con el valor por omisión de la firma.
    complete = _respond

    def _decide(self, last: str) -> dict:
        """Elige entre responder o pedir una herramienta."""
        if last.startswith(TOOL_PREFIX):
            return {"answer": f"Según el directorio: {last[len(TOOL_PREFIX):]}"}
        found = _EMPLOYEE_ID.search(last)
        if found:
            return {"tool": "get_employee", "args": {"employee_id": found.group()}}
        normalized = normalize(last)
        for department in self._directory.departments:
            if normalize(department) in normalized:
                args = {"department": department}
                return {"tool": "search_by_department", "args": args}
        keyword = self._policies.find_keyword(last) if self._policies else None
        if keyword:
            return {"tool": "get_policy", "args": {"topic": keyword}}
        return {"answer": HELP_MESSAGE}


class GatewayLLM:
    """Modelo real de Workers AI a través de AI Gateway.

    :param config: configuración con cuenta, gateway, token y palancas.
    :param transport: transporte de httpx; en pruebas es simulado.
    """

    def __init__(self, config: Config, transport=None) -> None:
        self._config = config
        self._url = (
            f"{config.gateway_base_url}/{config.cf_account_id}"
            f"/{config.cf_gateway_id}/workers-ai/v1/chat/completions"
        )
        self._client = httpx.Client(
            transport=transport, timeout=config.gateway_timeout_seconds
        )

    def complete(self, messages: list[dict], model: str | None = None) -> LLMResult:
        """Llama al gateway y lee texto, tokens y estado de la caché.

        :param messages: lista de mensajes de la conversación.
        :param model: modelo a usar; por omisión ``MODEL_LARGE``.
        :return: el resultado de la llamada.
        :raises LLMUnavailable: si la red falla o la respuesta no es válida.
        """
        config = self._config
        model = model or config.model_large
        headers = {"Authorization": f"Bearer {config.cf_api_token}"}
        if config.cf_aig_token:
            headers["cf-aig-authorization"] = f"Bearer {config.cf_aig_token}"
        if config.cache_ttl_seconds > 0:
            headers["cf-aig-cache-ttl"] = str(config.cache_ttl_seconds)
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": config.model_max_tokens,
            "temperature": config.model_temperature,
        }
        try:
            response = self._client.post(self._url, json=body, headers=headers)
        except httpx.HTTPError as error:
            raise LLMUnavailable(type(error).__name__) from None
        if response.status_code >= 400:
            raise LLMUnavailable(f"gateway status {response.status_code}")
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            usage = data["usage"]
            tokens = (int(usage["prompt_tokens"]), int(usage["completion_tokens"]))
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMUnavailable("invalid gateway response") from None
        cached = response.headers.get("cf-aig-cache-status", "").upper() == "HIT"
        return LLMResult(text, tokens[0], tokens[1], model, cached)


def build_llm(
    config: Config, directory: Directory, policies: Policies | None = None
) -> LLM:
    """Crea el modelo según la configuración.

    :param config: configuración del servicio.
    :param directory: directorio de empleados.
    :param policies: políticas de RH; opcional.
    :return: el modelo elegido.
    :raises ValueError: si el proveedor no existe.
    """
    if config.model_provider == "fake":
        return FakeLLM(directory, policies)
    if config.model_provider == "gateway":
        return GatewayLLM(config)
    raise ValueError(f"Unknown model provider: {config.model_provider}")
