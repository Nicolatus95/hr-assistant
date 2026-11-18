"""Agente con bucle acotado que usa herramientas del directorio."""

import inspect
import json
from dataclasses import dataclass, field

from app.directory import Directory
from app.llm import TOOL_PREFIX

CAP_MESSAGE = "No pude completar la respuesta. Intenta con una pregunta más concreta."


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


class Agent:  # pylint: disable=too-many-instance-attributes
    """Agente de un solo modelo con tope de vueltas.

    :param llm: modelo con método ``complete(messages)``; si además admite
        ``model``, se le indica el modelo elegido por el enrutador.
    :param directory: directorio de empleados.
    :param max_steps: tope de vueltas del bucle.
    :param audit: función ``audit(tool, args)`` llamada por cada herramienta.
    :param tracer: objeto con ``wrap(func, name)`` para trazar; opcional.
    :param pricing: precios para calcular el costo; opcional.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        llm,
        directory: Directory,
        max_steps: int,
        audit=None,
        tracer=None,
        pricing=None,
    ) -> None:
        self._llm = llm
        self._pricing = pricing
        self._with_model = _accepts_model(llm.complete)
        self._directory = directory
        self._max_steps = max_steps
        self._audit = audit
        wrap = tracer.wrap if tracer is not None else (lambda func, _name: func)
        self._complete = wrap(llm.complete, "llm_call")
        self._tools = {
            "get_employee": wrap(
                lambda a: self._directory.get_employee(a["employee_id"]),
                "tool:get_employee",
            ),
            "search_by_department": wrap(
                lambda a: self._directory.search_by_department(a["department"]),
                "tool:search_by_department",
            ),
        }
        self._traced_run = wrap(self._run, "agent_run")

    def run(self, messages: list[dict], model: str | None = None) -> AgentResult:
        """Ejecuta el bucle hasta obtener respuesta o llegar al tope.

        :param messages: conversación, con la pregunta al final.
        :param model: modelo elegido por el enrutador; opcional.
        :return: el resultado del agente.
        """
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
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            return {"final": False, "text": "error: invalid JSON from the model"}
        if not isinstance(body, dict):
            return {"final": False, "text": "error: invalid JSON from the model"}
        if "answer" in body:
            return {"final": True, "text": str(body["answer"])}
        name = body.get("tool")
        tool = self._tools.get(name)
        if tool is None:
            return {"final": False, "text": f"error: unknown tool {name!r}"}
        args = body.get("args") or {}
        if self._audit is not None:
            self._audit(name, args)
        try:
            output = tool(args)
        except (KeyError, TypeError):
            return {"final": False, "text": f"error: bad arguments for {name}"}
        result.tools_used.append(name)
        return {"final": False, "text": json.dumps(output, ensure_ascii=False)}
