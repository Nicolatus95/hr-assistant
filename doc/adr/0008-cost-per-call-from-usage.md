# 0008. Costo calculado por llamada desde los tokens reales

## Contexto
Hay que medir cada palanca. El modelo simulado también debe tener precio para medir sin red, y las llamadas con
caché del gateway no cuestan.

## Decisión
Cada llamada devuelve `model`, tokens y `cached`. `pricing.py` calcula el costo con la tabla de precios por millón
de tokens (`data/model_prices.json`) y el agente lo suma. Una llamada con `cf-aig-cache-status: HIT` vale 0 y cuenta
en `cached_calls`. `FakeLLM` reporta el nombre del modelo recibido para usar el precio de ese nombre.

## Consecuencias
- El costo se puede comparar entre configuraciones sin gastar cuota.
- Los precios cambian: la tabla es un archivo editable y se valida al arrancar.
- El costo de la respuesta es la suma de todas las vueltas del agente, no solo de una llamada.
- El simulado cuenta palabras, así que sus costos sirven para comparar, no como cifra real.
