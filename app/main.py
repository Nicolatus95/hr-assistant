"""API web sin estado del HR Assistant."""

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from app.agent import Agent, directory_tools, policies_tools
from app.auth import authenticate
from app.clock import SystemClock
from app.config import Config, load_config
from app.context import client_var, request_id_var
from app.directory import Directory
from app.llm import LLMUnavailable, build_llm
from app.logging_setup import JsonLogger
from app.metrics import Metrics
from app.observe import make_observer
from app.orchestrator import Orchestrator
from app.pii import mask
from app.policies import Policies
from app.pricing import Pricing
from app.prompts import PROMPTS
from app.ratelimit import RateLimiter
from app.responses import AskRequest, AskResponse, agent_run_fields, build_response
from app.router import choose_model
from app.tracing import build_tracer

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _secret_values(config: Config, env) -> tuple[str, ...]:
    """Reúne los valores que la salida nunca debe contener.

    :param config: configuración del servicio.
    :param env: variables de entorno (de ahí sale la clave de LangSmith).
    :return: los valores no vacíos de las claves y los tokens.
    """
    values = [*config.api_keys.values(), config.cf_api_token, config.cf_aig_token]
    values.append(env.get("LANGSMITH_API_KEY", ""))
    return tuple(value for value in values if value)


def record_answer_metrics(metrics: Metrics, reply) -> None:
    """Registra tokens, costo y datos de la respuesta en las métricas.

    :param metrics: métricas del proceso.
    :param reply: respuesta del orquestador.
    """
    result = reply.result
    metrics.record_tokens(result.input_tokens, result.output_tokens)
    metrics.record_cost(result.cost_usd)
    metrics.record_answer(
        reply.agent,
        result.cost_usd,
        bool(reply.pii_types),
        reply.blocked is not None,
    )


def build_guards(api_keys, limiter: RateLimiter, logger=None):
    """Crea las dependencias de acceso y de límite de peticiones.

    :param api_keys: diccionario de cliente a clave.
    :param limiter: limitador de peticiones por cliente.
    :param logger: log JSON para la auditoría; opcional.
    :return: la pareja ``(require_client, limit_client)``.
    """

    def audit(action: str, **fields) -> None:
        """Registra un evento de auditoría si hay log."""
        if logger is not None:
            logger.emit("audit", action=action, **fields)

    async def require_client(request: Request) -> str:
        """Exige ``X-API-Key`` y devuelve el cliente.

        :raises HTTPException: 401 si la clave falta o no es válida.
        """
        client = authenticate(api_keys, request.headers.get("X-API-Key"))
        if client is None:
            # Solo la ruta: la clave recibida nunca se registra.
            audit("auth_failed", path=request.url.path)
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
            audit("rate_limited", client=client)
            raise HTTPException(
                status_code=429,
                detail="rate limit exceeded",
                headers={"Retry-After": str(wait)},
            )
        return client

    return require_client, limit_client


def prepare_inputs(request: AskRequest, config: Config, logger):
    """Valida la entrada y enmascara la PII antes de que llegue a otra parte.

    El enmascarado ocurre antes del enrutador, del supervisor, del modelo, del
    log y de la traza. La auditoría registra dónde y qué tipos, nunca el valor.

    :param request: cuerpo de ``POST /ask``.
    :param config: configuración del servicio.
    :param logger: log JSON para la auditoría.
    :return: la terna ``(pregunta, historial, tipos de PII)``, ya enmascarados.
    :raises HTTPException: 422 si la pregunta o el historial no son válidos.
    """
    limit = config.max_question_chars
    question = request.question
    if not question.strip() or len(question) > limit:
        raise HTTPException(status_code=422, detail="Invalid question length")
    too_long = any(len(item.content) > limit for item in request.history)
    if too_long or len(request.history) > config.max_history_items:
        raise HTTPException(status_code=422, detail="Invalid history")
    question, question_pii = mask(question)
    history = []
    history_pii: set[str] = set()
    for item in request.history:
        content, found = mask(item.content)
        history.append({"role": item.role, "content": content})
        history_pii.update(found)
    for where, found in (("question", question_pii), ("history", history_pii)):
        if found:
            logger.emit(
                "audit", action="pii_detected", where=where, types=sorted(found)
            )
    return question, history, sorted({*question_pii, *history_pii})


def _resolve_path(path: Path) -> Path:
    """Resuelve una ruta relativa contra el directorio actual y el del producto."""
    if path.is_absolute() or path.exists():
        return path
    return Path(__file__).resolve().parents[1] / path


def build_agents(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    config, llm, directory, policies, logger, tracer, pricing
) -> dict[str, Agent]:
    """Crea los especialistas, cada uno con su prompt y solo sus herramientas.

    :param config: configuración del servicio.
    :param llm: modelo compartido.
    :param directory: directorio de empleados.
    :param policies: políticas de RH.
    :param logger: log JSON para la auditoría de herramientas.
    :param tracer: tracer de LangSmith.
    :param pricing: precios por modelo.
    :return: diccionario de nombre de especialista a su agente.
    """
    toolsets = {
        "directory": directory_tools(directory),
        "policies": policies_tools(policies),
    }

    def audit_for(agent_name: str):
        """Crea la auditoría de herramientas de un especialista."""

        def audit(tool: str, args: dict) -> None:
            """Registra la llamada a una herramienta."""
            logger.emit(
                "audit", action="tool_call", tool=tool, args=args, agent=agent_name
            )

        return audit

    return {
        name: Agent(
            llm,
            directory,
            config.agent_max_steps,
            audit_for(name),
            tracer,
            pricing,
            name=name,
            prompt=PROMPTS[name],
            tools=tools,
        )
        for name, tools in toolsets.items()
    }


def create_app(  # pylint: disable=R0913,R0914,R0917
    config=None,
    llm=None,
    directory=None,
    clock=None,
    tracer=None,
    policies=None,
) -> FastAPI:
    """Construye la aplicación con sus dependencias.

    :param config: configuración; por omisión se lee del entorno.
    :param llm: modelo; por omisión se crea según la configuración.
    :param directory: directorio; por omisión se carga de la configuración.
    :param clock: reloj del log y del límite; por omisión el reloj del sistema.
    :param tracer: tracer; por omisión se crea según la configuración.
    :param policies: políticas de RH; por omisión se cargan de la configuración.
    :return: la aplicación FastAPI.
    """
    config: Config = config or load_config()
    directory = directory or Directory(config.employees_path)
    policies = policies or Policies(_resolve_path(config.policies_path))
    llm = llm or build_llm(config, directory, policies)
    clock = clock or SystemClock()
    logger = JsonLogger(config.service_name, clock)
    metrics = Metrics(config.slo_p95_ms, tuple(PROMPTS))
    tracer = tracer or build_tracer(config, os.environ)
    secrets = _secret_values(config, os.environ)

    pricing = Pricing(config.prices_path)
    pricing.require(config.model_small, config.model_large)
    agents = build_agents(config, llm, directory, policies, logger, tracer, pricing)
    orchestrator = Orchestrator(
        config, agents, policies, directory.departments, tracer, logger, secrets
    )
    limiter = RateLimiter(config.rate_limit_per_minute, clock)
    app = FastAPI(title="HR Assistant")

    app.middleware("http")(make_observer(logger, metrics))
    require_client, limit_client = build_guards(config.api_keys, limiter, logger)

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
        question, history, input_pii = prepare_inputs(request, config, logger)
        model, route = choose_model(question, config)
        try:
            reply = orchestrator.run(question, history, model, route, input_pii)
        except LLMUnavailable as error:
            logger.emit("error", error_type="LLMUnavailable", reason=str(error))
            return JSONResponse(
                status_code=502,
                content={
                    "detail": "model unavailable",
                    "request_id": request_id_var.get(),
                },
            )
        record_answer_metrics(metrics, reply)
        logger.emit(
            "agent_run",
            **agent_run_fields(
                reply, model, route, len(question), len(request.history)
            ),
        )
        return build_response(reply, model, route, request_id_var.get())

    return app


app = create_app()
