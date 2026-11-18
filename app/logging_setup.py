"""Log en JSON, una línea por evento."""

import json
import sys

from app.context import client_var, request_id_var


class JsonLogger:
    """Escribe eventos como líneas JSON.

    :param service: nombre del servicio para el campo ``service``.
    :param clock: objeto con método ``now()``.
    :param stream: destino; si es ``None`` se usa ``sys.stdout`` al escribir.
    """

    def __init__(self, service: str, clock, stream=None) -> None:
        self._service = service
        self._clock = clock
        self._stream = stream

    def emit(self, event: str, **fields) -> None:
        """Escribe un evento.

        :param event: nombre del evento.
        :param fields: campos adicionales del evento.
        """
        line = {
            "ts": self._clock.now().isoformat(),
            "service": self._service,
            "event": event,
            "request_id": request_id_var.get(),
            **fields,
        }
        client = client_var.get()
        if client and "client" not in line:
            line["client"] = client
        stream = self._stream if self._stream is not None else sys.stdout
        stream.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
        stream.flush()
