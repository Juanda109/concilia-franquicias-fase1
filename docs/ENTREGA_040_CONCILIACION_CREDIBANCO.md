# Entrega 040 - Conciliacion Credibanco operativa

## Objetivo

Exponer una matriz operativa utilizable por negocio a partir de los datos F1/F2 ya persistidos, sin convertir diagnósticos en homologaciones contables no aprobadas.

## Cambios

- Nuevo servicio `reporte_credibanco_productivo.py`.
- Nuevo endpoint `GET /api/v1/jornadas/{id_jornada}/conciliacion-credibanco`.
- Usa los seis conceptos/cuentas documentados en `catalogo_credibanco_inc44.json` y dos cuentas DEPO del cierre V67.
- Expone valor de origen y neto Host por HA22/HA26/HA32.
- No suma fuentes Host ni publica `total_host_homologado` sin regla aprobada.
- Mantiene estado `CONCILIACION_OPERATIVA_PENDIENTE_HOMOLOGACION` hasta aprobar reglas.

## Instalacion

1. Copiar el contenido del paquete conservando rutas.
2. Ejecutar `powershell -ExecutionPolicy Bypass -File .\scripts\aplicar_patch_040.ps1` desde la raiz.
3. Compilar y ejecutar la prueba incluida.

## Prueba

```powershell
& ".\.venv\Scripts\python.exe" -m py_compile `
  ".\backend\app\services\fase2\reporte_credibanco_productivo.py" `
  ".\backend\app\api\reporte_credibanco_productivo.py"

& ".\.venv\Scripts\python.exe" -m pytest `
  ".\tests\test_reporte_credibanco_productivo.py" -q --tb=short
```

## Uso

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8000/api/v1/jornadas/2590/conciliacion-credibanco"
```

El endpoint es operativo pero no certifica reglas sin aprobación. La matriz deja `total_host_homologado` y `diferencia_homologada` en `null` hasta que exista una regla aprobada con fuente, campo, signo, escala, moneda, tolerancia y evidencia.
