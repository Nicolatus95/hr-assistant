# 0010. Una clave por cliente en el encabezado X-API-Key

## Contexto
Al publicar, `POST /ask` gasta cuota del modelo y `GET /metrics` expone datos operativos. Hace falta saber quién
llama, poder revocar a un cliente y no filtrar nunca la clave.

## Decisión
`API_KEYS` (`cliente:clave,cliente2:clave2`) se parsea al arrancar en `auth.py`. `POST /ask` y `GET /metrics` exigen
`X-API-Key`; la comparación usa `hmac.compare_digest`. Sin clave o inválida: `401 {"detail": "invalid or missing API
key"}`. `/`, `/health` y `/docs` quedan abiertas. El nombre del cliente se guarda en un contexto y va al log
(`client`), a la auditoría y a los metadatos de traza. Una entrada mal formada impide arrancar y el error dice qué
entrada falla y su largo, nunca su valor.

## Consecuencias
- La API sigue sin estado: las claves vienen del entorno, no de una base de datos.
- Revocar o rotar una clave exige cambiar la variable y reiniciar.
- La clave nunca se escribe en logs, trazas ni errores; las pruebas lo vigilan.
- La página guarda la clave en `sessionStorage`, así que se pierde al cerrar la pestaña.
