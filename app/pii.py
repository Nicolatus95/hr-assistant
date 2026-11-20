"""Detección y enmascarado de datos personales (PII) con expresiones regulares."""

import re

_LETTERS = "A-Za-zÑñ"
_PATTERNS = (
    ("CARD", re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")),
    (
        "CURP",
        re.compile(
            rf"(?<![A-Za-z0-9])[{_LETTERS}]{{4}}\d{{6}}[HhMm][{_LETTERS}]{{5}}"
            r"[A-Za-z0-9]\d(?![A-Za-z0-9])"
        ),
    ),
    (
        "RFC",
        re.compile(
            rf"(?<![A-Za-z0-9])[{_LETTERS}&]{{3,4}}\d{{6}}[A-Za-z0-9]{{3}}"
            r"(?![A-Za-z0-9])"
        ),
    ),
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("NSS", re.compile(r"(?<!\d)\d{11}(?!\d)")),
    (
        "PHONE",
        re.compile(r"(?<![\d+])(?:\+52[ -]?)?\d(?:[ -]?\d){9}(?!\d)"),
    ),
)


def _luhn(digits: str) -> bool:
    """Indica si una cadena de dígitos pasa la prueba de Luhn."""
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _replace_card(match: re.Match) -> str:
    """Reemplaza una coincidencia solo si es una tarjeta válida."""
    digits = re.sub(r"\D", "", match.group(0))
    if 13 <= len(digits) <= 19 and _luhn(digits):
        return "[CARD]"
    return match.group(0)


def mask(text: str) -> tuple[str, list[str]]:
    """Reemplaza cada dato personal por su marcador, por ejemplo ``[CURP]``.

    Los tipos se buscan en el orden CARD, CURP, RFC, EMAIL, NSS y PHONE, de
    modo que un número no se cuente dos veces.

    :param text: texto original.
    :return: la pareja ``(texto enmascarado, tipos encontrados)``; los tipos
        van sin repetir y en el orden de detección.
    """
    types: list[str] = []
    for kind, pattern in _PATTERNS:
        if kind == "CARD":
            masked = pattern.sub(_replace_card, text)
        else:
            masked = pattern.sub(f"[{kind}]", text)
        if masked != text:
            types.append(kind)
        text = masked
    return text, types
