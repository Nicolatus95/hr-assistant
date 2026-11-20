"""Trazas opcionales en LangSmith, con un árbol por petición."""

from collections.abc import Callable, Mapping
from contextlib import contextmanager
from functools import wraps

from langsmith import Client
from langsmith.run_helpers import trace, tracing_context

from app.config import Config
from app.context import client_var, request_id_var

DEFAULT_PROJECT = "hr-assistant-local"


class Span:
    """Tramo de una traza; si la traza está apagada no hace nada.

    :param run: ejecución de LangSmith, o ``None`` si está apagada.
    """

    def __init__(self, run=None) -> None:
        self._run = run

    def add_metadata(self, metadata: Mapping) -> None:
        """Agrega metadatos al tramo (nunca texto, PII ni claves).

        :param metadata: pares nombre y valor.
        """
        if self._run is not None:
            self._run.add_metadata(dict(metadata))

    def add_tags(self, *tags: str) -> None:
        """Agrega etiquetas al tramo.

        :param tags: etiquetas nuevas.
        """
        if self._run is not None:
            for tag in tags:
                if tag not in self._run.tags:
                    self._run.tags.append(tag)

    def set_outputs(self, outputs: Mapping) -> None:
        """Fija las salidas del tramo.

        :param outputs: salidas a enviar.
        """
        if self._run is not None:
            self._run.outputs = dict(outputs)


class Tracer:
    """Envuelve funciones y abre tramos para trazarlos; sin cliente no hace nada.

    :param client: cliente de LangSmith, o ``None`` si está apagado.
    :param hide_inputs: no enviar entradas.
    :param hide_outputs: no enviar salidas.
    :param project: proyecto de LangSmith, pasado de forma explícita.
    """

    def __init__(
        self,
        client=None,
        hide_inputs=True,
        hide_outputs=True,
        project=DEFAULT_PROJECT,
    ) -> None:
        self._client = client
        self._hide_inputs = hide_inputs
        self._hide_outputs = hide_outputs
        self._project = project

    def __repr__(self) -> str:
        return f"Tracer(enabled={self.enabled})"

    @property
    def enabled(self) -> bool:
        """Indica si las trazas están encendidas."""
        return self._client is not None

    @contextmanager
    def span(self, name: str, metadata=None, tags=None, inputs=None):
        """Abre un tramo hijo del tramo actual (o raíz si no hay).

        Si el bloque lanza una excepción, el tramo queda marcado con error.

        :param name: nombre del tramo.
        :param metadata: metadatos iniciales.
        :param tags: etiquetas iniciales.
        :param inputs: entradas; se ignoran con ``HIDE_INPUTS``.
        :yield: un :class:`Span`.
        """
        if not self.enabled:
            yield Span()
            return
        shown = None if self._hide_inputs else inputs
        with tracing_context(
            enabled=True, client=self._client, project_name=self._project
        ):
            with trace(
                name,
                "chain",
                inputs=shown,
                project_name=self._project,
                tags=list(tags or []),
                metadata=dict(metadata or {}),
                client=self._client,
            ) as run:
                yield Span(run)

    def wrap(self, func: Callable, name: str) -> Callable:
        """Devuelve ``func`` trazada, o ``func`` sin cambios si está apagado.

        :param func: función a trazar.
        :param name: nombre de la traza.
        :return: la función resultante.
        """
        if not self.enabled:
            return func

        @wraps(func)
        def traced(*args, **kwargs):
            call = {"args": list(args), "kwargs": kwargs}
            with self.span(name, inputs=call) as span:
                result = func(*args, **kwargs)
                if not self._hide_outputs:
                    span.set_outputs({"output": result})
                return result

        return traced


def build_tracer(config: Config, env: Mapping[str, str], client=None) -> Tracer:
    """Crea el tracer según la configuración y la clave del entorno.

    :param config: configuración del servicio.
    :param env: variables de entorno (de ahí sale la clave).
    :param client: cliente de LangSmith ya hecho (pruebas); opcional.
    :return: un tracer, apagado si falta la clave o el interruptor.
    """
    key = env.get("LANGSMITH_API_KEY")
    if not (config.langsmith_tracing and key):
        return Tracer()
    if client is None:
        client = Client(
            api_key=key,
            hide_inputs=(lambda _i: {}) if config.hide_inputs else None,
            hide_outputs=(lambda _o: {}) if config.hide_outputs else None,
        )
    return Tracer(
        client, config.hide_inputs, config.hide_outputs, config.langsmith_project
    )


def request_metadata(environment: str) -> dict:
    """Metadatos con que empieza la traza de una petición.

    :param environment: ambiente del servicio.
    :return: ``request_id``, ``client`` y ``environment``.
    """
    return {
        "request_id": request_id_var.get(),
        "client": client_var.get(),
        "environment": environment,
    }
