"""Trazas opcionales en LangSmith."""

from collections.abc import Callable, Mapping
from functools import wraps

from langsmith import Client, traceable

from app.config import Config
from app.context import client_var, request_id_var


class Tracer:
    """Envuelve funciones para trazarlas; sin clave no hace nada.

    :param client: cliente de LangSmith, o ``None`` si está apagado.
    :param hide_inputs: no enviar entradas.
    :param hide_outputs: no enviar salidas.
    """

    def __init__(self, client=None, hide_inputs=True, hide_outputs=True) -> None:
        self._client = client
        self._hide_inputs = hide_inputs
        self._hide_outputs = hide_outputs

    def __repr__(self) -> str:
        return f"Tracer(enabled={self.enabled})"

    @property
    def enabled(self) -> bool:
        """Indica si las trazas están encendidas."""
        return self._client is not None

    def wrap(self, func: Callable, name: str) -> Callable:
        """Devuelve ``func`` trazada, o ``func`` sin cambios si está apagado.

        :param func: función a trazar.
        :param name: nombre de la traza.
        :return: la función resultante.
        """
        if not self.enabled:
            return func
        hide_in, hide_out = self._hide_inputs, self._hide_outputs

        @wraps(func)
        def traced(*args, **kwargs):
            decorator = traceable(
                name=name,
                client=self._client,
                metadata={
                    "request_id": request_id_var.get(),
                    "client": client_var.get(),
                },
                process_inputs=(lambda _inputs: {}) if hide_in else None,
                process_outputs=(lambda _outputs: {}) if hide_out else None,
            )
            return decorator(func)(*args, **kwargs)

        return traced


def build_tracer(config: Config, env: Mapping[str, str]) -> Tracer:
    """Crea el tracer según la configuración y la clave del entorno.

    :param config: configuración del servicio.
    :param env: variables de entorno (de ahí sale la clave).
    :return: un tracer, apagado si falta la clave o el interruptor.
    """
    key = env.get("LANGSMITH_API_KEY")
    if not (config.langsmith_tracing and key):
        return Tracer()
    client = Client(
        api_key=key,
        hide_inputs=(lambda _i: {}) if config.hide_inputs else None,
        hide_outputs=(lambda _o: {}) if config.hide_outputs else None,
    )
    return Tracer(client, config.hide_inputs, config.hide_outputs)
