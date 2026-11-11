# Versionamiento auditable de insumos – Migración 039

## Propósito

Permitir recibir una nueva versión de un insumo de una jornada aunque su archivo
vigente ya esté `PROCESADO`, conservando el archivo, checksum, detalle y
trazabilidad de la versión anterior.

La migración crea `public.con_insumo_archivo_version` y registra como versión 1
el archivo actualmente asociado a cada fila de `con_insumo_esperado`. Ese
backfill representa la primera versión conocida al instalar la migración; no
pretende reconstruir versiones históricas anteriores que no estén registradas.

## Instalación

Ejecutar `sql/migrations/039_VERSIONAMIENTO_ARCHIVOS_INSUMO.sql` una sola vez,
contra la base autorizada del entorno correspondiente. La migración no elimina
archivos, filas de detalle ni actualiza referencias vigentes.

## Recepción inicial

La recepción estándar no cambia: se envían `archivo`, `fecha_contable` y
`tipo_archivo`. La API registra la versión inicial y mantiene la referencia del
insumo en `con_insumo_esperado.id_archivo`.

## Sustituir un archivo ya procesado

La sustitución requiere dos campos multipart adicionales:

- `nueva_version=true`
- `motivo_version=<motivo funcional de la sustitución>` (máximo 500 caracteres)

Ejemplo conceptual de multipart:

```text
archivo=<archivo corregido>
fecha_contable=2026-10-23
tipo_archivo=HA22
nueva_version=true
motivo_version=Nuevo extracto Host recibido para corregir la version anterior
```

El archivo anterior y su detalle no se borran. La recepción inserta el archivo
nuevo, marca la versión anterior como `SUSTITUIDA`, registra la nueva como
`VIGENTE`, actualiza `con_insumo_esperado.id_archivo` y registra el evento
`ARCHIVO_VERSION_RECIBIDO`, todo en la misma transacción.

El procesamiento F1 se encola para el nuevo `id_archivo`. Los reportes que
consultan el `id_archivo` actualmente asociado al insumo pasan a tomar la nueva
versión una vez que se reciba y procese correctamente.

## Controles

- Una sola versión `VIGENTE` por insumo/jornada mediante índice único parcial.
- Número de versión único por insumo/jornada.
- Un archivo no puede pertenecer a dos versiones.
- El checksum no puede ser igual al de la versión vigente.
- Se conserva el bloqueo de jornadas no modificables.
- Una confirmación de cero movimientos exige su procedimiento explícito de
  revocación; una nueva versión no la revoca automáticamente.
- Los reemplazos de archivos `RECIBIDO` conservan la protección F1 que impide
  reemplazar un archivo con detalle ya persistido.
- El versionamiento no aprueba correspondencias monetarias ni certifica L8.

## Consulta del historial

`GET /api/v1/archivos/{id_archivo}/versiones` devuelve el historial del insumo,
con archivos anterior y vigente, estado, checksum, cantidad de registros y
motivo de cada sustitución.
