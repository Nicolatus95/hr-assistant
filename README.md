# HR Assistant

API web sin estado con un agente que responde preguntas sobre empleados y
departamentos usando un directorio local. Incluye observabilidad: un id por
petición, log en JSON, métricas y trazas opcionales en LangSmith.

## Cómo correrlo

```
pip install -r requirements.txt
uvicorn app.main:app
```

`requirements.txt` trae solo las dependencias de producción. Para pruebas y
navegador, ver la sección «Desarrollo».

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

## Supervisor y especialistas

Un supervisor reparte cada pregunta con reglas en código (cero tokens). En
orden: un id `EMP-0000` o el nombre de un departamento va a `directory` (motivo
`employee_id` o `department`); una palabra clave de una política (`keywords` de
`data/policies.json`, sin distinguir mayúsculas ni acentos) va a `policies`
(motivo `policy:<palabra>`); lo demás va a `directory` (motivo `default`).
Una pregunta la responde un solo especialista, cada uno con su prompt (en
`app/prompts.py`) y solo sus herramientas:

- `directory`: `get_employee` y `search_by_department`.
- `policies`: `get_policy(topic)` y `list_policies()`.

Una herramienta ajena responde `error: unknown tool` y queda en la auditoría.
`POST /ask` agrega `agent` y `agent_route`.

Limitación conocida: una pregunta que cruza dominios («¿cuántos días de
vacaciones tiene EMP-0004?») va a `directory` por la primera regla.

Las trazas de LangSmith van al proyecto `LANGSMITH_PROJECT` con el árbol
`hr_request` > `supervisor` > `agent:<nombre>` > `llm_call` y `tool:<nombre>`.
En los metadatos de `hr_request`, `agent_route` lleva solo el tipo de regla
(`policy`, no la palabra clave), para que no salga texto de la pregunta.

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `POLICIES_PATH` | `data/policies.json` | Políticas de RH |
| `MAX_HISTORY_ITEMS` | `20` | Mensajes de historial permitidos |
| `MAX_ANSWER_CHARS` | `1500` | Largo máximo de la respuesta |
| `LANGSMITH_PROJECT` | `hr-assistant-local` | Proyecto de LangSmith |
| `PREFETCH_TOOLS` | `true` | El especialista trae en código el dato que indica el supervisor antes de llamar al modelo (cuenta como una vuelta, va en `tools_used` y se audita con `prefetched: true`). `false` es la línea base |

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

### Datos personales, salida y auditoría

- **PII.** La pregunta y cada mensaje del historial se enmascaran antes del
  enrutador, del supervisor, del modelo, del log y de la traza; la respuesta
  también. Tipos, en este orden: `CARD` (con Luhn), `CURP`, `RFC`, `EMAIL`, `NSS`
  y `PHONE`; el marcador es `[CURP]`, etc. `POST /ask` agrega `pii_types`
  (ordenada y sin repetir). La página muestra el aviso `pii-notice`.
- **Entrada.** Un mensaje del historial de más de `MAX_QUESTION_CHARS`, o más de
  `MAX_HISTORY_ITEMS` mensajes, responde `422`.
- **Salida.** Después del especialista, una respuesta con HTML o con un secreto
  (claves de `API_KEYS`, `CF_API_TOKEN`, `CF_AIG_TOKEN`, `LANGSMITH_API_KEY`,
  `Bearer `, `lsv2_`) se cambia por un mensaje fijo y `output_blocked` vale
  `true`. Una respuesta de más de `MAX_ANSWER_CHARS` se recorta y termina en `…`.
- **Auditoría.** Eventos `audit` en el log: `agent_selected`, `tool_call`,
  `pii_detected` (dónde y tipos), `output_blocked` (motivo), `auth_failed`
  (ruta) y `rate_limited` (cliente). Nunca un valor, un texto ni una clave.
- **Encabezados.** Toda respuesta lleva `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY` y `Referrer-Policy: no-referrer`; `POST /ask` agrega
  `Cache-Control: no-store`.
- **Métricas.** `/metrics` agrega `requests_by_agent`, `cost_usd_by_agent`,
  `pii_detections` y `outputs_blocked`.

Cada control, su lugar en el código y su prueba están en
`doc/security-controls.md`.

## Desarrollo

```
pip install -r requirements-dev.txt
python -m playwright install chromium
```

Desde `product/`, las pruebas unitarias y las de navegador (e2e):

```
python -m pytest tests
python -m pytest e2e
```

### Contenedor

```
docker build -t hr-assistant .
docker run --rm -p 8000:8000 -e MODEL_PROVIDER=fake -e API_KEYS=demo:clave-de-prueba-0123456789 hr-assistant
```

El contenedor corre como usuario sin privilegios y arranca
`uvicorn app.main:app --no-server-header` en `0.0.0.0` y en el puerto `PORT`
(8000 por omisión). Solo instala `requirements.txt`.

## Pruebas

Con las dependencias de desarrollo instaladas, desde `product/`:

```
python -m pytest tests
python -m pytest e2e
```

La fábrica las corre con `uv run python -m verification unit` (desde la raíz
del repositorio).

La arquitectura y los ADR están en `doc/`.
