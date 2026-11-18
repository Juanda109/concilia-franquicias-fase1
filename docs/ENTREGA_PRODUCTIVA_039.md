# Entrega productiva 039 – Versionamiento de archivos de insumo

## Archivos modificados/agregados

- `sql/migrations/039_VERSIONAMIENTO_ARCHIVOS_INSUMO.sql`
- `backend/app/services/versionamiento_insumos.py`
- `backend/app/api/archivos.py`
- `tests/test_versionamiento_insumos.py`
- `tests/test_versionamiento_api_contrato.py`
- `scripts/aplicar_migracion_039.ps1`
- `docs/VERSIONAMIENTO_INSUMOS_039.md`

## Qué entrega

1. Historial de versiones por `id_insumo_esperado`.
2. Backfill de la referencia actualmente vigente como primera versión conocida.
3. Sustitución explícita de un archivo ya procesado con `nueva_version=true` y `motivo_version` obligatorio.
4. Conservación del archivo anterior y de sus detalles.
5. Cambio transaccional de versión vigente y puntero `con_insumo_esperado.id_archivo`.
6. Trazabilidad `ARCHIVO_VERSION_RECIBIDO`.
7. Consulta `GET /api/v1/archivos/{id_archivo}/versiones`.
8. Encolamiento existente de F1 para el nuevo identificador de archivo.

## Seguridad de la sustitución

- No se acepta una nueva versión sin motivo.
- Se rechaza el mismo checksum que la versión vigente.
- Una confirmación de cero movimientos no se revoca automáticamente.
- Se mantiene el bloqueo de jornada no modificable.
- Los reemplazos simples de archivos `RECIBIDO` conservan la protección que impide reemplazar detalles ya persistidos.
- El cliente que no envíe `nueva_version=true` mantiene el comportamiento anterior: los archivos procesados se rechazan.

## Instalación local

Desde PowerShell en la raíz del repositorio:

```powershell
.\scripts\aplicar_migracion_039.ps1
```

Parámetros opcionales:

```powershell
.\scripts\aplicar_migracion_039.ps1 -ContainerName "concilia-postgres" -DatabaseName "concilia_test" -DatabaseUser "concilia_app"
```

El script ejecuta primero la migración dentro de una transacción con `ROLLBACK`, y solo después la aplica con `COMMIT`.

## Ejemplo de nueva versión

Enviar a `POST /api/v1/archivos` con multipart:

- `archivo`: archivo corregido.
- `fecha_contable`: fecha de la jornada.
- `tipo_archivo`: `HA22`, `HA26`, `HA32` u otro insumo funcional.
- `nueva_version`: `true`.
- `motivo_version`: justificación de hasta 500 caracteres.

La respuesta devuelve `numero_version` e `id_archivo_anterior`.

## Pruebas ejecutadas en el entorno de revisión

- 24 pruebas de política, contrato y compatibilidad F1 aprobadas.
- Se amplió el conjunto incluyendo pruebas F2 puras: 88 pruebas aprobadas.
- `compileall backend/app` aprobado.

No se ejecutaron pruebas de integración que requieren PostgreSQL/`psycopg` en este entorno, ni se aplicó la migración a una base de datos. La migración debe probarse en `concilia_test` con el instalador incluido antes de desplegar a producción.

## Fuera de alcance de esta entrega

Esta entrega no aprueba escalas, signos, monedas ni cuentas contables; tampoco altera las reglas CANT/DEPO ni certifica L3/L5/L6/L8. Es la base de gobierno de versiones necesaria para que las nuevas evidencias Host puedan procesarse sin perder historia.
