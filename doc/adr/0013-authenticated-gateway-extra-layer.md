# 0013. Gateway autenticado como capa extra de seguridad

## Contexto
El AI Gateway "default" de Cloudflare tiene la autenticación encendida y no se puede apagar. Además de
`Authorization: Bearer {CF_API_TOKEN}`, cada llamada a `gateway.ai.cloudflare.com` debe llevar
`cf-aig-authorization: Bearer {CF_AIG_TOKEN}`. Es una segunda credencial: quien tenga solo el token de la API no
puede usar el gateway.

## Decisión
- Variable nueva `CF_AIG_TOKEN`: secreta y vacía por omisión. Si tiene valor, `GatewayLLM` manda el encabezado
  `cf-aig-authorization`; si está vacía, no lo manda (útil en desarrollo y en pruebas).
- `compliance.py` agrega una regla: con `ENVIRONMENT=production` y `MODEL_PROVIDER=gateway`, el producto no arranca
  si `CF_AIG_TOKEN` está vacía.
- El token se trata igual que `CF_API_TOKEN`: `repr=False` y nunca en log, traza ni error.
- En Render va con `sync: false`.

## Consecuencias
- Defensa en profundidad: dos secretos distintos protegen la salida al modelo.
- En producción un gateway sin token falla al arrancar y no con un 401 en la primera pregunta.
- Una variable secreta más que rotar y que escribir a mano en Render.
- En desarrollo sigue funcionando sin token (gateway sin autenticación o modelo simulado).
