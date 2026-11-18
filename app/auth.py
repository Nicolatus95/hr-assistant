"""Claves de API por cliente."""

import hmac
from collections.abc import Mapping


def parse_api_keys(raw: str) -> dict[str, str]:
    """Convierte ``cliente:clave,cliente2:clave2`` en un diccionario.

    Los errores dicen qué entrada falla y su largo, nunca su valor.

    :param raw: valor de ``API_KEYS``; vacío significa sin clientes.
    :return: diccionario de nombre de cliente a clave.
    :raises ValueError: si una entrada no tiene la forma ``cliente:clave`` o si
        un cliente se repite.
    """
    keys: dict[str, str] = {}
    if not raw.strip():
        return keys
    for position, entry in enumerate(raw.split(","), start=1):
        name, separator, key = entry.strip().partition(":")
        name = name.strip()
        if not separator or not name or not key:
            raise ValueError(
                f"API_KEYS entry {position} is malformed "
                f"(length {len(entry.strip())}); expected client:key"
            )
        if name in keys:
            raise ValueError(f"API_KEYS repeats the client {name!r}")
        keys[name] = key
    return keys


def authenticate(keys: Mapping[str, str], provided: str | None) -> str | None:
    """Busca al cliente dueño de una clave en tiempo constante.

    Recorre todos los clientes para que el tiempo no dependa de cuál acierta.

    :param keys: diccionario de cliente a clave.
    :param provided: valor del encabezado ``X-API-Key``, si vino.
    :return: el nombre del cliente, o ``None`` si la clave falta o no coincide.
    """
    if not provided:
        return None
    candidate = provided.encode("utf-8")
    found = None
    for name, key in keys.items():
        if hmac.compare_digest(candidate, key.encode("utf-8")):
            found = name
    return found
