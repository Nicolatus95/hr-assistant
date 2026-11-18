"""Precios por modelo y costo de cada llamada."""

import json
from pathlib import Path

MILLION = 1_000_000


class Pricing:
    """Tabla de precios en USD por millón de tokens.

    :param path: archivo JSON con la clave ``models``.
    """

    def __init__(self, path: Path) -> None:
        with open(path, encoding="utf-8") as handle:
            self._models = json.load(handle)["models"]

    def require(self, *models: str) -> None:
        """Verifica que cada modelo tenga precio.

        :param models: nombres de modelo a comprobar.
        :raises ValueError: si alguno no está en la tabla de precios.
        """
        missing = [name for name in models if name not in self._models]
        if missing:
            raise ValueError(
                f"MODEL_SMALL/MODEL_LARGE without a price in the price table: "
                f"{missing}"
            )

    def cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached: bool = False,
    ) -> float:
        """Calcula el costo de una llamada.

        :param model: nombre del modelo.
        :param input_tokens: tokens de entrada.
        :param output_tokens: tokens de salida.
        :param cached: si la llamada fue cacheada, no cuesta.
        :return: el costo en USD.
        :raises ValueError: si el modelo no tiene precio.
        """
        if model not in self._models:
            raise ValueError(f"No price for model {model!r}")
        if cached:
            return 0.0
        price = self._models[model]
        total = input_tokens * price["input"] + output_tokens * price["output"]
        return total / MILLION
