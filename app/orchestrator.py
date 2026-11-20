"""Orquesta una petición: supervisor, especialista, salida segura y trazas."""

from dataclasses import dataclass

from app.agent import Agent, AgentResult
from app.output_guard import check_output
from app.pii import mask
from app.supervisor import choose_agent
from app.tracing import Tracer, request_metadata
from app.window import trim_history


@dataclass
class Reply:
    """Respuesta final de una petición, ya validada.

    :param agent: especialista que contestó.
    :param agent_route: motivo del supervisor.
    :param result: resultado del especialista, con la respuesta ya segura.
    :param pii_types: tipos de PII de pregunta, historial y respuesta.
    :param blocked: motivo del bloqueo de la salida, o ``None``.
    """

    agent: str
    agent_route: str
    result: AgentResult
    pii_types: list[str]
    blocked: str | None


class Orchestrator:  # pylint: disable=too-few-public-methods
    """Reparte cada pregunta a un especialista y deja la traza de la petición.

    :param config: configuración del servicio.
    :param agents: especialistas por nombre.
    :param policies: políticas de RH, para las reglas del supervisor.
    :param departments: departamentos conocidos, para las reglas del supervisor.
    :param tracer: tracer de LangSmith.
    :param logger: log JSON para la auditoría.
    :param secrets: valores secretos que la salida nunca debe contener.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        config,
        agents: dict[str, Agent],
        policies,
        departments: tuple[str, ...],
        tracer: Tracer,
        logger,
        secrets: tuple[str, ...] = (),
    ) -> None:
        self._config = config
        self._agents = agents
        self._policies = policies
        self._departments = departments
        self._tracer = tracer
        self._logger = logger
        self._secrets = secrets

    def run(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        question: str,
        history: list[dict],
        model: str,
        route: str,
        input_pii: list[str] | None = None,
    ) -> Reply:
        """Elige al especialista, lo corre, valida la salida y cierra la traza.

        Árbol: ``hr_request`` > ``supervisor`` > ``agent:<nombre>``.

        :param question: pregunta ya enmascarada.
        :param history: historial ya enmascarado.
        :param model: modelo elegido por el enrutador.
        :param route: motivo del enrutador de modelo.
        :param input_pii: tipos de PII hallados en la pregunta y el historial.
        :return: la respuesta validada.
        :raises LLMUnavailable: si el modelo falla; la traza queda con error.
        """
        config = self._config
        meta = request_metadata(config.environment)
        with self._tracer.span("hr_request", meta, [config.environment]) as root:
            with self._tracer.span("supervisor"):
                name, reason = choose_agent(question, self._policies, self._departments)
                root.add_tags(name)
                # Solo el tipo de regla: la palabra clave sale de la pregunta.
                root.add_metadata(
                    {
                        "agent": name,
                        "agent_route": reason.split(":")[0],
                        "model": model,
                        "route": route,
                    }
                )
                messages = trim_history(history, config.history_window)
                messages.append({"role": "user", "content": question})
                # Antes de correr al especialista, para que quede aunque falle.
                self._logger.emit(
                    "audit", action="agent_selected", agent=name, reason=reason
                )
                result = self._agents[name].run(messages, model)
            pii_types, blocked = self._secure(result, input_pii or [])
            root.add_metadata(
                {
                    "steps": result.steps,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "cost_usd": result.cost_usd,
                    "cached_calls": result.cached_calls,
                    "pii_types": pii_types,
                    "output_blocked": blocked is not None,
                    "stopped": result.stopped,
                }
            )
        return Reply(name, reason, result, pii_types, blocked)

    def _secure(
        self, result: AgentResult, input_pii: list[str]
    ) -> tuple[list[str], str | None]:
        """Valida y enmascara la respuesta del especialista, y la audita.

        :param result: resultado cuyo texto se reemplaza por el seguro.
        :param input_pii: tipos de PII ya hallados en la entrada.
        :return: los tipos de PII totales y el motivo del bloqueo, si hubo.
        """
        # Se enmascara antes de recortar, para no dejar un dato a medias.
        masked, found = mask(result.answer)
        text, blocked = check_output(
            masked, self._secrets, self._config.max_answer_chars
        )
        if found:
            self._logger.emit(
                "audit", action="pii_detected", where="answer", types=found
            )
        if blocked is not None:
            self._logger.emit("audit", action="output_blocked", reason=blocked)
        result.answer = text
        return sorted(set(input_pii) | set(found)), blocked
