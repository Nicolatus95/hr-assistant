"""Límite de peticiones por cliente en memoria."""

import math
import threading

WINDOW_SECONDS = 60


class RateLimiter:
    """Ventana fija de un minuto por cliente.

    :param limit: peticiones permitidas por ventana.
    :param clock: objeto con método ``now()`` que devuelve un datetime.
    """

    def __init__(self, limit: int, clock) -> None:
        self._limit = limit
        self._clock = clock
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def check(self, client: str) -> int:
        """Cuenta una petición del cliente.

        :param client: nombre del cliente.
        :return: ``0`` si pasa; si no, los segundos que faltan para la ventana
            siguiente.
        """
        now = self._clock.now().timestamp()
        with self._lock:
            start, count = self._windows.get(client, (now, 0))
            if now - start >= WINDOW_SECONDS:
                start, count = now, 0
            if count >= self._limit:
                return max(1, math.ceil(start + WINDOW_SECONDS - now))
            self._windows[client] = (start, count + 1)
            return 0
