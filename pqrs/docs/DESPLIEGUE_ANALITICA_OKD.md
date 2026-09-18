# Despliegue de la analítica en OKD/OpenShift — paso a paso

Guía para el operador. Levanta el **OpenSearch de analítica + OpenSearch Dashboards (OSD) +
reporte SMTP**, sin afectar el OpenSearch **operativo**. Todo vive en `IaC/elk/` y está
registrado en `IaC/elk/kustomization.yaml`. Estrategia acordada: **corte duro** (dev = prd
espejo, no masificado).

## 0. Panorama de recursos

**Pods/recursos que se levantan (nuevos):**
| Recurso | Tipo | Carpeta |
|---|---|---|
| `opensearch-analytics` | Deployment + Service + PVC(30Gi) + SA + RoleBinding | `IaC/elk/opensearch-analytics/00..06` |
| `opensearch-analytics-bootstrap` | Job (crea ISM 30d/90d/365d + index templates, incluidos los de benchmark) | `IaC/elk/opensearch-analytics/05..06` |
| `opensearch-dashboards-analytics` | Deployment + Service + Route + ConfigMap | `IaC/elk/opensearch-analytics/07..10` |
| `opensearch-analytics-bootstrap-alerting` | Job (cuenta SMTP + canal email + monitor de alerta del canario) | `IaC/elk/opensearch-analytics/11..12` |
| `co-pqrs-back-report` | CronJob (imagen propia) | `IaC/backend/co_pqrs_back_report/` + código en `co_pqrs_back_report/` |
| `co-pqrs-benchmark` / `co-pqrs-benchmark-canario` | CronJobs (entregados **suspendidos**); publican `benchmark.*` al mismo exchange | `IaC/backend/co_pqrs_benchmark/` + código en `co_pqrs_benchmark/` |

**Modificado:** `logstash` (imagen OSS con output OpenSearch + salida repuntada a analítica).
**Deprecados (retirar tras validar):** `elasticsearch`, `kibana`.
**Sin tocar:** OpenSearch **operativo** (`IaC/BD/opensearch/`).

---

## 1. Crear el Secret del OpenSearch de analítica (OBLIGATORIO)
No está en el repo por seguridad. Plantilla: `IaC/elk/opensearch-analytics/secret.example.yaml`.

```bash
oc project pqr-genai-dev   # el namespace del entorno

oc create secret generic opensearch-analytics-secret \
  --from-literal=OPENSEARCH_INITIAL_ADMIN_PASSWORD='<PASSWORD_FUERTE>'
```
Requisito OpenSearch 2.13: ≥8 caracteres con mayúscula, minúscula, dígito y símbolo.
Este password lo usan el clúster, Logstash, el OSD de analítica y el CronJob de reporte.

## 2. SMTP — NO requiere secret
El reporte usa el SMTP interno de BBVA (`mailB.bbva.com.co:25`, **sin autenticación**, igual
que `co_pqrs_back_data`). Ya está en el CronJob. No crear secret de SMTP.

## 3. Reporte = módulo de backend `co_pqrs_back_report` (imagen propia)
No existe imagen oficial del reporting-cli, así que el reporte es un **módulo de backend con
su CronJob** (igual que `load_ada_data`): código en `co_pqrs_back_report/` (Dockerfile con
Node + reporting-cli + Chromium) e IaC en `IaC/backend/co_pqrs_back_report/00-cronjob.yaml`.
- **Construir y publicar la imagen** en el registry interno (ver `co_pqrs_back_report/README.md`):
  `docker build -t quay.apps.work.ocp.co.igrupobbva/bbvaco/pqrs_back_report:v1 co_pqrs_back_report && docker push ...`
- En `IaC/backend/co_pqrs_back_report/00-cronjob.yaml` (env inline):
  - `REPORT_RECIPIENTS` — correos destino (editable en el manifiesto, sin rebuild).
  - `DASHBOARD_URL` — reemplazar `<DASHBOARD_ID>` **después** de crear el tablero (paso 7).
  - `REPORT_SUBJECT`, `REPORT_SENDER` — opcionales; SMTP y `OPENSEARCH_PASSWORD` ya vienen.
- Confirmar **tag de Logstash**: `opensearchproject/logstash-oss-with-opensearch-output-plugin:8.9.0`
  (que exista y traiga el input de **RabbitMQ**; si no, instalar `logstash-input-rabbitmq`).

## 4. Encender la emisión de eventos del agente
En `IaC/backend/co_pqrs_back_agent/01-configmap.yaml` asegurar `RABBITMQ_ENABLED=true`
(si está en `false`, el agente no publica y no habrá métricas). Es fire-and-forget: no afecta
la latencia del bot.

## 5. Aplicar / sincronizar

> Esta sección aplica solo la analítica (`IaC/elk`). Para desplegar la versión de llmops, con
> imágenes nuevas de backend y frontend, ver la sección 8d.

Con ArgoCD: sincronizar la app que incluye `IaC/elk`. O manual:
```bash
oc apply -k IaC/elk/
```
Verificar que levantan y quedan **Ready**:
```bash
oc get pods -l app.kubernetes.io/part-of=elk-metrics
oc get pods | grep -E "opensearch-analytics|logstash|report"
```
El OpenSearch **operativo** no debe reiniciarse ni cambiar.

## 6. Validar que el pipeline escribe
1. Confirmar que el Job de bootstrap terminó OK:
   ```bash
   oc logs job/opensearch-analytics-bootstrap
   ```
2. Tener una conversación real con el bot (inicio + turnos + cierre).
3. En OSD (Route `opensearch-dashboards-analytics`, login `admin`) → **Dev Tools**:
   ```
   GET _cat/indices?v
   GET pqr-metrics-*/_search       { "size": 5, "sort": [{ "@timestamp": "desc" }] }
   GET pqr-conversations-*/_search { "size": 5, "sort": [{ "@timestamp": "desc" }] }
   ```
   Deben aparecer documentos `conversation.*` y la traza con `user_content`/`assistant_content`.

## 7. Crear index patterns y tableros en OSD
Seguir [`METRICAS_CAMPOS_Y_VISUALIZACIONES.md`](./METRICAS_CAMPOS_Y_VISUALIZACIONES.md):
1. Index patterns `pqr-metrics-*` y `pqr-conversations-*` (time field `@timestamp`).
2. Tableros **"PQRS Métricas"** y **"PQRS Conversaciones"**.
3. Copiar el **id del tablero** a `DASHBOARD_URL` en el CronJob `co_pqrs_back_report` (paso 3) y re-sincronizar.

## 8. (Opcional) Probar el reporte SMTP
```bash
oc create job --from=cronjob/co-pqrs-back-report prueba-reporte
oc logs job/prueba-reporte
```
Verificar que llega el correo a `REPORT_RECIPIENTS`.

## 8b. Benchmark y canario en el pipeline (índices propios)
El benchmark (`co-pqrs-benchmark`, nocturno) y el canario (`co-pqrs-benchmark-canario`, cada
30 min en horario hábil) publican `benchmark.case` / `benchmark.run` al **mismo** exchange
`pqr.events`; Logstash los escribe en `pqr-benchmark-runs-YYYY.MM` (ISM 365 d). Las
conversaciones sintéticas que abren contra el agente llegan con `source: benchmark` y van a
`pqr-benchmark-conversations-YYYY.MM` (ISM 90 d), **fuera** de `pqr-metrics-*`.
Diccionario y tablero: [`METRICAS_CAMPOS_Y_VISUALIZACIONES.md`](./METRICAS_CAMPOS_Y_VISUALIZACIONES.md) §2, §4.4.

1. En `IaC/backend/co_pqrs_benchmark/`: el configmap `conf-pqrs-benchmark-env` trae
   `RABBITMQ_HOST/PORT/VHOST/EXCHANGE/EXCHANGE_TYPE/PUBLISH_TIMEOUT_SECONDS` (mismos valores que
   el agente) más `ENVIRONMENT` y `CATALOG_VERSION`. Esta última se estampa con
   `scripts/stamp_catalog_version.sh <commit>`, que la fija en el configmap y en el deployment
   del front; con `unknown` las corridas no se pueden enlazar con su ficha de versión. Cada CronJob (`01-cronjob.yaml`,
   `02-cronjob-canario.yaml`) fija en su propio `env` `RABBITMQ_ENABLED=true`, `BENCHMARK_SOURCE`
   y `RABBITMQ_USER/PASSWORD` desde el Secret `rabbitmq-secret` (claves `username`/`password`,
   el mismo que usa el agente). Opcional: `RUN_NAME` (el canario lo fija a
   `canario_rutas_criticas`; el nocturno usa el nombre del dataset).
2. `BENCHMARK_SOURCE`: `canario` en el CronJob canario, `benchmark` en el nocturno (también es
   el default si no se define).
3. El agente desplegado debe ser una versión que emita `source` en `conversation.*`; si no,
   los `benchmark.*` llegan igual pero las conversaciones sintéticas siguen en `pqr-metrics-*`.
4. Los dos CronJobs se entregan **suspendidos** (consumen tokens del LLM). Encender:
   `oc patch cronjob co-pqrs-benchmark-canario -p '{"spec":{"suspend":false}}'`.
   Corrida manual: `oc create job --from=cronjob/co-pqrs-benchmark-canario prueba-canario`.
5. Validar en **Dev Tools**:
   ```
   GET pqr-benchmark-runs-*/_search { "size": 3, "query": { "term": { "event": "benchmark.run" } }, "sort": [{ "@timestamp": "desc" }] }
   GET pqr-benchmark-conversations-*/_count
   GET pqr-metrics-*/_count?q=source:benchmark          # debe ser 0
   ```
6. Index pattern `pqr-benchmark-runs-*` y tablero **"PQRS Benchmark"** (guía §4.1 y §4.4).
   Si RabbitMQ no está disponible, el job loguea el error y termina igual: el NDJSON y el
   resumen se siguen escribiendo como hoy.

### 8b.1 Dataset del benchmark completo y corridas desde el front

- La imagen del benchmark **no** trae `datasets/`. El CronJob `co-pqrs-benchmark` monta el ConfigMap
  `conf-pqrs-benchmark-dataset` (`03-configmap-dataset.yaml`, copia exacta de los datasets
  `doble_cobro_routing.json` y `trx_no_reconocida_routing.json`, una clave por fichero; el test `test_dataset_configmap.py` falla si
  se desincronizan, regenerar con `scripts/build_dataset_configmap.py`) y fija
  `INPUT_JSON=/data/input/doble_cobro_routing.json` y `RUN_NAME=benchmark_doble_cobro`. El lote
  original de MinIO (`input_data/user_inputs.json`) deja de usarse para este CronJob.
- **Corrida bajo demanda sin YAML**: la vista *Benchmark* del front de pruebas. Para que exista en OKD:
  construir el front con `co_pqrs_front_test/Dockerfile.benchmark` **desde la raíz del repo** (copia
  también `co_pqrs_benchmark/`), subirla con un tag nuevo y ajustar `image:` en
  `IaC/frontend/co_pqrs_front_test/01-deployment.yaml`, que ya trae `BENCHMARK_DIR`, `OSD_URL`
  (confirmar el host con `oc get route opensearch-dashboards-analytics`) y las variables de RabbitMQ.

## 8c. Alertas del canario y del benchmark (correo)
Objetos en `IaC/elk/opensearch-analytics/11-configmap-alerting.yaml` y el Job de bootstrap
`12-job-bootstrap-alerting.yaml` (ambos registrados en `IaC/elk/kustomization.yaml`, después del 10).
Usa el **mismo relay SMTP** del reporte (`mailB.bbva.com.co:25`, sin auth): **no requiere
Secret**. Alerting y Notifications vienen en la imagen de OpenSearch 2.13; nada que instalar.

1. Revisar las envs del Job 12 antes de sincronizar:
   - `CANARIO_PRECISION_THRESHOLD` — umbral de `precision_pct`. **Provisional (90), decisión de
     Fabián.**
   - `ALERT_RECIPIENTS` — destinatarios separados por coma (default: el mismo del reporte).
   - `ALERT_LOOKBACK` — solo se mira el último run dentro de esta ventana (default `24h`).
   - `RUTA_CAIDA_LOOKBACK` / `RUTA_CAIDA_MIN_CORRIDAS` — el monitor de *ruta crítica caída* avisa cuando
     una misma ruta del canario falla en al menos N corridas dentro de la ventana (defaults `70m` y `2`,
     es decir dos canarios seguidos), aunque la precisión agregada no baje del umbral.
   - El tercer monitor, *resumen de corrida*, no tiene parámetros: cada 10 minutos mira si terminó una
     corrida del benchmark completo y envía su resumen por el mismo canal.
2. Sincronizar y confirmar: `oc logs job/opensearch-analytics-bootstrap-alerting` → debe
   terminar en `Bootstrap alerting completado.` El Job es idempotente: comprueba si la cuenta
   SMTP, el canal y el monitor existen y los actualiza en vez de duplicarlos. Si OpenSearch
   rechaza alguno de los tres objetos (HTTP distinto de 200/201) el log muestra `FALLO: ...`
   con el cuerpo de la respuesta y el Job termina en error (ArgoCD marca la sincronización
   como fallida): no hay alerta "a medias". En un clúster recién creado, sin monitores, la
   búsqueda de monitores responde 404 y es normal: el Job lo trata como "plugin listo" y crea
   el monitor con `POST`.
3. En OSD: **OpenSearch Plugins → Alerting → Monitors** → `pqr-benchmark-canario-precision`
   Enabled; **Notifications → Channels** → `pqr-benchmark-canario-email` → *Send test message*.
4. Cambiar el umbral o los destinatarios = editar la env del Job 12 y re-sincronizar.
   Detalle del monitor y cómo probar un disparo real: guía de métricas §6.

## 8d. Imágenes de la versión llmops (tags y construcción)

**Estado al 11/09: los manifiestos de dev apuntan a los tags nuevos.** El merge de llmops a dev
conservó primero los tags de dev (commit `65d2a6a`); después los manifiestos pasaron a los tags de
esta tabla. **Las siete imágenes tienen que estar en quay antes de aplicar**: si el manifiesto llega
antes que la imagen, el pod nuevo queda en `ImagePullBackOff`. Los deployments usan la estrategia por
defecto (RollingUpdate), así que el pod anterior sigue atendiendo, pero el despliegue no avanza. Los
CronJobs del benchmark y del canario siguen suspendidos.

| Imagen | Tag anterior | Tag en el manifiesto | Contexto de build | Qué trae |
|---|---|---|---|---|
| `co_pqrs_back_agent` | `1.0.14` | `1.0.15` | `co_pqrs_back_agent/` | campo `source` en los eventos, paso final y autor del texto en la cabecera del benchmark, fix del gate de movimientos (H-17) |
| `co_pqrs_benchmark` | `v8` | `v9` | `co_pqrs_benchmark/` | eventos a RabbitMQ, datasets adversarial, bypass, TNR y grounding, evaluador `leak`/`step`/`invented`/`grounding`, dataset leído del ConfigMap |
| `co_pqrs_front_test` | `v3` | `v5` | **raíz del repo**, `-f co_pqrs_front_test/Dockerfile.benchmark` | vista Benchmark; mismo comando y puerto. `v3` y `v4` quedaron ocupados, `v4` desde la rama de contrato frontal |
| `co_pqrs_back_error_handler` | `v1` | `v2` | `co_pqrs_back_error_handler/` | sanitizador de trazas antes de MinIO (credenciales y PAN con Luhn) |
| `co_pqrs_back_trx_noreconocida` | `test_v1.0.7` | `test_v1.0.8` | `co_pqrs_back_trx_noreconocida/` | contraseña y TSEC nunca en claro, cuerpo del ASO enmascarado; rutas `/customer-address` e `/identity-by-card` que antes servía back_data |
| `co_pqrs_back_data` | `test_v1.0.5` | `test_v1.0.6` | `co_pqrs_back_data/` | volcado E2E enmascarado y cabeceras seguras; **retira** `/trx/account-id` y `/customer_address` (pasaron al trx) |
| `co_pqrs_back_doble_cobro` | `1.0.1` | `1.0.2` | `co_pqrs_back_doble_cobro/` | TSEC solo como huella |

Los siete tags estaban libres el 11/09 en el historial de IaC de todas las ramas dentro de
`pqr-genai/`. Los `v2` a `v5` del error handler que aparecen en junio y julio son del espacio viejo
`bbvaco/`, que es otro repositorio (producción sigue en `bbvaco/`). QA comparte `pqr-genai/` con
otros tags (agente `test_v1.0.6`, back_data `1.0.2`, trx `test_v1.0.6`, front `v1`).

El ConfigMap del trx añade `TRX_IDENTITY_CSV_FILE=data/unifi.csv`: el trx `test_v1.0.8` lee
`DATA_CSV` como ruta, y `unifi` (el nombre que usa back_data) apuntaba a `/app/unifi`, que no existe.
Solo se usa si faltan los datos de Postgres. El pod nuevo lo lee al arrancar, porque el cambio de tag
ya fuerza el reinicio.

### Construir y subir

```bash
R=quay.apps.work.ocp.co.igrupobbva/pqr-genai
# Desde la raíz del repo, en el commit que tiene estos manifiestos
podman build -t $R/co_pqrs_back_agent:1.0.15 co_pqrs_back_agent
podman build -t $R/co_pqrs_benchmark:v9 co_pqrs_benchmark
podman build -f co_pqrs_front_test/Dockerfile.benchmark -t $R/co_pqrs_front_test:v5 .
podman build -t $R/co_pqrs_back_error_handler:v2 co_pqrs_back_error_handler
podman build -t $R/co_pqrs_back_trx_noreconocida:test_v1.0.8 co_pqrs_back_trx_noreconocida
podman build -t $R/co_pqrs_back_data:test_v1.0.6 co_pqrs_back_data
podman build -t $R/co_pqrs_back_doble_cobro:1.0.2 co_pqrs_back_doble_cobro
# podman push $R/<imagen>:<tag> para cada una, y confirmar que las siete existen:
# cada línea debe mostrar un digest (sha256:...), no "manifest unknown"
for t in co_pqrs_back_agent:1.0.15 co_pqrs_benchmark:v9 co_pqrs_front_test:v5 \
  co_pqrs_back_error_handler:v2 co_pqrs_back_trx_noreconocida:test_v1.0.8 \
  co_pqrs_back_data:test_v1.0.6 co_pqrs_back_doble_cobro:1.0.2; do
  printf '%-45s ' "$t"; skopeo inspect --format '{{.Digest}}' docker://$R/$t 2>&1 | head -1; done
```

En la red corporativa, solo `co_pqrs_front_test/Dockerfile.benchmark` declara `ARG BUILD_HTTP_PROXY`:
se le pasa con `--build-arg BUILD_HTTP_PROXY=...`. Los seis Containerfile restantes no declaran proxy.

### Aplicar: el trx antes que back_data

Se aplica **todo** el IaC, no solo la analítica de la sección 5. El back_data nuevo retira
`/trx/account-id`, que el trx anterior todavía consulta; para que no haya un intervalo en el que el
trx viejo pregunte a un back_data que ya no responde, se retiene back_data hasta que el trx nuevo
esté listo:

```bash
NS=pqr-genai-dev
oc -n $NS rollout pause deploy/co-pqrs-back-data
oc apply -k IaC/
oc -n $NS rollout status deploy/co-pqrs-back-trx-noreconocida
oc -n $NS rollout resume deploy/co-pqrs-back-data
oc -n $NS rollout status deploy/co-pqrs-back-data
```

Con ArgoCD (apps de backend, frontend y elk) el orden no se controla: el intervalo dura lo que tarda
el trx en quedar listo, y como las llamadas son fail-open solo afecta a un turno de TNR en ese lapso.
El cambio de tag reinicia trx, back_data y doble cobro, así que leen sus ConfigMaps nuevos; Logstash
solo necesita reinicio si no se reinició después del merge del 11/09.

### Verificar

```bash
oc -n $NS get deploy,cronjob \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{..image}{"\n"}{end}' | grep pqr-genai
python scripts/build_release_card.py   # la ficha debe mostrar los tags de la tabla
```

Para el siguiente cambio de imagen: elegir el tag libre siguiente de la serie (`skopeo inspect` debe
responder "manifest unknown"), construir, subir y solo entonces cambiar el tag en el manifiesto.

**Fuera de esta tabla:** `co_pqrs_back_trx_tantia_export` sigue en `v1` (13/08) y tiene tres commits
posteriores sin construir (CSV y festivos, y la adecuación al doble cobro del 07/09). Su CronJob usa
`imagePullPolicy: IfNotPresent`. Construir un `v2`, que está libre, lo deciden Fabián y Diego.
## 9. Retirar ELK (solo tras validar los tableros y el reporte)
En `IaC/elk/kustomization.yaml` comentar/eliminar los bloques `elastic/*` y `kibana/*`
(hay una nota "RETIRO DE ELK (Fase 6)"). Re-sincronizar. **Rollback:** si algo falla antes de
retirar, revertir la salida de Logstash a ES; ELK sigue desplegado.

---

## 10. (Opcional) Conectar el OpenSearch operativo como data source
El OSD de analítica trae habilitado **Multiple Data Sources** (`data_source.enabled: true` en
`07-configmap-dashboards.yaml`) para poder consultar, desde el mismo OSD, clústeres
OpenSearch **adicionales** (p.ej. el operativo) sin cambiar el clúster por defecto (analítica).
- Habilitar el flag es **inocuo**: no crea conexión ni guarda credenciales hasta registrar el
  data source.
- Para registrarlo: **Dashboards Management → Data Sources → Create data source** → endpoint
  `https://opensearch.pqr-genai-dev.svc.cluster.local:9200`, auth username/password del
  `opensearch-secret` operativo. Ambos son OpenSearch 2.13 (compatibles).
- ⚠️ **Impacto:** solo registrar la conexión = carga despreciable. Pero al crear index-patterns
  o abrir Discover contra ese data source, OSD **enviará queries reales** al operativo (heap
  512MB, sirviendo prod). Usar un **usuario de solo lectura** para acotar el impacto.

## Secretos — resumen
| Secret | ¿Requerido? | Contenido |
|---|---|---|
| `opensearch-analytics-secret` | **Sí** | `OPENSEARCH_INITIAL_ADMIN_PASSWORD` (también lo usa el Job de alerting) |
| SMTP | **No** | Relay interno sin auth (reporte **y** alerta del canario) |
| `rabbitmq-secret` (benchmark y canario) | **Sí** (el mismo Secret del agente) | `username` / `password`, referenciados como `RABBITMQ_USER/PASSWORD` en el `env` de los CronJobs `co-pqrs-benchmark` y `co-pqrs-benchmark-canario` |

## Notas de operación
- **Impacto en el bot:** ninguno. El agente publica a RabbitMQ fire-and-forget; la indexación
  ocurre en el clúster de analítica aislado. Si RabbitMQ/Logstash/OpenSearch-analítica fallan,
  se pierden métricas (best-effort), el bot sigue igual.
- **Completitud (HA):** en dev todo es mono-nodo. Para alto volumen, RabbitMQ en clúster
  (quorum queues) y OpenSearch multi-nodo con réplicas. Confirmar si BBVA ofrece un
  ELK/OpenSearch corporativo antes de operar HA propio.
- **Retención:** 30 días (ISM) en analítica para `pqr-metrics-*` / `pqr-conversations-*`;
  **365 días** para `pqr-benchmark-runs-*` (series largas de precisión) y **90 días** para
  `pqr-benchmark-conversations-*`. El archivo frío de largo plazo sigue en MinIO
  (lo escribe `maintenance`); OSD no lee MinIO directo → reindexar bajo demanda si se necesita
  histórico > 30 días.
- **Por entorno:** el `opensearch-analytics-secret` y los valores del CronJob `co_pqrs_back_report` son
  por-entorno. No cruzar secretos/endpoints/tags entre dev/QA/PRD.
