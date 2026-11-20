"""Modelos de la API y construcción de la respuesta y del evento de ``/ask``."""

from typing import Literal

from pydantic import BaseModel


class HistoryItem(BaseModel):
    """Mensaje previo enviado por el cliente."""

    role: Literal["user", "assistant"]
    content: str


class AskRequest(BaseModel):
    """Cuerpo de ``POST /ask``."""

    question: str
    history: list[HistoryItem] = []


class AskResponse(BaseModel):
    """Respuesta de ``POST /ask``."""

    answer: str
    steps: int
    tools_used: list[str]
    input_tokens: int
    output_tokens: int
    request_id: str
    model: str
    route: str
    cached_calls: int
    cost_usd: float
    agent: str
    agent_route: str
    pii_types: list[str]
    output_blocked: bool


def build_response(reply, model: str, route: str, request_id: str) -> AskResponse:
    """Arma la respuesta pública a partir de la respuesta del orquestador.

    :param reply: respuesta del orquestador.
    :param model: modelo elegido por el enrutador.
    :param route: ruta elegida por el enrutador.
    :param request_id: id de la petición.
    :return: la respuesta de ``POST /ask``.
    """
    result = reply.result
    return AskResponse(
        agent=reply.agent,
        agent_route=reply.agent_route,
        model=model,
        route=route,
        cached_calls=result.cached_calls,
        cost_usd=result.cost_usd,
        request_id=request_id,
        answer=result.answer,
        steps=result.steps,
        tools_used=result.tools_used,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        pii_types=reply.pii_types,
        output_blocked=reply.blocked is not None,
    )


def agent_run_fields(
    reply, model: str, route: str, question_chars: int, history_messages: int
) -> dict:
    """Arma los campos del evento ``agent_run`` (sin texto ni PII).

    :param reply: respuesta del orquestador.
    :param model: modelo elegido por el enrutador.
    :param route: ruta elegida por el enrutador.
    :param question_chars: largo de la pregunta, nunca su texto.
    :param history_messages: cantidad de mensajes del historial.
    :return: los campos para ``logger.emit("agent_run", **fields)``.
    """
    result = reply.result
    return {
        "question_chars": question_chars,
        "history_messages": history_messages,
        "steps": result.steps,
        "tools": result.tools_used,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "stopped": result.stopped,
        "model": model,
        "route": route,
        "agent": reply.agent,
        "agent_route": reply.agent_route,
        "cached_calls": result.cached_calls,
        "cost_usd": result.cost_usd,
        "prefetched": result.prefetched,
    }
