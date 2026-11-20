# 0014. Supervisor con dos especialistas

Estado: Aceptado. Reemplaza al 0002.

## Contexto
Un solo agente con todas las herramientas tiene más privilegio del necesario y un prompt largo (más costo). Ahora hay
dos dominios: directorio de empleados y políticas de RH.

## Decisión
Un supervisor elige al especialista con reglas en código, sin llamar al modelo: id `EMP-0000` o departamento →
`directory`; palabra clave de política → `policies`; si no, `directory` (`default`). Cada especialista tiene solo sus
herramientas, su prompt corto (máx. 120 palabras, en el código) y conserva el bucle con tope, el enrutamiento de modelo,
la ventana de historial y el costo. Una herramienta ajena devuelve `error: unknown tool` y se audita.

## Consecuencias
Mínimo privilegio y cero tokens en el reparto. Una pregunta responde un solo especialista: las que cruzan dominios
(«¿cuántos días de vacaciones tiene EMP-0004?») van a `directory`. Es una limitación conocida y documentada.
