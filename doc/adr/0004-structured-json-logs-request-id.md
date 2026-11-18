# 0004. Log JSON con un id por petición

## Contexto
Hay que responder qué pasó con una petición concreta sin guardar texto de personas.

## Decisión
Un middleware toma `X-Request-ID` o genera un UUID, lo guarda en un `ContextVar` y lo devuelve en la respuesta.
Cada evento (`request`, `agent_run`, `audit`, `error`) es una línea JSON en stdout con `ts`, `service`, `event`
y `request_id`. Nunca se registra el texto de la pregunta ni de la respuesta; solo su largo. El reloj se inyecta.

## Consecuencias
- Soporte busca un id y reconstruye la petición con un `grep`.
- Sin estado nuevo en la API: el log va a stdout y lo recoge la plataforma.
- Hay que probar que ningún texto de usuario llegue al log.
