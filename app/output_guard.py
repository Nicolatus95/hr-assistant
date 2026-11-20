"""Validación de la salida: HTML, secretos y largo máximo."""

import re
from collections.abc import Iterable

BLOCK_MESSAGE = "No puedo mostrar esa respuesta. Intenta con otra pregunta."
_HTML = re.compile(r"<[/!]?[A-Za-z]|javascript:", re.IGNORECASE)
_SECRET_PREFIXES = ("Bearer ", "lsv2_")


def check_output(
    text: str, secrets: Iterable[str], max_chars: int
) -> tuple[str, str | None]:
    """Bloquea respuestas con HTML o secretos y recorta las muy largas.

    :param text: respuesta del especialista.
    :param secrets: valores secretos que nunca deben salir; los vacíos se ignoran.
    :param max_chars: largo máximo de la respuesta.
    :return: la pareja ``(texto, motivo)``; el motivo es ``"html"``,
        ``"secret"`` o ``None``.
    """
    if _HTML.search(text):
        return BLOCK_MESSAGE, "html"
    leaked = any(prefix in text for prefix in _SECRET_PREFIXES)
    if leaked or any(secret and secret in text for secret in secrets):
        return BLOCK_MESSAGE, "secret"
    if len(text) > max_chars:
        return text[: max(max_chars - 1, 0)] + "…", None
    return text, None
