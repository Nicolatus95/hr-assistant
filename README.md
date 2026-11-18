# HR Assistant

API web sin estado con un agente que responde preguntas sobre empleados y
departamentos usando un directorio local. Incluye observabilidad: un id por
petición, log en JSON, métricas y trazas opcionales en LangSmith.

## Cómo correrlo

```
pip install -r requirements.txt
uvicorn app.main:app
```

Endpoints: `GET /` (página), `GET /health`, `POST /ask`, `GET /metrics`.
Toda respuesta trae el encabezado `X-Request-ID`; `POST /ask` también lo
devuelve como `request_id` en el cuerpo. La página lo muestra para soporte.

## Variables de entorno

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `MODEL_PROVIDER` | `fake` | Modelo a usar |
| `AGENT_MAX_STEPS` | `3` | Tope de vueltas del agente |
| `MAX_QUESTION_CHARS` | `2000` | Largo máximo de la pregunta |
| `EMPLOYEES_PATH` | `data/employees.json` | Archivo de empleados |
| `SERVICE_NAME` | `hr-assistant` | Campo `service` del log |
| `SLO_P95_MS` | `2000` | Meta de latencia p95 en ms |
| `LANGSMITH_TRACING` | `false` | Enciende las trazas |
| `LANGSMITH_API_KEY` | (vacía) | Clave de LangSmith; nunca se registra |
| `HIDE_INPUTS` / `HIDE_OUTPUTS` | `true` | No enviar textos a LangSmith |

Sin `LANGSMITH_API_KEY` el producto funciona igual y no se conecta a nada.

## Costos

Con `MODEL_PROVIDER=gateway` se usa Cloudflare Workers AI a través de AI
Gateway; con `fake` hay dos modelos simulados con el nombre y el precio de
`MODEL_SMALL` y `MODEL_LARGE`. Copia `.env.example` a `.env` para configurar.
`POST /ask` agrega `model`, `route`, `cached_calls` y `cost_usd`; `/metrics`
agrega `cost_usd` acumulado. Si el modelo falla, la API responde
`502 {"detail": "model unavailable", "request_id": ...}`.

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `CF_ACCOUNT_ID`, `CF_GATEWAY_ID`, `CF_API_TOKEN` | vacías | Cuenta, gateway y token (secreto); obligatorias con `gateway` |
| `MODEL_SMALL` | `@cf/meta/llama-3.1-8b-instruct-fast` | Modelo barato |
| `MODEL_LARGE` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Modelo capaz |
| `ROUTING` | `true` | Enrutamiento por pregunta |
| `ROUTER_MAX_CHARS` | `80` | Preguntas más largas van al modelo capaz |
| `HISTORY_WINDOW` | `6` | Mensajes de historial que se mandan |
| `MODEL_MAX_TOKENS` | `300` | Tope de tokens de salida |
| `MODEL_TEMPERATURE` | `0` | Temperatura del modelo |
| `CACHE_TTL_SECONDS` | `0` | Caché del gateway (0: apagada) |
| `PRICES_PATH` | `data/model_prices.json` | Precios por modelo |
| `GATEWAY_BASE_URL` | `https://gateway.ai.cloudflare.com/v1` | URL base del gateway |
| `GATEWAY_TIMEOUT_SECONDS` | `30` | Tiempo máximo de espera del gateway |

Al arrancar se comprueba que `MODEL_SMALL` y `MODEL_LARGE` tengan precio en la
tabla; si no, el servicio falla con un `ValueError` claro.

## Seguridad

`POST /ask` y `GET /metrics` exigen el encabezado `X-API-Key`; sin clave o con
una inválida responden `401 {"detail": "invalid or missing API key"}`. `GET /`,
`GET /health` y `/docs` no piden clave. La página guarda la clave en
`sessionStorage`. El nombre del cliente va en el log (`client`), la auditoría y
la traza; la clave nunca se registra. Pasado `RATE_LIMIT_PER_MINUTE`, la API
responde `429 {"detail": "rate limit exceeded"}` con `Retry-After`.

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | Con `production` se aplican las reglas de compliance |
| `API_KEYS` | vacía | `cliente:clave,cliente2:clave2` (secreto) |
| `RATE_LIMIT_PER_MINUTE` | `30` | Peticiones por cliente por minuto |
| `CF_AIG_TOKEN` | vacía | Token del gateway (secreto) |

El gateway `default` de Cloudflare tiene la autenticación encendida: además de
`Authorization` con `CF_API_TOKEN`, pide el token en el encabezado
`cf-aig-authorization`. Se manda solo si `CF_AIG_TOKEN` tiene valor, y en
producción con `MODEL_PROVIDER=gateway` es obligatorio.

Con `ENVIRONMENT=production` el producto no arranca si el modelo es `fake`, si
`API_KEYS` está vacía o tiene una clave de menos de 16 caracteres, si hay
trazas sin `HIDE_INPUTS` y `HIDE_OUTPUTS` en `true`, o si falta `CF_AIG_TOKEN`
con `gateway`. Ver `doc/compliance-checklist.md`.

## Pruebas

```
uv run python -m verification unit
```

La arquitectura y los ADR están en `doc/`.
