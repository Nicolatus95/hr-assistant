# 0005. Métricas en memoria por proceso

## Contexto
Se pide `GET /metrics` con peticiones, tasa de error, p50, p95, tokens y SLO, sin agregar librerías.

## Decisión
Un módulo `metrics.py` guarda contadores y una ventana acotada de latencias en memoria. `/metrics` las
resume junto con `pid`. `slo.met` es verdadero si el p95 es menor que `SLO_P95_MS`.

## Consecuencias
- Simple y sin dependencias; no rompe la API sin estado de negocio (no afecta las respuestas).
- Con varias copias cada una informa lo suyo; se distinguen por `pid`. Agregarlas queda fuera de esta sesión.
- Las métricas se pierden al reiniciar el proceso.
