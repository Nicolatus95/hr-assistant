# Arquitectura del HR Assistant

API FastAPI sin estado, un agente con bucle con tope, modelo detrás de una interfaz y un directorio de empleados
de solo lectura. La sesión 2 agrega observabilidad. La sesión 3 agrega el modelo real por AI Gateway y cuatro
palancas de costo. La sesión 4 agrega acceso por clave, límite de peticiones, compliance al arrancar, contenedor, CI
y publicación en Render, y el gateway autenticado con un segundo token (`CF_AIG_TOKEN`). Ver `adr/`.

```mermaid
flowchart LR
    U[Personal de RH] --> W[index.html<br/>clave en sessionStorage]
    W -- POST /ask, X-API-Key --> M[main.py<br/>create_app + middleware]
    M --> AU[auth.py<br/>cliente por clave]
    M --> RL[ratelimit.py<br/>por cliente y minuto]
    M --> C[config.py]
    C --> CP[compliance.py<br/>reglas de produccion]
    M --> X[context.py<br/>request_id, client]
    M -- historial --> H[window.py]
    M -- pregunta --> RT[router.py]
    M --> A[agent.py<br/>bucle con tope]
    A -- complete messages, model --> L[llm.py<br/>FakeLLM / GatewayLLM]
    L -- HTTPS, Authorization + cf-aig-authorization --> GW[(AI Gateway<br/>Workers AI)]
    A -- tokens, model, cached --> P[pricing.py]
    A -- tools --> D[directory.py]
    D --> J[(data/employees.json)]
    M --> G[logging_setup.py<br/>JSON con client]
    A -- audit --> G
    M --> T[metrics.py]
    U2[Soporte] -- GET /metrics, X-API-Key --> M
    A -. traceable .-> R[tracing.py]
    R -. opcional .-> S[(LangSmith)]
    K[clock.py] --> M
    K --> RL
    K --> G
    subgraph Entrega
        GH[GitHub Actions<br/>style, unit, e2e, docker] -- checksPass --> RN[Render<br/>Dockerfile, render.yaml]
    end
    RN --> M
    SM[scripts/smoke.py] -. health, ask .-> RN
```

Módulos:
- `config.py`: configuración validada al arrancar; aplica `compliance.py` en producción. Lee `CF_AIG_TOKEN` (secreta,
  `repr=False`, vacía por omisión).
- `compliance.py`: reglas de `ENVIRONMENT=production`; el producto no arranca si falla alguna, incluida
  `CF_AIG_TOKEN` vacía con `gateway`.
- `auth.py`: parsea `API_KEYS` y resuelve el cliente por `X-API-Key`; nunca registra la clave.
- `ratelimit.py`: límite por cliente y minuto en memoria, con reloj inyectado y `Retry-After`.
- `directory.py`: herramientas de solo lectura.
- `llm.py`: interfaz `complete(messages, model)`, modelo simulado y cliente del gateway, que manda
  `cf-aig-authorization` solo si hay `CF_AIG_TOKEN`.
- `router.py`: elige modelo y motivo por pregunta con reglas en código.
- `window.py`: recorta el historial a la ventana configurada.
- `pricing.py`: costo por llamada con la tabla de precios; las llamadas cacheadas valen 0.
- `agent.py`: bucle herramienta/respuesta con tope, con auditoría y acumulado de costo.
- `main.py`: rutas `/`, `/health`, `/ask`, `/metrics`, middleware de `request_id`, 401, 429 y 502.
- `clock.py`: reloj inyectable.
- `context.py`: `request_id` y `client` de la petición actual.
- `logging_setup.py`: eventos JSON de una línea, con `client`.
- `metrics.py`: contadores, percentiles, SLO y costo acumulado por proceso.
- `tracing.py`: trazas opcionales con datos ocultos por omisión.
