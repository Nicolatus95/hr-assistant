# HR Assistant

## Qué es

Sistema multi-agente de recursos humanos. Un supervisor reparte cada pregunta
a uno de dos especialistas: `directory` (empleados y departamentos) y
`policies` (políticas de RH). Es una API web sin estado con página de prueba,
observabilidad (un id por petición, log en JSON, métricas y trazas opcionales
en LangSmith), costos medidos y controles de seguridad.

- Producción: https://hr-assistant-myj2.onrender.com
- Documentación interactiva de la API: https://hr-assistant-myj2.onrender.com/docs

Endpoints: `GET /` (página), `GET /health`, `POST /ask`, `GET /metrics` y
`/docs`. Toda respuesta trae el encabezado `X-Request-ID`; `POST /ask` también
lo devuelve como `request_id` en el cuerpo. La página lo muestra para soporte.

## Requisitos previos

- Python 3.12.
- `uv` o `pip`.
- Docker (opcional, para correr el contenedor).
- Para el modelo real: cuentas de Cloudflare (Workers AI y AI Gateway con
  autenticación), de LangSmith (trazas) y de Render (despliegue).

## Clonar e instalar

```
git clone https://github.com/Nicolatus95/hr-assistant.git
cd hr-assistant
uv venv --python 3.12
uv pip install -r requirements-dev.txt
python -m playwright install chromium
```

`requirements.txt` trae solo las dependencias de producción;
`requirements-dev.txt` agrega pruebas, pylint y el navegador de las pruebas e2e.
Sin `uv`, usa `python -m venv .venv` y `pip install -r requirements-dev.txt`.

## Configuración

Copia `.env.example` a `.env` y completa los valores. Nunca subas el `.env`
al repositorio. La aplicación lee variables de entorno y no carga el archivo
por sí sola: expórtalas en el shell o pásalo al contenedor con `--env-file`.
Los secretos están marcados.

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `MODEL_PROVIDER` | `fake` | Modelo: `fake` (simulado) o `gateway` (Cloudflare) |
| `AGENT_MAX_STEPS` | `3` | Tope de vueltas del especialista |
| `MAX_QUESTION_CHARS` | `2000` | Largo máximo de la pregunta y de cada mensaje del historial |
| `EMPLOYEES_PATH` | `data/employees.json` | Archivo de empleados |
| `POLICIES_PATH` | `data/policies.json` | Políticas de RH (también sus palabras clave de ruteo) |
| `MAX_HISTORY_ITEMS` | `20` | Mensajes de historial permitidos (más: `422`) |
| `MAX_ANSWER_CHARS` | `1500` | Largo máximo de la respuesta; se recorta con `…` |
| `SERVICE_NAME` | `hr-assistant` | Campo `service` del log |
| `SLO_P95_MS` | `2000` | Meta de latencia p95 en ms |
| `ENVIRONMENT` | `development` | Con `production` se aplican las reglas de compliance |
| `API_KEYS` | vacía | Secreto. `cliente:clave,cliente2:clave2`; en producción, 16 caracteres o más |
| `RATE_LIMIT_PER_MINUTE` | `30` | Peticiones por cliente por minuto |
| `LANGSMITH_TRACING` | `false` | Enciende las trazas |
| `LANGSMITH_API_KEY` | vacía | Secreto. Clave de LangSmith; nunca se registra |
| `LANGSMITH_PROJECT` | `hr-assistant-local` | Proyecto de LangSmith |
| `PREFETCH_TOOLS` | `true` | El especialista trae en código el dato que indica el supervisor antes de llamar al modelo (cuenta como una vuelta, va en `tools_used` y se audita con `prefetched: true`). `false` es la línea base |
| `HIDE_INPUTS` | `true` | No enviar las entradas a LangSmith |
| `HIDE_OUTPUTS` | `true` | No enviar las salidas a LangSmith |
| `CF_ACCOUNT_ID` | vacía | Cuenta de Cloudflare; obligatoria con `gateway` |
| `CF_GATEWAY_ID` | `default` | Gateway de AI Gateway; obligatoria con `gateway` |
| `CF_API_TOKEN` | vacía | Secreto. Token de Cloudflare; obligatorio con `gateway` |
| `CF_AIG_TOKEN` | vacía | Secreto. Token del gateway autenticado; obligatorio en producción con `gateway` |
| `GATEWAY_BASE_URL` | `https://gateway.ai.cloudflare.com/v1` | URL base del gateway |
| `GATEWAY_TIMEOUT_SECONDS` | `30` | Tiempo máximo de espera del gateway |
| `MODEL_SMALL` | `@cf/meta/llama-3.1-8b-instruct-fast` | Modelo barato |
| `MODEL_LARGE` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Modelo capaz |
| `ROUTING` | `true` | Enrutamiento de modelo por pregunta |
| `ROUTER_MAX_CHARS` | `80` | Preguntas más largas van al modelo capaz |
| `HISTORY_WINDOW` | `6` | Mensajes de historial que se mandan al modelo |
| `MODEL_MAX_TOKENS` | `300` | Tope de tokens de salida |
| `MODEL_TEMPERATURE` | `0` | Temperatura del modelo |
| `CACHE_TTL_SECONDS` | `0` | Caché del gateway (0: apagada) |
| `PRICES_PATH` | `data/model_prices.json` | Precios por modelo |

Además, el contenedor y Render usan `PORT` (8000 por omisión), que no va en
`.env.example`. Sin `LANGSMITH_API_KEY` el producto funciona igual y no se
conecta a nada.

## Ejecutar

Desde la raíz del repositorio.

**Modelo simulado** (sin cuentas ni red):

```
uvicorn app.main:app
```

Abre http://127.0.0.1:8000. Con `API_KEYS` vacía, `POST /ask` y `GET /metrics`
responden `401`; define una clave, por ejemplo `API_KEYS=demo:clave-de-prueba-0123456789`.

**Modelo real** (Cloudflare AI Gateway):

```
MODEL_PROVIDER=gateway
CF_ACCOUNT_ID=...
CF_API_TOKEN=...
CF_AIG_TOKEN=...
API_KEYS=demo:clave-de-prueba-0123456789
uvicorn app.main:app
```

Exporta esas variables en tu shell (los valores son secretos, no los
escribas en el repositorio). Sin `CF_ACCOUNT_ID`, `CF_GATEWAY_ID` o
`CF_API_TOKEN`, el servicio no arranca con `gateway`.

**Contenedor:**

```
docker build -t hr-assistant .
docker run --rm -p 8000:8000 -e MODEL_PROVIDER=fake -e API_KEYS=demo:clave-de-prueba-0123456789 hr-assistant
```

El contenedor corre como usuario sin privilegios y arranca
`uvicorn app.main:app --no-server-header` en `0.0.0.0` y en el puerto `PORT`.
Solo instala `requirements.txt`. Para el modelo real, agrega
`--env-file .env` al `docker run`.

## Desplegar en Render

1. `render.yaml` es el Blueprint: servicio web Docker `hr-assistant`, plan
   `free`, `healthCheckPath: /health`, `ENVIRONMENT=production`,
   `MODEL_PROVIDER=gateway` y `CF_GATEWAY_ID=default`.
2. `API_KEYS`, `CF_ACCOUNT_ID`, `CF_API_TOKEN` y `CF_AIG_TOKEN` van en el
   Blueprint con `sync: false`: Render las declara sin valor y se escriben en
   Render > Environment. `LANGSMITH_API_KEY` no está en el Blueprint: se agrega
   a mano en Render > Environment.
3. El despliegue es automático solo con el CI en verde
   (`autoDeployTrigger: checksPass`).
4. Prueba de humo contra el servicio publicado (la clave va en la variable de
   entorno `SMOKE_API_KEY`, nunca como argumento):

```
python scripts/smoke.py https://hr-assistant-myj2.onrender.com
```

Comprueba que `/health` responde 200, que `/ask` sin clave responde 401 y que
`/ask` con clave responde 200.

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

## Costos

Con `MODEL_PROVIDER=gateway` se usa Cloudflare Workers AI a través de AI
Gateway; con `fake` hay dos modelos simulados con el nombre y el precio de
`MODEL_SMALL` y `MODEL_LARGE`. `POST /ask` agrega `model`, `route`,
`cached_calls` y `cost_usd`; `/metrics` agrega `cost_usd` acumulado. Si el
modelo falla, la API responde `502 {"detail": "model unavailable", "request_id": ...}`.
Las variables están en la tabla de Configuración.

Al arrancar se comprueba que `MODEL_SMALL` y `MODEL_LARGE` tengan precio en la
tabla de `PRICES_PATH`; si no, el servicio falla con un `ValueError` claro.

Medición con el modelo real y 10 preguntas:

| Escenario | Calidad | Costo (USD) | Cambio |
| --- | --- | --- | --- |
| Línea base: 70B sin palancas | 100 % | 0.003510 | |
| Con palancas (enrutamiento, ventana de historial, tope de tokens, prefetch) | 100 % | 0.000475 | -86 % |
| Con caché | 100 % | 0 | -100 % |

## Seguridad

`POST /ask` y `GET /metrics` exigen el encabezado `X-API-Key`; sin clave o con
una inválida responden `401 {"detail": "invalid or missing API key"}`. `GET /`,
`GET /health` y `/docs` no piden clave. La página guarda la clave en
`sessionStorage`. El nombre del cliente va en el log (`client`), la auditoría y
la traza; la clave nunca se registra. Pasado `RATE_LIMIT_PER_MINUTE`, la API
responde `429 {"detail": "rate limit exceeded"}` con `Retry-After`.

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

Con las dependencias de desarrollo instaladas (ver «Clonar e instalar»), desde
la raíz del repositorio, las pruebas unitarias y las de navegador (e2e):

```
python -m pytest tests
python -m pytest e2e
```

## Pruebas

La fábrica las corre con `uv run python -m verification unit` (desde la raíz
del repositorio).

La arquitectura y los ADR están en `doc/`.
