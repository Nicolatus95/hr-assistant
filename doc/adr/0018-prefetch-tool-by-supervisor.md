# 0018. Herramienta anticipada por el supervisor

Estado: Aceptado. Complementa al 0014.

## Contexto
Con el modelo real, el 8B contestaba sin llamar a la herramienta y la calidad bajó de 100 % a 30 %. Además, cada
vuelta de herramienta cuesta una llamada al modelo. El supervisor ya sabe qué dato hace falta.

## Decisión
Además de especialista y motivo, el supervisor indica herramienta y argumentos: `employee_id` → `get_employee` con el
primer id; `department` → `search_by_department`; `policy:<palabra>` → `get_policy`; `default` → ninguna. Con
`PREFETCH_TOOLS=true` el especialista ejecuta esa herramienta en código antes de la primera llamada al modelo y agrega
`Resultado de la herramienta: ...` a la conversación; el modelo solo redacta. La herramienta cuenta como una vuelta de
`AGENT_MAX_STEPS`, va en `tools_used`, se audita como `tool_call` con `prefetched: true` y deja su span `tool:<nombre>`.
Si el modelo la repite con los mismos argumentos recibe el error de llamada repetida. `agent_run` y los metadatos de
`hr_request` agregan `prefetched`. Con `PREFETCH_TOOLS=false` todo funciona como antes (línea base de `evaluate`).

## Consecuencias
Sube la calidad con el modelo pequeño y baja el costo (menos vueltas, prompts que no necesitan decidir la herramienta).
El supervisor deja de ser solo un selector y el reparto sigue sin gastar tokens. Una elección errónea de reglas trae un
dato irrelevante; se mitiga porque el modelo aún puede pedir otra herramienta propia. Las preguntas que cruzan
dominios mantienen la limitación del 0014.
