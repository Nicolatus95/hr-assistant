# 0003. Modelo detrás de una interfaz `complete(messages)`

## Contexto
Hoy solo hay modelo simulado; mañana habrá proveedores reales. El agente no debe cambiar por eso.

## Decisión
`llm.py` define la interfaz `complete(messages)` y una fábrica según `MODEL_PROVIDER`. En esta sesión solo existe `FakeLLM`, determinista y sin red, que también cuenta tokens aproximados.

## Consecuencias
Pruebas rápidas y reproducibles sin costo. Agregar un proveedor es una clase nueva más una entrada en la fábrica. Un proveedor desconocido impide arrancar.
