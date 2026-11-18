# 0009. Proveedor gateway detrás de la interfaz y fallo como 502

## Contexto
El modelo real se llama a través de Cloudflare AI Gateway, que ofrece caché y requiere un token secreto.

## Decisión
`GatewayLLM` implementa la misma interfaz `complete` que el simulado, usa httpx y lee todo de la configuración.
Con `gateway` se exigen las tres variables `CF_*` al arrancar. Un fallo de red o un estado de error se convierte en
una excepción propia que `main.py` responde como `502 {"detail": "model unavailable", "request_id"}`. El token nunca
se escribe en logs, trazas ni mensajes de error.

## Consecuencias
- El agente no cambia al cambiar de proveedor (ver ADR 0003).
- Las pruebas usan `httpx.MockTransport` y no gastan cuota.
- El 502 distingue un fallo del modelo de un error interno (500).
- Sin reintentos por ahora: un fallo se ve de inmediato, a costa de menos tolerancia.
- El gateway puede exigir un segundo token (`CF_AIG_TOKEN`); ver ADR 0013.
