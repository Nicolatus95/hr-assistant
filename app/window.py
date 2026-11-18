"""Palanca 2: ventana de historial."""


def trim_history(history: list[dict], window: int) -> list[dict]:
    """Deja solo los últimos mensajes del historial.

    :param history: mensajes previos, del más antiguo al más reciente.
    :param window: cuántos mensajes conservar.
    :return: los últimos ``window`` mensajes.
    """
    if window <= 0:
        return []
    return list(history[-window:])
