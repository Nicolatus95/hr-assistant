"""Palanca 1: enrutamiento por reglas en código."""

from app.config import Config
from app.directory import normalize

KEYWORDS = ("compara", "resume", "explica", "por qué", "analiza", "todos")


def choose_model(question: str, config: Config) -> tuple[str, str]:
    """Elige el modelo para una pregunta.

    :param question: texto de la pregunta.
    :param config: configuración del servicio.
    :return: el modelo y el motivo (``routing_off``, ``long_question``,
        ``keyword:<palabra>`` o ``default``).
    """
    if not config.routing:
        return config.model_large, "routing_off"
    if len(question) > config.router_max_chars:
        return config.model_large, "long_question"
    normalized = normalize(question)
    for word in KEYWORDS:
        if normalize(word) in normalized:
            return config.model_large, f"keyword:{word}"
    return config.model_small, "default"
