"""API web sin estado del HR Assistant."""

import os
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.agent import Agent
from app.auth import authenticate
from app.clock import SystemClock
from app.config import Config, load_config
from app.context import client_var, request_id_var
from app.directory import Directory
from app.llm import LLMUnavailable, build_llm
from app.logging_setup import JsonLogger
from app.metrics import Metrics
from app.pricing import Pricing
from app.ratelimit import RateLimiter
from app.router import choose_model
from app.tracing import build_tracer
from app.window import trim_history

STATIC_DIR = Path(__file__).resolve().parent / "static"


class HistoryItem(BaseModel):
    """Mensaje previo enviado por el cliente."""

    role: Literal["user", "assistant"]
    content: str


class AskRequest(BaseModel):
    """Cuerpo de ``POST /ask``."""

    question: str
    history: list[HistoryItem] = []


class AskResponse(BaseModel):
    """Respuesta de ``POST /ask``."""

    answer: str
    steps: int
    tools_used: list[str]
    input_tokens: int
    output_tokens: int
    request_id: str
    model: str
    route: str
    cached_calls: int
    cost_usd: float


def build_guards(api_keys, limiter: RateLimiter):
    """Crea las dependencias de acceso y de límite de peticiones.

    :param api_keys: diccionario de cliente a clave.
    :param limiter: limitador de peticiones por cliente.
    :return: la pareja ``(require_client, limit_client)``.
    """

    async def require_client(request: Request) -> str:
        """Exige ``X-API-Key`` y devuelve el cliente.

        :raises HTTPException: 401 si la clave falta o no es válida.
        """
        client = authenticate(api_keys, request.headers.get("X-API-Key"))
        if client is None:
            raise HTTPException(status_code=401, detail="invalid or missing API key")
        request.state.client = client
        client_var.set(client)
        return client

    async def limit_client(client: str = Depends(require_client)) -> str:
        """Aplica el límite de peticiones del cliente.

        :raises HTTPException: 429 con ``Retry-After`` si se pasó del límite.
        """
        wait = limiter.check(client)
        if wait:
            raise HTTPException(
                status_code=429,
                detail="rate limit exceeded",
                headers={"Retry-After": str(wait)},
            )
        return client

    return require_client, limit_client


def create_app(  # pylint: disable=too-many-locals
    config=None, llm=None, directory=None, clock=None
) -> FastAPI:
    """Construye la aplicación con sus dependencias.

    :param config: configuración; por omisión se lee del entorno.
    :param llm: modelo; por omisión se crea según la configuración.
    :param directory: directorio; por omisión se carga de la configuración.
    :param clock: reloj del log y del límite; por omisión el reloj del sistema.
    :return: la aplicación FastAPI.
    """
    config: Config = config or load_config()
    directory = directory or Directory(config.employees_path)
    llm = llm or build_llm(config, directory)
    clock = clock or SystemClock()
    logger = JsonLogger(config.service_name, clock)
    metrics = Metrics(config.slo_p95_ms)
    tracer = build_tracer(config, os.environ)

    def audit(tool: str, args: dict) -> None:
        """Registra la llamada a una herramienta."""
        logger.emit("audit", action="tool_call", tool=tool, args=args)

    pricing = Pricing(config.prices_path)
    pricing.require(config.model_small, config.model_large)
    agent = Agent(llm, directory, config.agent_max_steps, audit, tracer, pricing)
    limiter = RateLimiter(config.rate_limit_per_minute, clock)
    app = FastAPI(title="HR Assistant")

    @app.middleware("http")
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
            response.headers["X-Request-ID"] = request_id
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

    require_client, limit_client = build_guards(config.api_keys, limiter)

    @app.get("/metrics", dependencies=[Depends(require_client)])
    def get_metrics() -> dict:
        """Métricas de este proceso."""
        return metrics.snapshot()

    @app.get("/")
    def home() -> FileResponse:
        """Sirve la página web."""
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    def health() -> dict:
        """Estado del servicio."""
        return {"status": "ok", "pid": os.getpid()}

    @app.post(
        "/ask",
        response_model=AskResponse,
        responses={502: {}},
        dependencies=[Depends(limit_client)],
    )
    def ask(request: AskRequest):
        """Responde una pregunta sin guardar estado."""
        question = request.question
        if not question.strip() or len(question) > config.max_question_chars:
            raise HTTPException(status_code=422, detail="Invalid question length")
        model, route = choose_model(question, config)
        history = [h.model_dump() for h in request.history]
        messages = trim_history(history, config.history_window)
        messages.append({"role": "user", "content": question})
        try:
            result = agent.run(messages, model)
        except LLMUnavailable as error:
            logger.emit("error", error_type="LLMUnavailable", reason=str(error))
            return JSONResponse(
                status_code=502,
                content={
                    "detail": "model unavailable",
                    "request_id": request_id_var.get(),
                },
            )
        metrics.record_tokens(result.input_tokens, result.output_tokens)
        metrics.record_cost(result.cost_usd)
        logger.emit(
            "agent_run",
            question_chars=len(question),
            history_messages=len(request.history),
            steps=result.steps,
            tools=result.tools_used,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            stopped=result.stopped,
            model=model,
            route=route,
            cached_calls=result.cached_calls,
            cost_usd=result.cost_usd,
        )
        return AskResponse(
            model=model,
            route=route,
            cached_calls=result.cached_calls,
            cost_usd=result.cost_usd,
            request_id=request_id_var.get(),
            answer=result.answer,
            steps=result.steps,
            tools_used=result.tools_used,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )

    return app


app = create_app()
