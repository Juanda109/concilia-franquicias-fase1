# Conciliación Franquicias — Fase 1 — paquete completo para Git

Este repositorio consolida los componentes vigentes de Fase 1 en una sola raíz para Git/despliegue.

## Baseline
- 12 archivos esperados/procesables.
- CAIT fuera de Fase 1.
- 21 tablas activas: 8 transversales + 13 de resultado.
- 10 mappings prioritarios: HA22, HA26, HA32, CAET, CANT, DEPO, Carta CEI 240A, PMD, MEP y VSS.
- PMPD1322 y PMRD8000 siguen visibles, esperados y participantes de KPI; su parser detallado se desarrolla al final.
- Orquestación funcional: Control-M Local Colombia -> Hub Linux -> SFTP puerto 22 -> MinIO/OKD.

## Componentes incluidos
- `backend/`: FastAPI, ingesta, parsers, repositories, estados, errores y pruebas.
- `database/`: DDL consolidado de 21 tablas, DDL individuales, migración y seed de los 12 insumos.
- `config/`: JSON y YAML de baseline, inventario, mappings, reglas, API, frontend e infraestructura.
- `openapi/`: especificación OpenAPI vigente.
- `components/python/`: componentes y paquetes de mapping generados/validados.
- `docs/mappings/`: matrices técnicas y equivalencias Excel/Python.
- `deploy/okd/`: Deployment, Service, ConfigMap y plantilla Secret.
- `deploy/control-m/`: definición de responsabilidades de Control-M Local Colombia.
- `frontend/`: tipos/interfaz TypeScript base.
- `demo/`: demo v59, con pendientes de infraestructura e integración únicamente en API/Swagger.

## CronJobs
Control-M Local Colombia es el orquestador funcional. No se deben crear CronJobs OKD que dupliquen calendarización, disparadores, dependencias o reintentos. Un CronJob OKD solo aplica a una tarea técnica interna explícitamente justificada.

## Antes de producción
Deben suministrarse los valores corporativos/por ambiente pendientes: API Gateway, seguridad/headers, credenciales SFTP, rutas MinIO, jobs/calendarios Control-M y variables de despliegue. No se incluyen secretos reales en Git.
