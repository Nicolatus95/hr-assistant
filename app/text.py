"""Normalización de texto compartida por el supervisor y las políticas."""

import unicodedata


def normalize(text: str) -> str:
    """Pasa a minúsculas y quita acentos.

    :param text: texto original.
    :return: texto normalizado para comparar.
    """
    decomposed = unicodedata.normalize("NFD", text.strip().lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))
