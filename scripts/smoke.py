"""Prueba de humo del HR Assistant ya publicado.

Uso: ``python scripts/smoke.py <url>``. La clave se lee de la variable de
entorno ``SMOKE_API_KEY``; nunca se acepta como argumento.
"""
import os
import sys
from collections.abc import Mapping

import httpx

TIMEOUT_SECONDS = 30


def check(name: str, ok: bool) -> bool:
    """Imprime ``[OK]`` o ``[FAIL]`` para una comprobacion y devuelve ``ok``."""
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    return ok


def run_checks(base_url: str, api_key: str, client: httpx.Client | None = None) -> bool:
    """Corre las tres comprobaciones contra ``base_url``.

    :param base_url: URL del servicio, sin barra final
    :param api_key: clave de un cliente valido (no se imprime)
    :param client: cliente HTTP; se inyecta en las pruebas
    :return: ``True`` si las tres pasan
    """
    base_url = base_url.rstrip("/")
    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    body = {"question": "Cuantos empleados hay?", "history": []}
    try:
        results = [
            check("/health responde 200",
                  client.get(f"{base_url}/health").status_code == 200),
            check("/ask sin clave responde 401",
                  client.post(f"{base_url}/ask", json=body).status_code == 401),
            check("/ask con clave responde 200",
                  client.post(f"{base_url}/ask", json=body,
                              headers={"X-API-Key": api_key}).status_code == 200),
        ]
    except httpx.HTTPError as error:
        # Solo el tipo de error: el mensaje podria incluir datos de la peticion
        check(f"conexion con {base_url} ({type(error).__name__})", False)
        return False
    finally:
        if owns_client:
            client.close()
    return all(results)


def main(argv: list[str], env: Mapping[str, str],
         transport: httpx.BaseTransport | None = None) -> int:
    """Punto de entrada; devuelve 0 si todo pasa y distinto de 0 si algo falla.

    :param argv: argumentos sin el nombre del programa, p. ej. ``["http://svc"]``
    :param env: entorno del que sale la clave (``SMOKE_API_KEY``)
    :param transport: transporte HTTP opcional, se inyecta en las pruebas
    """
    api_key = env.get("SMOKE_API_KEY", "")
    if not api_key:
        print("Falta la variable de entorno SMOKE_API_KEY")
        return 2
    if len(argv) != 1:
        print("Uso: python scripts/smoke.py <url> (la clave va en SMOKE_API_KEY)")
        return 2
    with httpx.Client(timeout=TIMEOUT_SECONDS, transport=transport) as client:
        return 0 if run_checks(argv[0], api_key, client) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ))
