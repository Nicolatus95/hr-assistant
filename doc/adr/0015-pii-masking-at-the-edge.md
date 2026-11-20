# 0015. PII enmascarada antes de llegar al modelo

Estado: Aceptado.

## Contexto
Las preguntas y el historial pueden traer datos personales (CURP, RFC, tarjeta, correo, NSS, teléfono) que no deben llegar
al modelo, al supervisor, a la traza ni al log.

## Decisión
`pii.py` detecta con expresiones regulares (tarjeta con Luhn) en orden fijo y reemplaza por marcadores como `[CURP]`.
Se aplica a la pregunta y al historial antes de cualquier otro paso, y a la respuesta antes de devolverla. La auditoría
registra `pii_detected` con el lugar y los tipos, nunca el valor. `POST /ask` devuelve `pii_types`.

## Consecuencias
El modelo nunca ve el dato real y la pregunta sigue su curso. Hay falsos positivos y negativos posibles (es una detección
por patrones, no semántica); el orden fijo evita contar un número dos veces y los ids y fechas quedan fuera.
