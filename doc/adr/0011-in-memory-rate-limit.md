# 0011. Límite de peticiones en memoria con reloj inyectado

## Contexto
Un cliente con un error o abusivo puede agotar la cuota del modelo. El límite es por cliente y por minuto. La API es
sin estado (ADR 0001), así que un contador compartido sería una dependencia nueva.

## Decisión
`ratelimit.py` lleva un contador por cliente en memoria, en ventanas de un minuto, usando el reloj inyectado
(`clock.py`). Pasado `RATE_LIMIT_PER_MINUTE` responde `429 {"detail": "rate limit exceeded"}` con `Retry-After` en
segundos que faltan. Solo se cuentan peticiones con clave válida.

## Consecuencias
- Sin infraestructura extra y pruebas deterministas con un reloj falso.
- El estado es por proceso: con N copias el límite efectivo es hasta N veces mayor. Es aceptable con el plan gratuito
  de Render (una instancia); al escalar habrá que moverlo a un almacén compartido.
- Un reinicio borra los contadores.
- El conjunto de clientes es cerrado, así que la memoria del limitador no crece sin control.
