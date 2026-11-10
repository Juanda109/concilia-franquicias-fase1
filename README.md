# Concilia BBVA - V1 sin IA
Baseline consolidada de las 17 historias técnicas.

Incluye recepción Host/Franquicias, HA22/HA26/HA32, jornada, bases operacionales OKD, reglas, conciliación determinística, Reporte Maestro, excepciones, decisión humana, reproceso, trazabilidad, APIs/OpenAPI, UX y observabilidad/OKD.

## Rutas
- `RECEPCION_HOST/OPERACIONES/host`
- `RECEPCION_HOST/OPERACIONES/franqucias`

## DDL
`sql/okd/` contiene un DDL por tabla y un DDL maestro.

## Fuera de esta rama
Agente IA y modelos ML. COBOL/JCL se cerrará al final con layouts definitivos.

## Seguridad
No versionar secretos, certificados, archivos productivos ni datos financieros reales.
