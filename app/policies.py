"""Políticas de RH de solo lectura."""

import json
from pathlib import Path

from app.text import normalize


class Policies:
    """Políticas cargadas una sola vez desde un archivo JSON.

    :param path: ruta del archivo ``policies.json``.
    """

    def __init__(self, path) -> None:
        with Path(path).open(encoding="utf-8") as handle:
            self._policies = tuple(json.load(handle))

    @property
    def keywords(self) -> tuple[str, ...]:
        """Palabras clave normalizadas de todas las políticas, en orden."""
        return tuple(
            normalize(word) for policy in self._policies for word in policy["keywords"]
        )

    def get_policy(self, topic: str) -> dict | None:
        """Busca una política por id, tema o palabra clave.

        :param topic: texto a buscar, sin distinguir mayúsculas ni acentos.
        :return: una copia de la política o ``None`` si no existe.
        """
        wanted = normalize(str(topic))
        for policy in self._policies:
            names = [policy["id"], policy["topic"], *policy["keywords"]]
            if wanted in (normalize(name) for name in names):
                return dict(policy)
        return None

    def list_policies(self) -> list[dict]:
        """Lista todas las políticas.

        :return: copias de las políticas.
        """
        return [dict(policy) for policy in self._policies]

    def find_keyword(self, text: str) -> str | None:
        """Devuelve la primera palabra clave que aparece en el texto.

        :param text: texto a revisar, sin distinguir mayúsculas ni acentos.
        :return: la palabra clave normalizada, o ``None``.
        """
        normalized = normalize(text)
        for word in self.keywords:
            if word in normalized:
                return word
        return None
