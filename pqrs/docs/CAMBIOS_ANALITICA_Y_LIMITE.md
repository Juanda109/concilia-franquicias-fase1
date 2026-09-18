# Cambios: analítica (OpenSearch + OSD) y límite diario por caso

> Ámbito actual: **dev** (`feature/PQRSdev`). PRD (`feature/HiddenLeague`) es espejo de
> dev y aún no masificado → se decidió **corte duro** (redirigir todo, sin ventana paralela).
> QA se alinea cuando se decida. Los cambios se dejan **sin commit** (commit/push lo hace el equipo).

## 1. Migración de métricas: de ELK a OpenSearch analítica

**Antes:** Agente → RabbitMQ → Logstash → **Elasticsearch** → **Kibana**.
**Problema:** OpenSearch Dashboards (OSD) no puede leer Elasticsearch 9.x, y la licencia de
Kibana no permite el reporte programado por correo. Además queríamos la **traza de
conversaciones** (pregunta ↔ respuesta) y no afectar el OpenSearch **operativo**.

**Ahora:** Agente → RabbitMQ → **Logstash (imagen OSS con output OpenSearch)** →
**OpenSearch de analítica (clúster nuevo, aislado)** → **OpenSearch Dashboards** → **reporte
SMTP** por CronJob.

```
Agente ──(fire-and-forget)── RabbitMQ "pqr.events"
                                   │
                              Logstash (OSS + opensearch output)
             ┌─────────────────────┼───────────────────────┐
             ▼                      ▼                        ▼
   pqr-conversations-*        pqr-metrics-*            logs-openshift-*
   (traza Q&A)                (métricas)               (logs técnicos)
             └──────── OpenSearch de ANALÍTICA (ISM 30d) ────┘
                                   ▼
                     OpenSearch Dashboards (tableros)
                                   ▼
                     CronJob reporte → PDF → SMTP interno BBVA
```

**Clave — impacto CERO en el bot:** el agente solo **publica un evento a RabbitMQ** de forma
**fire-and-forget, no bloqueante y gateada** (`RABBITMQ_ENABLED`); si RabbitMQ/Logstash/
OpenSearch-analítica están caídos o lentos, el turno del bot no se entera (best-effort). La
indexación ocurre en el **clúster de analítica separado** (pod propio, aislado del operativo).

### Índices (retención ISM 30 días)
- **`pqr-metrics-*`** — métricas (eventos `started/turn/closed/error/cap_reached`).
- **`pqr-conversations-*`** — traza Q&A (evento `trace`, con `user_content`+`assistant_content`, **sin enmascarar**).
- **`logs-openshift-*`** — logs técnicos.

> Detalle de todos los campos: ver [`METRICAS_CAMPOS_Y_VISUALIZACIONES.md`](./METRICAS_CAMPOS_Y_VISUALIZACIONES.md).

### Creación de índices (por qué template y no solo dinámico)
Un Job de bootstrap crea **templates explícitos** (tipos correctos) + la política **ISM 30d**.
Los índices diarios (`pqr-metrics-YYYY.MM.dd`) los crea Logstash en la primera escritura, pero
**casan con el template** → agregaciones (percentiles, sumas, unique counts) funcionan. Con
mapeo puramente dinámico, OpenSearch adivina tipos (números como texto) y rompe las métricas.

## 2. Traza de conversaciones (evento nuevo del agente)
El agente emite, por turno, un segundo evento **`conversation.trace`** con el último par
pregunta/respuesta (`user_content` + `assistant_content`) → índice `pqr-conversations-*`.
Permite auditar qué preguntó el usuario y qué respondió el bot, con time-picker.

## 3. Límite diario de 3 por caso (y por subflujo en centrales)
- Cada uno de los **20 casos** permite **máx. 3 consultas/día** por usuario.
- **Centrales de riesgo** se cuenta **por subflujo** (`centrales_de_riesgo:<subflujo>`),
  no global: 3/día por cada una de sus 3 situaciones (paso `1.4.1`).
- Al topar: se muestra el aviso Sí/No existente ("¿Quieres hacer una consulta diferente?");
  **Sí** → vuelve al inicio ("Genial, por favor cuéntame tu solicitud"); **No** → cierra la
  sesión ("Qué bueno que logramos resolverlo… Hasta pronto"). **Solo se bloquea ese caso.**
- Conteo **por fecha** en la control-table (OpenSearch operativo), reseteo automático a
  medianoche de Bogotá (TZ del pod); sin cron. TTL de registro: 30 días.
- Config: `MAX_DAILY_CATEGORY_INTERACTIONS=3` (dev). `MAX_DAILY_SESSIONS` sigue en 5000.

Implementación (código):
- `workflow_engine.get_limit_key(workflow)` → llave de conteo = el workflow (antes era la
  categoría de grupo compartida).
- `chat_service`: `_maybe_handle_category_cap` usa la llave por caso y **omite centrales** al
  inicio; helper `_maybe_handle_centrales_subflow_cap` cuenta/valida por subflujo en `1.4.1`.

## 4. Métricas nuevas (campos + evento) — preparadas
Se agregaron al índice `pqr-metrics-*`:
- En `conversation.turn`: `llm_used`, `guardrail_blocked`, `routing_outcome`
  (`matched`/`confirmation`/`no_match`/`in_flow`/`guardrail_blocked`/`other`), `subflow_key`.
- En `conversation.closed`: `resolution` (`resolved`/`not_resolved`/`abandoned`/`limit_closed`/`closed`).
- Evento nuevo **`conversation.cap_reached`** (`limit_key`, `limit_label`, `limit_scope` =
  `case`|`centrales_subflow`) → mide cuántos usuarios topan cada casuística por día.

> Significado de cada campo: ver [`METRICAS_CAMPOS_Y_VISUALIZACIONES.md`](./METRICAS_CAMPOS_Y_VISUALIZACIONES.md).

## 5. Pods nuevos / modificados / deprecados

| Pod / recurso | Estado | Dónde |
|---|---|---|
| `opensearch-analytics` (+ bootstrap Job) | **Nuevo** | `IaC/elk/opensearch-analytics/00..06` |
| `opensearch-dashboards-analytics` | **Nuevo** | `IaC/elk/opensearch-analytics/07..10` |
| `co-pqrs-back-report` (CronJob, imagen propia) | **Nuevo** | `IaC/backend/co_pqrs_back_report/` + `co_pqrs_back_report/` |
| `logstash` | **Modificado** (imagen OSS + output → analítica) | `IaC/elk/logstash/` |
| `elasticsearch`, `kibana` | **Deprecados** (retirar tras validar) | `IaC/elk/elastic`, `IaC/elk/kibana` |
| OpenSearch **operativo** | **Sin cambios** | `IaC/BD/opensearch/` |

## 6. Verificación
- Suite del agente: **232 passed** / 9 fallas **pre-existentes** (confirmadas en baseline vía
  `git stash`: ruteo `start.confirmation` ×4, `KeyError 1.4.1.1.1` ×2, trx opción 4,
  `valor_pago` `$ 2.500.000` vs `2500000`, validación 406). **0 regresiones.**

## 7. Pendientes / decisiones
- Secretos por-entorno (ver guía de despliegue): `opensearch-analytics-secret`.
- Confirmar tag de `logstash-oss-with-opensearch-output-plugin`; construir/publicar la imagen
  de `co_pqrs_back_report` (Node+Chromium+reporting-cli); poner `DASHBOARD_ID` real.
- Encender `RABBITMQ_ENABLED=true` para que fluyan las métricas.
