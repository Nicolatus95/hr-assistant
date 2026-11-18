"""Contexto de la petición en curso."""

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
client_var: ContextVar[str | None] = ContextVar("client", default=None)
