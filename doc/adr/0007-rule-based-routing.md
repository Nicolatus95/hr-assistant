# 0007. Enrutamiento por regla en código

## Contexto
Hay un modelo barato y uno capaz. Casi todas las preguntas son simples y pagar siempre el modelo grande sube el
costo sin mejorar la respuesta.

## Decisión
Una función pura (`router.py`) elige el modelo por pregunta con reglas fijas: largo, palabras clave o
`ROUTING=false`. No se usa otro modelo para clasificar. Se elige una vez por pregunta, no por vuelta del agente, y
el motivo se devuelve en `route`.

## Consecuencias
- Costo cero y decisión determinista, fácil de probar y de explicar.
- Una pregunta compleja sin palabra clave irá al modelo pequeño; se corrige ajustando las reglas con el set de
  evaluación.
- Quitar el enrutamiento es una variable (`ROUTING=false`), útil como línea base.
