# 0012. Compliance como código al arrancar

## Contexto
Una mala configuración en producción (modelo simulado, claves débiles, trazas con textos de personas) es un incidente
de seguridad. Una lista de revisión manual se olvida.

## Decisión
`compliance.py` evalúa las reglas dentro de `load_config` cuando `ENVIRONMENT=production`. El producto se niega a
arrancar si `MODEL_PROVIDER` es `fake`, si `API_KEYS` está vacía o tiene una clave de menos de 16 caracteres, o si las
trazas están encendidas y `HIDE_INPUTS` o `HIDE_OUTPUTS` no valen `true`. Con `MODEL_PROVIDER=gateway` también se
niega si `CF_AIG_TOKEN` está vacía (ADR 0013). El error nombra la regla, nunca un valor secreto.
`doc/compliance-checklist.md` mapea cada regla a su código y a su prueba.

## Consecuencias
- Fallar rápido: el despliegue no queda sano con una configuración insegura, y `healthCheckPath` lo detecta.
- Las reglas se revisan solas en cada ejecución de pruebas.
- En desarrollo y pruebas no se aplican, así que el modelo simulado sigue sirviendo para CI y e2e.
- Agregar una regla exige código, prueba y una fila en la tabla.
