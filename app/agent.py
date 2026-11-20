"""Especialista con bucle acotado que usa solo las herramientas que le tocan."""

import inspect
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from app.directory import Directory
from app.llm import TOOL_PREFIX

CAP_MESSAGE = "No pude completar la respuesta. Intenta con una pregunta más concreta."
_DECODER = json.JSONDecoder()


@dataclass
class AgentResult:  # pylint: disable=too-many-instance-attributes
    """Resultado de una ejecución del agente.

    :param answer: texto final.
    :param steps: vueltas consumidas.
    :param tools_used: herramientas ejecutadas con éxito, en orden.
    :param input_tokens: tokens de entrada acumulados.
    :param output_tokens: tokens de salida acumulados.
    :param stopped: ``True`` solo si el tope de vueltas cortó la corrida.
    """

    answer: str
    steps: int = 0
    tools_used: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    stopped: bool = False
    cost_usd: float = 0.0
    cached_calls: int = 0


def _accepts_model(complete) -> bool:
    """Indica si ``complete`` admite el nombre del modelo como segundo argumento."""
    try:
        params = list(inspect.signature(complete).parameters.values())
    except (TypeError, ValueError):
        return False
    kinds = inspect.Parameter
    positional = (kinds.POSITIONAL_ONLY, kinds.POSITIONAL_OR_KEYWORD)
    count = sum(1 for p in params if p.kind in positional)
    return count >= 2 or any(p.kind is kinds.VAR_POSITIONAL for p in params)


def directory_tools(directory: Directory) -> dict[str, Callable]:
    """Herramientas del especialista ``directory``.

    :param directory: directorio de empleados.
    :return: diccionario de nombre a función que recibe los argumentos.
    """
    return {
        "get_employee": lambda a: directory.get_employee(a["employee_id"]),
        "search_by_department": lambda a: directory.search_by_department(
            a["department"]
        ),
    }


def policies_tools(policies) -> dict[str, Callable]:
    """Herramientas del especialista ``policies``.

    :param policies: políticas de RH.
    :return: diccionario de nombre a función que recibe los argumentos.
    """
    return {
        "get_policy": lambda a: policies.get_policy(a["topic"]),
        "list_policies": lambda _a: policies.list_policies(),
    }


def parse_reply(text: str) -> dict | None:
    """Toma el primer objeto JSON del texto, aunque venga en un bloque de código.

    :param text: respuesta del modelo.
    :return: el objeto, o ``None`` si el texto no tiene ninguno.
    """
    start = text.find("{")
    while start != -1:
        try:
            body, _end = _DECODER.raw_decode(text, start)
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        return body
    return None


class Agent:  # pylint: disable=too-many-instance-attributes
    """Especialista de un solo modelo con tope de vueltas.

    :param llm: modelo con método ``complete(messages)``; si además admite
        ``model``, se le indica el modelo elegido por el enrutador.
    :param directory: directorio de empleados; da las herramientas por omisión.
    :param max_steps: tope de vueltas del bucle.
    :param audit: función ``audit(tool, args)`` llamada por cada herramienta
        pedida, incluso si no es del especialista.
    :param tracer: objeto con ``wrap(func, name)`` para trazar; opcional.
    :param pricing: precios para calcular el costo; opcional.
    :param name: nombre del especialista.
    :param prompt: mensaje de sistema; se antepone a la conversación.
    :param tools: herramientas propias (nombre a función); si falta, las del
        directorio.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        llm,
        directory: Directory,
        max_steps: int,
        audit=None,
        tracer=None,
        pricing=None,
        name: str = "directory",
        prompt: str | None = None,
        tools: Mapping[str, Callable] | None = None,
    ) -> None:
        self.name = name
        self._llm = llm
        self._pricing = pricing
        self._with_model = _accepts_model(llm.complete)
        self._max_steps = max_steps
        self._audit = audit
        self._prompt = prompt
        wrap = tracer.wrap if tracer is not None else (lambda func, _name: func)
        self._complete = wrap(llm.complete, "llm_call")
        own = directory_tools(directory) if tools is None else dict(tools)
        self._tools = {
            key: wrap(func, f"tool:{key}") for key, func in own.items()
        }
        self._traced_run = wrap(self._run, f"agent:{name}")

    def run(self, messages: list[dict], model: str | None = None) -> AgentResult:
        """Ejecuta el bucle hasta obtener respuesta o llegar al tope.

        El mensaje de sistema se antepone aquí, después de que el llamador
        recortó el historial, así que la ventana nunca lo quita.

        :param messages: conversación, con la pregunta al final.
        :param model: modelo elegido por el enrutador; opcional.
        :return: el resultado del agente.
        """
        if self._prompt:
            messages = [{"role": "system", "content": self._prompt}, *messages]
        return self._traced_run(messages, model)

    def _run(self, messages: list[dict], model: str | None = None) -> AgentResult:
        """Bucle del agente, sin trazas propias."""
        result = AgentResult(answer=CAP_MESSAGE)
        conversation = list(messages)
        for _ in range(self._max_steps):
            if self._with_model and model is not None:
                reply = self._complete(conversation, model)
            else:
                reply = self._complete(conversation)
            result.steps += 1
            result.input_tokens += reply.input_tokens
            result.output_tokens += reply.output_tokens
            self._add_cost(result, reply, model)
            outcome = self._execute(reply.text, result)
            if outcome["final"]:
                result.answer = outcome["text"]
                return result
            conversation.append(
                {"role": "user", "content": TOOL_PREFIX + outcome["text"]}
            )
        result.stopped = True
        return result

    def _add_cost(self, result: AgentResult, reply, model: str | None) -> None:
        """Suma el costo y las llamadas cacheadas de una respuesta del modelo."""
        cached = bool(getattr(reply, "cached", False))
        result.cached_calls += 1 if cached else 0
        if self._pricing is None:
            return
        name = getattr(reply, "model", "") or model or "fake"
        result.cost_usd += self._pricing.cost(
            name, reply.input_tokens, reply.output_tokens, cached
        )

    def _execute(self, text: str, result: AgentResult) -> dict:
        """Interpreta la respuesta del modelo y ejecuta la herramienta pedida."""
        body = parse_reply(text)
        if body is None:
            return {"final": True, "text": text}
        if "answer" in body:
            return {"final": True, "text": str(body["answer"])}
        name = body.get("tool")
        args = body.get("args") or {}
        if self._audit is not None:
            self._audit(name, args)
        tool = self._tools.get(name) if isinstance(name, str) else None
        if tool is None:
            return {"final": False, "text": f"error: unknown tool {name!r}"}
        try:
            output = tool(args)
        except (KeyError, TypeError, AttributeError):
            return {"final": False, "text": f"error: bad arguments for {name}"}
        result.tools_used.append(name)
        return {"final": False, "text": json.dumps(output, ensure_ascii=False)}
