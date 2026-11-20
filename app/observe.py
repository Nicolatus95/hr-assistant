"""Middleware de observabilidad: id de petición, métricas, log y encabezados."""

import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from app.context import request_id_var

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


def _decorate(response, request: Request, request_id: str) -> None:
    """Pone el id y los encabezados de seguridad en la respuesta."""
    response.headers["X-Request-ID"] = request_id
    response.headers.update(SECURITY_HEADERS)
    if request.method == "POST" and request.url.path == "/ask":
        response.headers["Cache-Control"] = "no-store"


def make_observer(logger, metrics):
    """Crea el middleware que asigna el id, mide, registra y atrapa errores.

    :param logger: log JSON del servicio.
    :param metrics: métricas del proceso.
    :return: la función middleware para ``app.middleware("http")``.
    """

    async def observe(request: Request, call_next):
        """Asigna el id de la petición, mide, registra y atrapa errores."""
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception as error:  # pylint: disable=broad-exception-caught
                logger.emit("error", error_type=type(error).__name__)
                response = JSONResponse(
                    status_code=500,
                    content={"detail": "internal error", "request_id": request_id},
                )
            latency_ms = (time.perf_counter() - started) * 1000
            _decorate(response, request, request_id)
            metrics.record_request(latency_ms, response.status_code >= 500)
            # El cliente lo fija la dependencia de auth en ``request.state``;
            # las variables de contexto no vuelven desde ``call_next``.
            known = getattr(request.state, "client", None)
            logger.emit(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                latency_ms=round(latency_ms, 3),
                **({"client": known} if known else {}),
            )
            return response
        finally:
            request_id_var.reset(token)

    return observe
