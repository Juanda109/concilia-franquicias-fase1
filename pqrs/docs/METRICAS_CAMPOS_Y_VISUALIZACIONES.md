# Métricas, campos y visualizaciones en OpenSearch Dashboards

Fuente de verdad de **qué medimos** y **cómo construir los tableros** en OpenSearch
Dashboards (OSD), tanto el de **métricas** como el de **conversaciones**.

Las métricas se alimentan de los eventos que el agente emite a RabbitMQ (fire-and-forget) y
que Logstash escribe en el OpenSearch de analítica. Logstash añade `cluster_origen=openshift`
y mapea el `ts` de negocio a `@timestamp`.

El **benchmark** y el **canario** de ruteo (`co_pqrs_benchmark`) publican por el **mismo**
exchange `pqr.events` sus propios eventos (`benchmark.case`, `benchmark.run`; en ellos el
campo de negocio es `timestamp`, que Logstash también mapea a `@timestamp`). Aterrizan en
índices **propios** (§1) y se ven en un tablero propio (§4.4) con alerta (§6). Nada de lo que
ya era visible en `pqr-metrics-*` / `pqr-conversations-*` cambia.

---

## 1. Índices

| Índice | Evento(s) fuente | Contenido | Retención |
|---|---|---|---|
| `pqr-metrics-*` | `conversation.started/turn/closed/error/cap_reached` con `source: live` (o sin `source`) | Métricas (sin contenido de mensajes) | ISM 30 días |
| `pqr-conversations-*` | `conversation.trace` con `source: live` (o sin `source`) | Traza Q&A (pregunta + respuesta) | ISM 30 días |
| `logs-openshift-*` | beats/http | Logs técnicos | ISM 30 días |
| `pqr-benchmark-runs-*` (mensual `YYYY.MM`) | `benchmark.case`, `benchmark.run` | Un doc por **caso** y un doc por **corrida** del benchmark/canario | ISM **365 días** |
| `pqr-benchmark-conversations-*` (mensual `YYYY.MM`) | `conversation.*` con `source: benchmark` | Las conversaciones **sintéticas** que abre el benchmark (métricas **y** traza en el mismo índice) | ISM **90 días** |

Todos los eventos traen `event` (keyword) para distinguir el tipo dentro del mismo índice.

> **Por qué existe `pqr-benchmark-conversations-*`.** Antes, cada corrida del benchmark
> abría decenas de conversaciones contra el agente real y todas caían en `pqr-metrics-*`,
> inflando "conversaciones iniciadas", tokens y no-match con tráfico que no era de clientes.
> Ahora el agente marca esas conversaciones con `source: benchmark` y Logstash las desvía.
> Un agente **viejo** (sin el campo `source`) sigue cayendo exactamente donde caía.

---

## 2. Diccionario de campos

### Comunes (todos los eventos `conversation.*`)
| Campo | Tipo | Para qué sirve |
|---|---|---|
| `event` | keyword | Tipo de evento (`conversation.turn`, etc.). Filtra visualizaciones. |
| `@timestamp` / `ts` | date | Momento del evento (eje de tiempo). |
| `conversation_id` | keyword | Id de la conversación (agrupar turnos de una misma sesión). |
| `user_id` | keyword | Cliente (usuarios únicos DAU/WAU/MAU). |
| `cluster_origen` | keyword | Origen (openshift). |
| `source` | keyword | **Quién abrió la conversación**: `live` (cliente real) o `benchmark` (la abrió el benchmark/canario con la cabecera `X-Benchmark-Mode` en `POST /start`). Se decide una vez en `/start`, se persiste en la conversación y lo heredan **todos** los eventos posteriores (turn, trace, closed, cap_reached, error; incluido el cierre por mantenimiento). Logstash enruta por este campo: `benchmark` → `pqr-benchmark-conversations-*`; `live` o ausente → donde siempre. |

### `conversation.started`
Solo comunes. **Sirve para:** conteo de sesiones iniciadas y usuarios únicos.

### `conversation.turn` (un doc por turno)
| Campo | Tipo | Para qué sirve |
|---|---|---|
| `general_workflow` | keyword | Grupo del caso (Hazlo tú mismo, Guía rápida, PQRs, FAQ, Trx). |
| `workflow` | keyword | **Caso** concreto (uno de los 20). Distribución de uso. |
| `current_step` | keyword | Paso actual del flujo. **Dónde se quedan/abandonan** (drop-off). |
| `status` | keyword | Estado de la conversación en el turno. |
| `message_count` | long | Nº de mensajes acumulados (profundidad de la sesión). |
| `tokens.input/output/total_tokens` | long | Consumo del LLM → **proxy de costo** por turno/día/caso. |
| `duration_ms` | long | **Latencia del turno** (p50/p95/p99). |
| `satisfaction_status` | keyword | Estado de la encuesta (ENTERED/ABANDONED). |
| `satisfaction_result` | boolean | Si el usuario dijo que se resolvió. |
| `llm_usage_status` | keyword | Estado del LLM (ok/fallback…). |
| `llm_fallback_reason` | keyword | Motivo de fallback del LLM. |
| `llm_used` | boolean | **Hubo consumo de LLM** en el turno (tokens>0) vs paso determinista (sin costo). |
| `guardrail_blocked` | boolean | El guardrail **bloqueó** la entrada (fuera de alcance/abuso). |
| `routing_outcome` | keyword | Desenlace del ruteo: `matched` / `confirmation` / `no_match` / `in_flow` / `guardrail_blocked` / `other`. **Comprensión y tasa de no-match.** |
| `subflow_key` | keyword | Subflujo elegido (solo centrales): hace legible el `current_step` `1.4.1.x`. |

### `conversation.closed` (un doc por cierre)
| Campo | Tipo | Para qué sirve |
|---|---|---|
| `duration_total_ms` | long | Duración total de la conversación. |
| `resolution` | keyword | Cómo cerró: `resolved` / `not_resolved` / `abandoned` / `limit_closed` / `closed`. **Tasa de resolución/contención.** |
| (+ satisfaction_*, workflow, message_count) | — | Igual que en turn. |

### `conversation.error`
| Campo | Tipo | Para qué sirve |
|---|---|---|
| `error_type` | keyword | Tipo de error (p.ej. `TimeoutError`). **Tasa de errores y timeouts.** |
| `error_message` | text | Mensaje (diagnóstico). |

### `conversation.cap_reached` (nuevo — mide el límite diario)
| Campo | Tipo | Para qué sirve |
|---|---|---|
| `limit_key` | keyword | Caso o subflujo topado (`impuesto_4x1000`, `centrales_de_riesgo:consulta_sin_permiso`). |
| `limit_label` | keyword | Etiqueta legible del caso/subflujo. |
| `limit_scope` | keyword | `case` (uno de los 20) o `centrales_subflow`. |
| `workflow` | keyword | Workflow en curso al topar. |

### `conversation.trace` → `pqr-conversations-*`
| Campo | Tipo | Para qué sirve |
|---|---|---|
| `user_content` | text (+ `.raw` keyword) | **Pregunta del usuario** (búsqueda full-text; `.raw` para agregación exacta). |
| `assistant_content` | text | **Respuesta del bot**. |
| (+ workflow, current_step, satisfaction_*, tokens, duration_ms) | — | Contexto del turno. |

### Eventos del benchmark → `pqr-benchmark-runs-*`

Los emite `co_pqrs_benchmark` (Job nocturno o CronJob canario) al terminar cada caso y cada
corrida. Son el mismo dato que el NDJSON y el resumen `.txt` que el job ya escribía, puestos en
el pipeline. Publicación fire-and-forget: si RabbitMQ no está, el job loguea y sigue; el
NDJSON y el resumen se escriben igual.

#### Comunes a `benchmark.case` y `benchmark.run`
| Campo | Tipo | Para qué sirve |
|---|---|---|
| `event` | keyword | `benchmark.case` (un doc por caso) o `benchmark.run` (un doc por corrida). **Siempre filtrar por él**: los dos tipos comparten índice. |
| `timestamp` / `@timestamp` | date | Momento del evento (ISO UTC). Logstash copia `timestamp` a `@timestamp`, que es el *time field* del index pattern. |
| `source` | keyword | `benchmark` (corrida completa, dataset grande) o `canario` (8 casos dorados cada 30 min). Viene de la env `BENCHMARK_SOURCE` del job; default `benchmark`. **La alerta (§6) filtra `canario`.** |
| `run_name` | keyword | Nombre de la corrida: env `RUN_NAME` o, si no, el nombre del dataset. |
| `run_id` | keyword | `run_name + '_' + inicio de la corrida` en formato `YYYYmmddTHHMMSSZ`. **Une los casos con su corrida** y es la unidad natural del eje X "por corrida". |
| `catalog_version` | keyword | Versión del catálogo de ruteo (`general.yml`) contra la que se corrió (env `CATALOG_VERSION`, default `unknown`). Permite comparar precisión antes/después de un cambio de catálogo. |
| `environment` | keyword | `local` / `dev` / `qa` / `prd` (env `ENVIRONMENT`, default `local`). |
| `flow` | keyword | Nombre del dataset sin extensión (`doble_cobro_routing`, `canario_rutas_criticas`). |
| `llm_model` | keyword | Modelo LLM que respondió el ruteo (lo reporta el agente en `X-Benchmark-Data`). |
| `cluster_origen` | keyword | Lo añade Logstash (`openshift`). |

#### `benchmark.case` (un doc por caso del dataset)
| Campo | Tipo | Para qué sirve |
|---|---|---|
| `case_index` | long | Posición del caso en el dataset (1-based, la misma que muestra el log `[n/total]`). Identifica el caso dentro de una `run_id`. |
| `user_input` | text (+ `.raw`) | Primer mensaje enviado al agente (la frase del dataset). `.raw` para agrupar por frase exacta. |
| `note` | text (+ `.raw`) | Campo `nota` del dataset: por qué existe el caso / qué frontera prueba. |
| `category` | keyword | Categoría del caso en datasets adversariales / de bypass (`inyeccion_directa`, `fuga_informacion`, `bypass_txnr`…). Vacío en los datasets de ruteo. |
| `final_step` | keyword | Paso del flujo en el que terminó la conversación (lo reporta el agente en `X-Benchmark-Data`). Es lo que evalúa `forbid_steps`: un caso de bypass falla si termina en un terminal de abono o bloqueo. |
| `workflow_expect` | keyword | Workflow esperado (`doble_cobro`, `pqrs_no_ruteo`, `""` si se espera ninguno). **Tipología del caso**: el eje de "fallos por tipología". |
| `outcome_expect` | keyword | `routing_outcome` esperado (`matched`, `no_match`, `guardrail_blocked`…) o `""` si no se exige. |
| `workflow_result` | keyword | Workflow **final** en el que quedó la conversación. |
| `workflow_llm` | keyword | Workflow que propuso el LLM antes de confirmaciones/aclaraciones. Distinto de `workflow_result` cuando hubo confirmación o reformulación. |
| `routing_outcome` | keyword | Desenlace del último turno (`matched`, `confirmation`, `no_match`, `guardrail_blocked`, `other`). |
| `confidence` | keyword | Confianza declarada por el router (`high` / `medium` / `low`). |
| `acierto` | boolean | **La misma evaluación con la que el job calcula su precisión**: `workflow_result == workflow_expect` y, si `outcome_expect` no está vacío, `routing_outcome == outcome_expect`. |
| `fail_kind` | keyword | `workflow` (fue a otro flujo), `outcome` (flujo correcto, desenlace distinto) o `null` si acertó. Nuevos valores adversariales: `leak` (la respuesta contenía algo prohibido por `must_not_contain`) y `step` (terminó en un paso de `forbid_steps`). Grounding: `invented` (afirmó algo que no está en su fuente, `must_not_invent`) y `grounding` (omitió lo que la fuente exigía, `must_contain`). |
| `response_source` | keyword | Quién redactó el último texto que vio el cliente: `model` (el LLM), vacío (texto aprobado del YAML) o `local_fallback_*` (el modelo no estaba disponible). Lo reporta el agente en `X-Benchmark-Data`; el tablero de grounding lo usa para acreditar o no un cierre al modelo. |
| `resolution` | keyword | `resolved` / `unresolved_max_turns` / `unresolved_needs_follow_up` / `unresolved_no_header`. Los `unresolved_*` **no cuentan** en la precisión. |
| `turns` | long | Turnos que necesitó el caso (1 = ruteó a la primera). |
| `llm_token_input` / `llm_token_output` / `llm_token_cached` | long | Tokens del caso (suma de sus turnos). Costo por caso. |
| `llm_token_cache_hit_pct` | float | % de tokens de entrada servidos desde caché de prompt. |
| `routing_time_total_s` | float | Segundos que el **agente** tardó en rutear (suma de turnos; lo reporta el agente en ms y el job lo convierte). |
| `user_time_total_s` | float | Segundos de ida y vuelta vistos por el **cliente HTTP** (e2e, incluye red y cola). |
| `conversation_id` | keyword | Conversación sintética que abrió el caso. Cruza con `pqr-benchmark-conversations-*` para leer la traza completa. |

#### `benchmark.run` (un doc por corrida)
| Campo | Tipo | Para qué sirve |
|---|---|---|
| `cases_total` | long | Casos del dataset. |
| `cases_ok` | long | Casos con `acierto: true`. |
| `cases_unresolved` | long | Casos sin resolver (turnos agotados o falta follow-up). No entran en la precisión. |
| `precision_pct` | float | **La métrica**: `cases_ok / evaluados * 100` (evaluados = total − sin resolver). Es el número que aparece en el resumen `.txt` y el que vigila la alerta. |
| `precision_workflow_pct` | float | Precisión mirando **solo** el workflow (ignora `outcome_expect`). Separa "fue al flujo equivocado" de "fue al flujo correcto por otro camino". |
| `routing_p50_s` / `routing_p95_s` | float | Percentiles del tiempo de ruteo por caso (`routing_time_total_s`). |
| `e2e_p50_s` / `e2e_p95_s` | float | Percentiles del tiempo e2e por caso (`user_time_total_s`). |
| `tokens_input_total` / `tokens_output_total` | long | Tokens de toda la corrida. Costo por corrida. |
| `cache_hit_pct_avg` | float | % de tokens de entrada servidos desde caché sobre **toda la corrida** (`tokens cacheados / tokens de entrada * 100`, no el promedio de los casos). |
| `duration_s` | float | Duración de la corrida completa (segundos de reloj). |

---

## 3. Catálogo de métricas (qué se puede extraer)

| Categoría | Métrica | Cómo |
|---|---|---|
| Volumen | Conversaciones iniciadas | count `event: conversation.started` por `@timestamp` |
| Volumen | **Usuarios únicos** (DAU/WAU/MAU) | unique count `user_id` |
| Volumen | Turnos totales / por conversación | count `conversation.turn` / group by `conversation_id` |
| Flujos | Distribución por caso | count `conversation.turn` split by `workflow` |
| Flujos | **Drop-off** por paso | count split by `current_step` |
| Comprensión | Tasa de **no-match** | count `routing_outcome: no_match` / total |
| Comprensión | Confirmaciones por ambigüedad | count `routing_outcome: confirmation` |
| Guardrail | Entradas bloqueadas | count `guardrail_blocked: true` |
| Satisfacción | **CSAT** | `conversation.closed` split by `satisfaction_result` |
| Satisfacción | Abandono de encuesta | count `satisfaction_status: ABANDONED` |
| Resolución | Tasa de resolución | `conversation.closed` split by `resolution` |
| Latencia | **p50/p95/p99 del turno** | percentiles de `duration_ms` (`conversation.turn`) |
| Latencia | Duración de conversación | p95 de `duration_total_ms` (`conversation.closed`) |
| Costo | Tokens por día / por caso | sum `tokens.total_tokens` split by `@timestamp` / `workflow` |
| Costo | % turnos con LLM | count `llm_used: true` / total |
| Fiabilidad | Errores por tipo | count `conversation.error` split by `error_type` |
| Fiabilidad | Timeouts | count `error_type: TimeoutError` |
| **Límite** | Topes alcanzados por caso | count `conversation.cap_reached` split by `limit_key` |
| **Límite** | Topes de subflujos centrales | `cap_reached` filtro `limit_scope: centrales_subflow` split by `limit_key` |
| **Benchmark** | Precisión por corrida | `benchmark.run` → max `precision_pct` por `run_id` / por `@timestamp` (índice `pqr-benchmark-runs-*`) |
| **Benchmark** | Fallos por tipología | `benchmark.case` filtro `acierto: false` split by `workflow_expect` (y `fail_kind`) |
| **Benchmark** | Latencia p95 de ruteo / e2e | `benchmark.run` → `routing_p95_s` / `e2e_p95_s`; o percentiles de `routing_time_total_s` / `user_time_total_s` en `benchmark.case` |
| **Benchmark** | Tokens por caso | `benchmark.case` → avg `llm_token_input` + `llm_token_output` |
| **Benchmark** | Canario bajo umbral | último `benchmark.run` con `source: canario` y `precision_pct < umbral` → alerta (§6) |

> Las métricas de conversación (volumen, no-match, CSAT…) se calculan **solo** sobre
> `pqr-metrics-*`; el tráfico del benchmark ya no está ahí. Si quieres ver el comportamiento
> del agente en las conversaciones sintéticas, usa el index pattern
> `pqr-benchmark-conversations-*` con las mismas recetas de §4.2.

---

## 4. Cómo crear las visualizaciones en OSD

### 4.1 Index patterns (una sola vez)
> En OpenSearch Dashboards **NO existe "Stack Management" ni "Lens"** (eso es Kibana). Los
> nombres correctos son **Dashboards Management** y **Visualize/VisBuilder**.

1. Abrir la Route de `opensearch-dashboards-analytics` (login `admin`).
2. Menú lateral (☰) → **Management → Dashboards Management → Index patterns**.
3. **Create index pattern** → nombre **`pqr-metrics-*`** (OSD agrega el `*`) → **Next step** →
   elegir **`@timestamp`** como *time field* → **Create index pattern**.
4. Repetir para **`pqr-conversations-*`** (time field `@timestamp`).
5. Para el tablero de benchmark (§4.4), repetir para **`pqr-benchmark-runs-*`** y, si se
   quiere auditar las conversaciones sintéticas, **`pqr-benchmark-conversations-*`** (ambos
   con time field `@timestamp`). Solo existen después de la **primera corrida** del benchmark
   o del canario con `RABBITMQ_ENABLED=true`.

**Si NO ves "Index patterns":**
- Debe estar dentro de **Dashboards Management** (sub-app), no directo bajo "Management".
- Requiere permisos: rol tipo `kibana_user` + `kibana_all_write` en el tenant. Con solo lectura
  puedes ver pero no crear.
- **Primero debe existir el índice**: si Logstash aún no ha escrito nada, no habrá índices que
  casen. Verifica en **Dev Tools** → `GET _cat/indices?v` que existan `pqr-metrics-*` /
  `pqr-conversations-*`. Si no existen, aún no ha llegado data (ver §5).
- Con **Multiple Data Sources** activado, al crear el index pattern primero te pide **elegir el
  data source** (selecciona el clúster local/analítica).

### 4.2 Tablero de MÉTRICAS
1. Menú lateral → **OpenSearch Dashboards → Visualize** → **Create visualization**.
2. En el diálogo **New Visualization** elige el tipo (no hay Lens). Opciones:
   - **VisBuilder** — arrastrar y soltar (lo más cómodo para explorar).
   - O una **aggregation-based** clásica: **Line, Bar, Pie, Data table, Metric**, etc.
3. Si lo pide, elige el **source** = index pattern `pqr-metrics-*`.
4. Configura **metrics** (eje Y) y **buckets** (eje X / split). Una visualización por fila del
   catálogo (§3). Ejemplos concretos:
   - **Conversaciones iniciadas** — Line. Filtro `event: conversation.started`. Bucket X: **Date Histogram** `@timestamp`. Metric Y: **Count**.
   - **Latencia p95 del turno** — Line. Filtro `event: conversation.turn`. Metric Y: **Percentiles** de `duration_ms` (95).
   - **Distribución por caso** — Bar/Pie. Filtro `event: conversation.turn`. Bucket: **Terms** `workflow`.
   - **Drop-off por paso** — Bar. Filtro `event: conversation.turn`. Bucket: **Terms** `current_step`.
   - **No-match** — Metric. Filtro `event: conversation.turn and routing_outcome: no_match`. Metric: **Count**.
   - **CSAT** — Pie. Filtro `event: conversation.closed`. Bucket: **Terms** `satisfaction_result`.
   - **Resolución** — Bar. Filtro `event: conversation.closed`. Bucket: **Terms** `resolution`.
   - **Tokens por día** — Bar. Filtro `event: conversation.turn`. Metric Y: **Sum** `tokens.total_tokens`; Bucket X: **Date Histogram** `@timestamp`.
   - **Errores por tipo** — Bar. Filtro `event: conversation.error`. Bucket: **Terms** `error_type`.
   - **Topes por caso** — Bar. Filtro `event: conversation.cap_reached`. Bucket: **Terms** `limit_key`.
   - **Usuarios únicos/día** — Bar. Filtro `event: conversation.started`. Metric Y: **Unique Count (Cardinality)** `user_id`; Bucket X: **Date Histogram** `@timestamp`.
   - **Save** cada una (arriba a la derecha) con un título.
5. Menú → **OpenSearch Dashboards → Dashboards** → **Create** → **Add / From library** → agregar
   las visualizaciones guardadas → **Save** como **"PQRS Métricas"**.
6. Usa el **time picker** (p.ej. "Últimos 7 días") y **Auto-refresh** para tiempo real.

### 4.3 Tablero de CONVERSACIONES (traza Q&A)
1. **OpenSearch Dashboards → Discover**, elige el index pattern `pqr-conversations-*`: agrega
   columnas `user_id`, `workflow`, `current_step`, `user_content`, `assistant_content`. Sirve
   para auditar y buscar (full-text sobre `user_content`).
2. Para el dashboard, crea una visualización **Data table** (Visualize → Create visualization →
   Data table), source `pqr-conversations-*`:
   - Metric: **Count** (o usa una **Terms** por `conversation_id`).
   - Buckets/columnas: **Terms** de `workflow`, `current_step`, `user_content.raw`,
     `assistant_content` (según permita la versión).
3. Filtros útiles: por `workflow`, por `user_id`, por rango de fechas (time picker).
4. Búsqueda (barra DQL): `user_content: "4x1000"` (full-text) para ver todas las preguntas de
   un tema; usa `user_content.raw` para agregación exacta.
5. Guarda el dashboard como **"PQRS Conversaciones"** con time-picker.

> Nota: las visualizaciones no se versionan bien como NDJSON (frágil entre versiones de OSD);
> se construyen con esta guía. Los **index patterns** sí pueden exportarse/importarse en
> **Management → Dashboards Management → Saved objects**.

### 4.4 Tablero de BENCHMARK (precisión del ruteo en el tiempo)

> **Atajo: tableros importables (recomendado).** `co_pqrs_benchmark/scripts/build_dashboards.py`
> genera dos ficheros de objetos guardados en `IaC/elk/opensearch-analytics/dashboards/`:
>
> | Fichero | Tablero | Responde |
> |---|---|---|
> | `pqr-benchmark-dashboard.ndjson` | **PQRS · Benchmark de ruteo** | ¿Esta versión del catálogo rutea bien? (28 casos, a demanda / nocturno) |
> | `pqr-canario-dashboard.ndjson` | **PQRS · Canario de ruteo** | ¿El agente está bien **ahora**? (8 rutas críticas cada 30 min) |
> | `pqr-adversarial-dashboard.ndjson` | **PQRS · Adversarial y bypass** | ¿Resiste inyección, manipulación, fuga y bypass de gates? (`source=adversarial`; objetivo cero fallos) |
>
> Ambos comparten los index patterns (`pqr-benchmark-runs-*`, `pqr-benchmark-conversations-*`) y las
> búsquedas guardadas. Importar en el tenant **Global** (o desde *Dashboards Management → Saved objects → Import*):
>
> ```bash
> for f in pqr-benchmark-dashboard pqr-canario-dashboard; do
>   curl -u admin:$OSD_PASS -H 'osd-xsrf: true' -H 'securitytenant: global' -X POST \
>     "$OSD_URL/api/saved_objects/_import?overwrite=true" \
>     -F file=@IaC/elk/opensearch-analytics/dashboards/$f.ndjson
> done
> ```
>
> El generador consulta un Dashboards vivo (`--osd-url`, default `http://localhost:5601`) para embeber la
> lista de campos de cada patrón en el fichero, así el import deja los index patterns completos, con los
> formatos de enlace y con el **campo calculado `acierto_num`** (1/0 sobre el booleano `acierto`; Dashboards
> no admite Min/Max sobre booleanos y la rejilla del canario agrega sobre este). Si se regenera sin
> Dashboards (`--no-fields`), tras importar hay que pulsar **refrescar campos** en *Index patterns* (la UI
> conserva formatos y campos calculados; por API con `PUT` hay que reenviar `fieldFormatMap` y `fields`).
> Validado el 8-sep-2026 en OSD 2.9 local con corridas reales del benchmark y del canario.
>
> **Lanzar una corrida sin YAML.** El front de pruebas (`co_pqrs_front_test`, vista *Benchmark*) corre el
> dataset elegido contra el agente, con nombre de corrida, publica los eventos al mismo pipeline y al
> terminar muestra el resumen y el enlace al tablero filtrado por `run_name`. En OKD requiere la imagen
> construida con `Dockerfile.benchmark` y las variables `BENCHMARK_DIR`, `OSD_URL` y `RABBITMQ_*` del
> deployment (`IaC/frontend/co_pqrs_front_test`).
>
> **Desglosar una corrida hasta el chat (lo que pide negocio).** Los tableros están encadenados:
> 1. En *Últimas corridas*, **clic en la corrida** → abre la búsqueda guardada *casos de la corrida*
>    filtrada por ese `run_id`: un caso por fila con lo que dijo el cliente (`user_input`), a dónde debía
>    ir (`workflow_expect`), a dónde fue (`workflow_result`), qué propuso el LLM, la confianza y la nota.
> 2. En cualquier fila, **clic en `conversation_id`** → abre la conversación completa, turno a turno
>    (`user_content` / `assistant_content`, paso del flujo, duración), desde `pqr-benchmark-conversations-*`.
> 3. Para aislar una corrida en todos los paneles a la vez: barra de búsqueda `run_id: "<id>"`;
>    para una versión del catálogo: `catalog_version: <sha>`.
>
> **Estrategia de nombres.** El título de cada panel es la *pregunta* que responde más el indicador
> ("Precisión por corrida · ¿cuánto acierta el ruteo?"); las series llevan etiqueta en español y el
> nombre técnico del campo va en la descripción del panel (icono ⓘ). Los tableros se llaman
> `PQRS · <qué> de ruteo` para que se ordenen juntos en la galería.
>
> **Estrategia de colores.** Un color por *concepto*, fijo en todos los paneles y tableros: azul para la
> medida principal (precisión total, ruteo p95, tokens de entrada), aqua/naranja para la secundaria
> (precisión de flujo, extremo a extremo, tokens de salida); **cada workflow destino tiene su color
> fijo** (`WORKFLOW_COLORS` en el generador: `trx_no_reconocida` naranja, `doble_cobro` azul,
> `pqrs_no_ruteo` violeta, `puntos_y_promociones` amarillo, …) para que se reconozca igual en el panel de
> fallos del benchmark y en el del canario; y los colores de **estado** (verde acertó / rojo falló,
> umbral rojo discontinuo) no se reutilizan para series. Paleta de referencia validada para daltonismo
> en pares adyacentes (el generador la documenta). Los paneles del canario usan la rejilla
> `min(acierto)` por ruta × media hora: verde 1 / rojo 0.
>
> **Pipeline completo en local (RabbitMQ + Logstash).** `co_pqrs_back_opensearch/docker-compose.analytics.yml`
> levanta RabbitMQ y Logstash con la **misma** imagen y la **misma** configuración del IaC
> (`render_logstash_local.py` la extrae del ConfigMap; solo cambia el host del OpenSearch de salida).
> Con `LOCAL_RABBITMQ_ENABLED=true python scripts/run_local.py up` el agente local publica sus eventos y
> el benchmark, con `RABBITMQ_ENABLED=true RABBITMQ_HOST=127.0.0.1`, publica los suyos. Verificado el
> 8-sep-2026: `logstash --config.test_and_exit` → *Configuration OK*; una conversación sin cabecera cae en
> `pqr-metrics-*` / `pqr-conversations-*` con `source=live`; las 28 conversaciones sintéticas del benchmark
> caen en `pqr-benchmark-conversations-*` y sus 29 eventos en `pqr-benchmark-runs-*`.

Responde "¿el ruteo sigue acertando lo mismo que ayer / que antes de tocar el catálogo?".
Source de todas las visualizaciones: index pattern **`pqr-benchmark-runs-*`** (§4.1 paso 5).
Cada corrida deja **un** `benchmark.run` y **N** `benchmark.case`; por eso todas las
visualizaciones empiezan por un filtro `event: ...` en la barra DQL.

Convención de filtros por origen: `source: canario` (8 casos, cada 30 min, serie densa) y
`source: benchmark` (dataset completo, nocturno, serie de un punto por día). **No los mezcles
en una misma línea**: el canario tiene 8 casos y su precisión salta de 12,5 en 12,5.

1. **Precisión por corrida en el tiempo** — tipo **Line**.
   - Barra DQL: `event: benchmark.run and source: benchmark` (duplicar después la
     visualización con `source: canario`).
   - Metrics (Y): **Max** de `precision_pct` (hay un solo `benchmark.run` por corrida, así que
     Max = el valor de la corrida; **Average** daría lo mismo pero Max no engaña si un día hay
     dos corridas).
   - Buckets (X): **Date Histogram** sobre `@timestamp`; intervalo **Daily** para
     `benchmark`, **30 minutes** para `canario`. Si prefieres un punto por corrida exacto:
     X = **Terms** sobre `run_id`, size 50, *Order by* → **Custom metric** → Max `@timestamp`
     ascendente.
   - Opcional: **Split series** → **Terms** sobre `flow` (una línea por dataset) o sobre
     `catalog_version` (ver el salto al cambiar el catálogo).
   - Metrics & axes → eje Y: *Custom extents* 0–100 para que un 96 no parezca un pico.
   - Añade una segunda métrica **Max** de `precision_workflow_pct` para ver cuánto del fallo
     es "flujo equivocado" y cuánto "desenlace distinto".
   - **Save** como *Benchmark · precisión por corrida (benchmark)* y *(canario)*.

2. **Fallos por tipología** — tipo **Vertical Bar**.
   - Barra DQL: `event: benchmark.case and acierto: false` (añade `and source: benchmark` o
     `canario` según el tablero).
   - Metrics (Y): **Count**.
   - Buckets (X): **Terms** sobre `workflow_expect`, size 25, order by Count desc. Cada barra
     es "cuántos casos que **debían** ir a X no fueron".
   - **Split series** → **Terms** sobre `fail_kind` (`workflow` vs `outcome`), modo *stacked*.
   - Para saber **a dónde** se fueron: segunda visualización idéntica con X = `workflow_expect`
     y Split series = **Terms** `workflow_result` (matriz esperado → obtenido).
   - Para leer los casos concretos: **Discover** sobre `pqr-benchmark-runs-*`, misma DQL,
     columnas `run_id`, `workflow_expect`, `workflow_result`, `workflow_llm`, `routing_outcome`,
     `user_input`, `note`. Guarda la búsqueda como *Benchmark · casos fallidos* y añádela al
     tablero (una saved search se agrega como panel igual que una visualización).

3. **Latencia p95 de ruteo y e2e** — tipo **Line**.
   - Barra DQL: `event: benchmark.run and source: benchmark` (o `canario`).
   - Metrics (Y): **Max** `routing_p95_s` y, con **Add metric**, **Max** `e2e_p95_s` (dos
     líneas). Estos p95 los calcula el job por corrida sobre sus casos, igual que en el
     resumen `.txt`; así el tablero dice lo mismo que el log del pod.
   - Buckets (X): **Date Histogram** sobre `@timestamp` (Daily / 30 minutes) o **Terms**
     `run_id` como en el punto 1.
   - Alternativa por caso (útil para un rango de varias corridas): DQL `event: benchmark.case`,
     Metrics **Percentiles** (95) sobre `routing_time_total_s` y sobre `user_time_total_s`.
   - Lectura: `e2e` − `routing` ≈ red + cola + guardrails. Si `e2e_p95_s` se acerca a 9 s el
     agente empezará a responder `204` (turno diferido; ver `ARQUITECTURA_BACK_AGENT.md`).

4. **Tokens por caso** — tipo **Vertical Bar**.
   - Barra DQL: `event: benchmark.case`.
   - Metrics (Y): **Average** `llm_token_input` y **Average** `llm_token_output` (dos series,
     stacked). Si quieres el total de la corrida, usa **Sum** o mira `tokens_input_total` en
     `benchmark.run`.
   - Buckets (X): **Date Histogram** `@timestamp` (una barra por corrida) o **Terms**
     `workflow_expect` (qué tipologías cuestan más porque piden confirmación/aclaración).
   - Añade **Average** `llm_token_cache_hit_pct` como métrica aparte (tipo **Metric**) para
     ver si el caché de prompt está funcionando (hoy 0 %; el prompt de ruteo son ~8 k tokens
     de entrada por turno, es la mayor palanca de costo).

5. **Últimas corridas** — tipo **Data table**.
   - Barra DQL: `event: benchmark.run`.
   - Buckets → **Split rows** → **Terms** sobre `run_id`, size 20, *Order by* → **Custom
     metric** → **Max** `@timestamp`, **Descending** (la más reciente arriba).
   - Añade más **Split rows** con **Terms** (size 1) sobre `source`, `flow`,
     `catalog_version`, `environment`, `llm_model`: aparecen como columnas.
   - Metrics: **Max** de `precision_pct`, `precision_workflow_pct`, `cases_total`, `cases_ok`,
     `cases_unresolved`, `routing_p95_s`, `e2e_p95_s`, `tokens_input_total`, `duration_s`.
   - Alternativa más simple: **Discover** sobre `pqr-benchmark-runs-*` con la misma DQL,
     ordenado por `@timestamp` desc y esas columnas; guardar como *Benchmark · últimas
     corridas* y agregarla al tablero.

6. Menú → **Dashboards → Create** → **Add / From library** → agregar las cinco (o siete)
   visualizaciones → **Save** como **"PQRS Benchmark"**. Time picker recomendado: *Last 30
   days* para `benchmark`, *Last 24 hours* para `canario`. Si quieres dos tableros, guarda
   **"PQRS Benchmark"** y **"PQRS Canario"** con los filtros de `source` fijados en cada
   visualización.

7. **Conversaciones sintéticas.** Para ver qué contestó el agente en un caso fallido: toma su
   `conversation_id` del `benchmark.case` y en **Discover** sobre
   `pqr-benchmark-conversations-*` filtra `conversation_id: "<id>"`; verás los `conversation.turn`
   y `conversation.trace` (con `user_content` / `assistant_content`) de esa conversación.

---

## 5. Requisitos para que fluyan los datos
- `RABBITMQ_ENABLED=true` en el configmap del agente (si está en `false`, no hay eventos).
- El Job de bootstrap (`opensearch-analytics-bootstrap`) debe haber creado templates + ISM.
- Verificación rápida en **Dev Tools**: `GET _cat/indices` y
  `GET pqr-metrics-*/_search { "size": 5, "sort": [{ "@timestamp": "desc" }] }`.
- Para el **benchmark/canario**: `RABBITMQ_ENABLED=true` en el `env` de cada CronJob
  (`01-cronjob.yaml`, `02-cronjob-canario.yaml`; default `false`), con `RABBITMQ_HOST/PORT/VHOST/
  EXCHANGE/EXCHANGE_TYPE` en el configmap `conf-pqrs-benchmark-env` y `RABBITMQ_USER/PASSWORD`
  desde el Secret `rabbitmq-secret` (los mismos valores que el agente), y `BENCHMARK_SOURCE=canario`
  en el CronJob canario (`benchmark` en el nocturno). Opcionales: `RUN_NAME`, `CATALOG_VERSION`,
  `ENVIRONMENT`. El agente debe ser una versión que emita `source` (si no, las conversaciones
  sintéticas seguirán cayendo en `pqr-metrics-*`, aunque los `benchmark.*` sí lleguen a
  `pqr-benchmark-runs-*`).
- Verificación del benchmark:
  `GET pqr-benchmark-runs-*/_search { "size": 3, "query": { "term": { "event": "benchmark.run" } }, "sort": [{ "@timestamp": "desc" }] }`
  y `GET pqr-benchmark-conversations-*/_count` (debe crecer tras una corrida, y
  `GET pqr-metrics-*/_count?q=source:benchmark` debe devolver **0**).
- Para la **alerta** (§6): el Job `opensearch-analytics-bootstrap-alerting` debe haber
  terminado OK (`oc logs job/opensearch-analytics-bootstrap-alerting`).

---

## 6. Alertas: canario bajo umbral, ruta crítica caída y resumen de corrida

**Qué vigila.** Cada 30 min, el **último** `benchmark.run` con `source: canario` en
`pqr-benchmark-runs-*` (dentro de una ventana de 24 h). Si su `precision_pct` está por debajo
del umbral, envía un correo. Con 8 casos dorados, un fallo = 87,5 % → dispara; cero fallos =
100 % → no dispara. Nada más: latencia y tokens se **miran** en el tablero, no alertan.

> **El umbral es PROVISIONAL (90 %) y lo decide Fabián.** Vive en la env
> `CANARIO_PRECISION_THRESHOLD` del Job `12-job-bootstrap-alerting.yaml`, no en el JSON del
> monitor. Cambiarlo = editar la env y re-sincronizar; el Job actualiza el monitor existente.

**Dónde vive.** `IaC/elk/opensearch-analytics/`:
| Fichero | Contenido |
|---|---|
| `11-configmap-alerting.yaml` | Cinco JSON: cuenta SMTP (`pqr-analytics-smtp`), canal email (`pqr-benchmark-canario-email`) y tres monitores: `pqr-benchmark-canario-precision` (query-level: última corrida del canario < umbral), `pqr-benchmark-canario-ruta-caida` (bucket-level: una misma ruta con fallo en ≥ N corridas de la ventana, aunque el agregado siga alto; un correo por ruta con throttle de 60 min) y `pqr-benchmark-resumen-corrida` (query-level cada 10 min: resumen por correo de cada corrida del benchmark completo, la respuesta automática a negocio). Marcadores `__PRECISION_THRESHOLD__`, `__ALERT_LOOKBACK__`, `__RUTA_CAIDA_LOOKBACK__`, `__RUTA_CAIDA_MIN_CORRIDAS__`, `__ALERT_RECIPIENTS_JSON__`. |
| `12-job-bootstrap-alerting.yaml` | Job PostSync (curl, como el 06) que sustituye los marcadores y hace **upsert**: comprueba si cada objeto existe (por `config_id` los del Notifications plugin, por **nombre** el monitor) y hace `PUT` si existe o `POST` si no. Re-sincronizar no duplica. Envs: `CANARIO_PRECISION_THRESHOLD` (90), `ALERT_RECIPIENTS` (coma-separado), `ALERT_LOOKBACK` (24h), `RUTA_CAIDA_LOOKBACK` (70m), `RUTA_CAIDA_MIN_CORRIDAS` (2). |

Ambos ficheros deben estar registrados en `IaC/elk/kustomization.yaml` (después del 10).

**Plugins.** Alerting y Notifications vienen incluidos en la imagen
`opensearchproject/opensearch:2.13.0` del clúster de analítica y los paneles correspondientes
en la de OSD; no hay que instalar nada.

**SMTP.** Mismo relay que `co_pqrs_back_report` y `co_pqrs_back_data`: `mailB.bbva.com.co:25`,
sin autenticación ni TLS (`method: none`). **No requiere Secret.** Remitente
`agente_pqrs@bbva.com`; destinatario por defecto el mismo `REPORT_RECIPIENTS` del reporte.
Si en QA/PRD el relay es otro, cambiarlo en el JSON `notification-smtp-account.json` de
**esa** rama (regla de no cruzar endpoints entre entornos).

**Anatomía del monitor** (query-level).
- `schedule`: cada 30 min (mismo ritmo que el CronJob `co-pqrs-benchmark-canario`).
- `inputs.search`: `pqr-benchmark-runs-*`, `size: 1`, `sort @timestamp desc`, filtros
  `event: benchmark.run`, `source: canario`, `@timestamp >= now-24h`.
- `trigger` (painless): `hits.size() > 0 && hits[0]._source.precision_pct < UMBRAL`.
  Sin hits (canario apagado o ventana vencida) → no dispara.
- `action`: correo por el canal `pqr-benchmark-canario-email` con `run_id`, `flow`,
  `environment`, `catalog_version`, `llm_model`, precisión, casos y p95; **throttle 120 min**
  para no repetir el mismo correo cada ciclo mientras el canario siga fallando.

**Verificar en OSD.**
1. Menú ☰ → **OpenSearch Plugins → Alerting → Monitors** → debe existir
   `pqr-benchmark-canario-precision` (Enabled). Pestaña **History** muestra cada ejecución.
2. Menú ☰ → **OpenSearch Plugins → Notifications → Channels** → `pqr-benchmark-canario-email`
   → **Send test message** (prueba el relay SMTP sin esperar a un fallo).
3. Ejecutar el monitor a mano en **Dev Tools**:
   `POST _plugins/_alerting/monitors/<monitor_id>/_execute?dryrun=true` (el `<monitor_id>` sale
   de `GET _plugins/_alerting/monitors/_search { "query": { "match": { "monitor.name": "pqr-benchmark-canario-precision" } } }`).
   La respuesta dice si el trigger evaluó `true` y qué documento leyó.
4. Provocar un disparo real: bajar temporalmente `CANARIO_PRECISION_THRESHOLD` a `101` y
   re-sincronizar; debe llegar un correo en el siguiente ciclo (o al ejecutar sin `dryrun`).
   Volver a dejar el umbral.

**Qué hacer cuando llega el correo.** Abrir el tablero **PQRS Benchmark** (§4.4) con
`source: canario`, ir a *casos fallidos* de esa `run_id` y leer `workflow_expect` vs
`workflow_result` / `workflow_llm`. Un caso dorado que falla es un ejemplo **literal** del
catálogo: el problema es el sistema (LLM, prompt, catálogo desplegado), no el caso.
