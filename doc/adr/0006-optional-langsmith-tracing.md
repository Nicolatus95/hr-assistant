# 0006. Trazas opcionales en LangSmith, ocultas por omisión

## Contexto
Se quieren trazas de agente, modelo y herramientas, pero el producto debe funcionar sin red ni clave y sin
filtrar preguntas de personas.

## Decisión
`tracing.py` envuelve `@traceable` y solo lo activa con `LANGSMITH_TRACING=true` y `LANGSMITH_API_KEY`; si no,
es un no-op que no se conecta. `HIDE_INPUTS` y `HIDE_OUTPUTS` valen `true` por omisión. El `request_id` va en
los metadatos. La clave solo se lee del entorno y nunca se escribe.

## Consecuencias
- Pruebas y desarrollo corren sin conexión.
- Quien quiera ver el contenido debe apagar `HIDE_*` de forma explícita.
- Agente, modelo y herramientas dependen de `tracing.py` y no directamente de `langsmith`.
