# 0001. API sin estado

## Contexto
El servicio debe escalar corriendo más copias detrás de un balanceador.

## Decisión
La API no guarda nada entre peticiones. El historial lo guarda el navegador y lo manda en `history`. Las dependencias (configuración, modelo, directorio) se crean en `create_app()` y son de solo lectura.

## Consecuencias
Cualquier copia puede atender cualquier petición. Las peticiones crecen con el historial, por eso se limita el largo de la pregunta. Las pruebas inyectan sus propias dependencias.
