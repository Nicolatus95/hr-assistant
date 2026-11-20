"""Métricas en memoria de este proceso."""

import math
import os
import threading


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """Percentil por rango más cercano; 0 si no hay datos."""
    if not sorted_values:
        return 0
    rank = max(1, math.ceil(fraction * len(sorted_values)))
    return sorted_values[rank - 1]


class Metrics:  # pylint: disable=too-many-instance-attributes
    """Acumula peticiones, latencias y tokens.

    :param slo_p95_ms: meta de latencia p95 en milisegundos.
    """

    def __init__(
        self, slo_p95_ms: int, agents: tuple[str, ...] = ("directory", "policies")
    ) -> None:
        self._target = slo_p95_ms
        self._by_agent = {name: 0 for name in agents}
        self._cost_by_agent = {name: 0.0 for name in agents}
        self._pii_detections = 0
        self._outputs_blocked = 0
        self._lock = threading.Lock()
        self._latencies: list[float] = []
        self._failures = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost_usd = 0.0

    def record_cost(self, cost_usd: float) -> None:
        """Suma el costo de una respuesta.

        :param cost_usd: costo en USD.
        """
        with self._lock:
            self._cost_usd += cost_usd

    def record_answer(
        self, agent: str, cost_usd: float, has_pii: bool, blocked: bool
    ) -> None:
        """Registra los contadores de negocio de una respuesta.

        :param agent: especialista que contestó.
        :param cost_usd: costo de la respuesta en USD.
        :param has_pii: si la petición tuvo datos personales.
        :param blocked: si la salida fue bloqueada.
        """
        with self._lock:
            self._by_agent[agent] = self._by_agent.get(agent, 0) + 1
            self._cost_by_agent[agent] = self._cost_by_agent.get(agent, 0.0) + cost_usd
            self._pii_detections += 1 if has_pii else 0
            self._outputs_blocked += 1 if blocked else 0

    def record_request(self, latency_ms: float, failed: bool) -> None:
        """Registra una petición.

        :param latency_ms: latencia en milisegundos.
        :param failed: si terminó con error del servidor.
        """
        with self._lock:
            self._latencies.append(latency_ms)
            self._failures += 1 if failed else 0

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Suma tokens consumidos.

        :param input_tokens: tokens de entrada.
        :param output_tokens: tokens de salida.
        """
        with self._lock:
            self._input_tokens += input_tokens
            self._output_tokens += output_tokens

    def snapshot(self) -> dict:
        """Devuelve el cuerpo de ``GET /metrics``.

        :return: diccionario con las métricas actuales.
        """
        with self._lock:
            values = sorted(self._latencies)
            total = len(values)
            p95 = _percentile(values, 0.95)
            return {
                "pid": os.getpid(),
                "requests": total,
                "error_rate": self._failures / total if total else 0,
                "latency_ms": {"p50": _percentile(values, 0.5), "p95": p95},
                "tokens": {
                    "input": self._input_tokens,
                    "output": self._output_tokens,
                },
                "cost_usd": self._cost_usd,
                "requests_by_agent": dict(self._by_agent),
                "cost_usd_by_agent": dict(self._cost_by_agent),
                "pii_detections": self._pii_detections,
                "outputs_blocked": self._outputs_blocked,
                "slo": {"p95_ms_target": self._target, "met": p95 < self._target},
            }
