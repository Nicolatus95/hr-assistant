# 0016. Validación de la salida antes de responder

Estado: Aceptado.

## Contexto
La respuesta del modelo no es de confianza: podría traer HTML, filtrar un secreto o ser demasiado larga.

## Decisión
Después del especialista, `output_guard.py` reemplaza la respuesta por «No puedo mostrar esa respuesta. Intenta con otra
pregunta.» si tiene HTML o un secreto (claves de `API_KEYS`, `CF_API_TOKEN`, `CF_AIG_TOKEN`, `LANGSMITH_API_KEY`, o los
prefijos `Bearer ` y `lsv2_`). Marca `output_blocked` y audita solo el motivo (`html` o `secret`). Si pasa de
`MAX_ANSWER_CHARS`, la recorta con «…». La página sigue usando `textContent`.

## Consecuencias
Defensa en capas junto con `textContent`. Una respuesta legítima con `<` seguido de una etiqueta se bloquea; se acepta
por seguridad. La lista de secretos se arma al arrancar e ignora valores vacíos.
