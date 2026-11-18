# 0002. Un solo agente con bucle con tope

## Contexto
El modelo decide en cada vuelta si pide una herramienta o responde; sin límite podría no terminar.

## Decisión
Un único agente con dos herramientas de solo lectura y un bucle limitado por `AGENT_MAX_STEPS`. Al agotar el tope responde exactamente "No pude completar la respuesta. Intenta con una pregunta más concreta.". JSON inválido o herramienta desconocida se devuelven al modelo como resultado de error.

## Consecuencias
Costo y latencia acotados. Preguntas que requieran muchas herramientas pueden no resolverse con el tope por omisión (3).
