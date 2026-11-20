# 0017. Árbol de trazas con cliente inyectable y proyecto explícito

Estado: Aceptado (reemplaza al 0006)

## Contexto
El 0006 describía `@traceable` sobre funciones sueltas. Con el supervisor y los especialistas (0014) hace falta un
árbol por petición, un proyecto de LangSmith fijo y trazas probables sin red. Los textos y la PII no deben salir.

## Decisión
`tracing.py` usa `trace` y `tracing_context` de `langsmith.run_helpers` dentro de `Tracer.span`. El `Client` se
inyecta (`build_tracer(config, env, client=None)`), así las pruebas pasan uno falso. Sin `LANGSMITH_TRACING=true` y
`LANGSMITH_API_KEY` el `Tracer` queda apagado y no se conecta. El proyecto sale de `LANGSMITH_PROJECT` (por omisión
`hr-assistant-local`) y se pasa de forma explícita. El árbol es `hr_request` > `supervisor` > `agent:<nombre>` >
`llm_call` y `tool:<nombre>`; lo arma `Orchestrator`. Los metadatos llevan solo `request_id`, `client`, `environment`,
agente, tipo de regla (`policy`, no la palabra), modelo, ruta, pasos, tokens, costo, `pii_types` y banderas; nunca
texto ni valores de PII. `HIDE_INPUTS` y `HIDE_OUTPUTS` valen `true` por omisión y también se aplican en el `Client`.
La clave solo se lee del entorno y nunca se escribe.

## Consecuencias
- Pruebas y desarrollo corren sin conexión; el cliente falso permite comprobar el árbol y los metadatos.
- Un tramo con excepción queda marcado con error.
- En producción la compliance exige `HIDE_*` en `true` si hay trazas.
- El resto del código depende de `tracing.py`, no directamente de `langsmith`.
