# Guía paso a paso: visualizaciones y tableros en OpenSearch Dashboards (OSD)

Guía específica para PQRS. En OSD **no hay Lens** (eso es Kibana). Las visualizaciones se
arman con **agregaciones**: eliges un **tipo** (barra, línea, tabla…), defines **Metrics**
(qué se calcula, normalmente el eje **Y**) y **Buckets** (cómo se agrupa, normalmente el eje
**X** o el "split"). Todo es apuntar-y-clic. Basado en la documentación oficial actual de
OpenSearch.

---

## 0. Antes de empezar (por qué "no ves campos")
Los campos y las visualizaciones **solo aparecen si ya hay datos indexados** y un **index
pattern** creado. Si no ves nada:
1. Debe existir el índice. En **Dev Tools**: `GET _cat/indices?v` → deben verse
   `pqr-metrics-YYYY.MM.dd` / `pqr-conversations-YYYY.MM.dd`. Si no, aún no ha llegado data
   (Logstash arriba + una conversación real; ver la guía de despliegue).
2. Debe existir el **index pattern** (§1). Sin él, la app Visualize no tiene "source" y no
   muestra campos.
3. El **time picker** (arriba a la derecha) debe cubrir el rango donde hay datos (p.ej.
   "Last 7 days"). Si está en un rango sin datos, verás la visualización vacía.

---

## 1. Crear el index pattern (una vez por índice)
1. Menú ☰ → **Management → Dashboards Management → Index patterns**.
2. **Create index pattern**.
3. Escribe `pqr-metrics-*` → **Next step**.
4. En *time field* elige **`@timestamp`** → **Create index pattern**.
5. Repite con `pqr-conversations-*`.
Al terminar verás la lista de campos con su tipo (keyword, long, date, boolean…). Si un campo
no aparece, usa el botón **Refresh field list** (icono de recargar arriba a la derecha del
index pattern).

---

## 2. Conceptos clave (Visualize)
- **Tipo de visualización**: Vertical Bar, Line, Pie, Metric, Data table, etc.
- **Metrics (eje Y)**: la operación numérica. Agregaciones útiles:
  - **Count** — nº de documentos (no requiere campo). Default.
  - **Unique Count (Cardinality)** — valores únicos de un campo (p.ej. usuarios).
  - **Sum / Average / Max / Min** — sobre un campo numérico (p.ej. tokens).
  - **Percentiles** — p50/p95/p99 (p.ej. latencia).
- **Buckets (eje X / división)**: cómo se agrupan los datos.
  - **X-axis** → **Date Histogram** sobre `@timestamp` = serie temporal.
  - **X-axis** → **Terms** sobre un keyword (p.ej. `workflow`) = una barra por categoría.
  - **Split series / Split chart** → subdivide por otra dimensión.
- **Search bar (DQL)**: filtra los documentos (p.ej. `event: conversation.turn`).
- **Update** (botón azul abajo a la derecha del panel de config): **aplica** los cambios. Si
  no lo pulsas, la visualización no se refresca.

Flujo mental: **elige tipo → elige source (index pattern) → filtra con la barra → define
Metrics (Y) → define Buckets (X/split) → Update → Save.**

---

## 3. Receta base (una serie temporal) — síguela una vez
Ejemplo: **conversaciones iniciadas por día**.
1. Menú ☰ → **OpenSearch Dashboards → Visualize** → **Create visualization**.
2. Elige **Vertical Bar** (o **Line**).
3. En **Choose a source**, elige **`pqr-metrics-*`**.
4. Time picker (arriba dcha.): **Last 7 days**.
5. En la **barra de búsqueda** escribe el filtro: `event: conversation.started`.
6. Panel derecho, sección **Buckets** → **Add** → **X-axis**.
7. **Aggregation** = **Date Histogram**. **Field** = **@timestamp**.
8. Pulsa **Update**. Verás barras = nº de conversaciones por intervalo.
9. **Metrics** ya está en **Count** (nº de documentos) — no toques nada.
10. Arriba: **Save** → título `PQRS - Conversaciones iniciadas` → **Save**.

> Esta es la mecánica para casi todo. Lo que cambia entre métricas es: el **filtro**
> (`event: ...`), la **Metric (Y)** y el **Bucket (X/split)**.

---

## 4. Recetas concretas para PQRS (índice `pqr-metrics-*`)

Para cada una: Visualize → Create visualization → (tipo) → source `pqr-metrics-*` → escribe el
**filtro** en la barra → configura **Metrics/Buckets** → **Update** → **Save**.

| # | Visualización | Tipo | Filtro (barra DQL) | Metrics (Y) | Buckets (X / split) |
|---|---|---|---|---|---|
| 1 | Conversaciones iniciadas | Vertical Bar/Line | `event: conversation.started` | Count | X-axis → Date Histogram → `@timestamp` |
| 2 | Conversaciones cerradas | Line | `event: conversation.closed` | Count | X-axis → Date Histogram → `@timestamp` |
| 3 | Turnos por día | Line | `event: conversation.turn` | Count | X-axis → Date Histogram → `@timestamp` |
| 4 | **Usuarios únicos/día** | Vertical Bar | `event: conversation.started` | **Unique Count** de `user_id` | X-axis → Date Histogram → `@timestamp` (Interval: Daily) |
| 5 | **Distribución por caso** | Pie o Horizontal Bar | `event: conversation.turn` | Count | **Split slices/series** → Terms → `workflow` (Size 20) |
| 6 | **Dónde abandonan (paso)** | Horizontal Bar | `event: conversation.turn` | Count | X-axis → Terms → `current_step` (Size 20, Order Descending) |
| 7 | **Latencia p50/p95/p99** | Line | `event: conversation.turn` | **Percentiles** de `duration_ms`, valores `50,95,99` | X-axis → Date Histogram → `@timestamp` |
| 8 | Tokens por día | Vertical Bar | `event: conversation.turn` | **Sum** de `tokens.total_tokens` | X-axis → Date Histogram → `@timestamp` |
| 9 | Tokens por caso | Horizontal Bar | `event: conversation.turn` | **Sum** de `tokens.total_tokens` | X-axis → Terms → `workflow` (Size 20) |
| 10 | **% LLM usado** | Pie | `event: conversation.turn` | Count | Split slices → Terms → `llm_used` |
| 11 | Ruteo (comprensión) | Pie | `event: conversation.turn` | Count | Split slices → Terms → `routing_outcome` |
| 12 | No-match (número) | Metric | `event: conversation.turn and routing_outcome: no_match` | Count | (sin bucket) |
| 13 | Bloqueos de guardrail | Metric | `event: conversation.turn and guardrail_blocked: true` | Count | (sin bucket) |
| 14 | **CSAT** | Pie | `event: conversation.closed` | Count | Split slices → Terms → `satisfaction_result` |
| 15 | Resolución | Horizontal Bar | `event: conversation.closed` | Count | X-axis → Terms → `resolution` |
| 16 | Abandono encuesta | Metric | `event: conversation.closed and satisfaction_status: ABANDONED` | Count | (sin bucket) |
| 17 | Errores por tipo | Horizontal Bar | `event: conversation.error` | Count | X-axis → Terms → `error_type` |
| 18 | **Timeouts** | Metric | `event: conversation.error and error_type: TimeoutError` | Count | (sin bucket) |
| 19 | **Topes por caso** | Horizontal Bar | `event: conversation.cap_reached` | Count | X-axis → Terms → `limit_key` (Size 30) |
| 20 | Topes subflujo centrales | Horizontal Bar | `event: conversation.cap_reached and limit_scope: centrales_subflow` | Count | X-axis → Terms → `limit_key` |

### Cómo se hace cada tipo de config (clic-a-clic)
- **Métrica no-default (Sum/Average/Unique Count/Percentiles):**
  Panel derecho → sección **Metrics** → clic en **Y-axis** → **Aggregation** (dropdown) →
  elige la agregación → **Field** (dropdown) → elige el campo → **Update**.
- **Percentiles (latencia):** en **Y-axis** → Aggregation **Percentiles** → Field
  `duration_ms` → en **Percents** deja `50, 95, 99` (usa el icono de borrar para quitar los
  que no quieras y **Add percent** para añadir) → **Update**.
- **Serie temporal (X):** **Buckets** → **Add** → **X-axis** → Aggregation **Date Histogram**
  → Field `@timestamp` → (opcional) **Minimum interval: Daily/Hourly** → **Update**.
- **Por categoría (X):** **Buckets** → **Add** → **X-axis** → Aggregation **Terms** → Field
  `workflow` (o el que sea) → **Size** 20 → **Order by** Metric: Count, **Descending** →
  **Update**.
- **Pie (división):** en Pie la sección es **Buckets → Add → Split slices → Terms → Field**.
- **Metric (número único):** tipo **Metric**; solo defines la **Metric (Count/…)**, sin bucket.
- **Combinar serie temporal + categoría:** primero X-axis Date Histogram y luego
  **Add → Split series → Terms → `workflow`** (barras apiladas por caso a lo largo del tiempo).

---

## 5. Tablero de CONVERSACIONES (traza Q&A, índice `pqr-conversations-*`)
La forma más simple de ver "pregunta ↔ respuesta" es **Discover** (no necesita agregaciones):
1. Menú ☰ → **OpenSearch Dashboards → Discover**.
2. Arriba a la izquierda, selecciona el index pattern **`pqr-conversations-*`**.
3. Time picker: el rango que quieras.
4. En la lista de **Available fields** (izquierda), pasa el mouse y pulsa **+** (Add) sobre:
   `user_id`, `workflow`, `current_step`, `user_content`, `assistant_content`. Se vuelven
   columnas de la tabla.
5. Busca en la barra DQL, p.ej. `user_content: "4x1000"` (full-text) o filtra por
   `workflow: impuesto_4x1000`.
6. **Save** (arriba) → título `PQRS - Traza conversaciones`. Un Discover guardado también se
   puede **añadir a un dashboard**.

Alternativa como panel de tabla en el dashboard: Visualize → Create visualization → **Data
table** → source `pqr-conversations-*` → Metrics: **Count** → Buckets → **Split rows** →
Terms → `workflow` (y añade más filas Terms para `user_content.raw`, etc.).

---

## 6. Armar el dashboard
1. Menú ☰ → **OpenSearch Dashboards → Dashboards** → **Create** (o **Create new dashboard**).
2. **Add** (o el icono +) → **From library** → selecciona las visualizaciones que guardaste.
3. Reacomoda/redimensiona los paneles arrastrando.
4. **Save** → título `PQRS Métricas` (y otro dashboard `PQRS Conversaciones` si quieres).
5. Usa el **time picker** y activa **Auto-refresh** (menú del reloj → cada 10s/30s) para
   tiempo casi real.
6. El **ID del dashboard** (para el reporte por correo) está en la URL al abrirlo:
   `.../app/dashboards#/view/`**`<ESTE-UUID>`** → ese va en `DASHBOARD_URL` del CronJob `co_pqrs_back_report`.

---

## 7. Filtros y búsqueda (DQL)
En la barra de búsqueda (aplica a Visualize, Discover y Dashboard):
- `event: conversation.turn` — un tipo de evento.
- `workflow: centrales_de_riesgo` — un caso.
- `routing_outcome: no_match` — no entendidos.
- Combinar: `event: conversation.closed and satisfaction_result: false`.
- Texto libre (solo campos `text` como `user_content`): `user_content: "no reconozco"`.
- Rango de fechas: con el **time picker**, no en la barra.

---

## 8. Troubleshooting
- **"no existe el índice / no puedo crear index pattern"** → aún no hay datos: genera una
  conversación y valida con `GET _cat/indices?v` en Dev Tools.
- **La visualización sale vacía** → revisa el **time picker** (rango con datos) y el **filtro**
  (`event: ...` correcto).
- **No aparece un campo en Metrics/Buckets** → si es reciente, en el index pattern pulsa
  **Refresh field list**. Para agregar por texto (p.ej. `user_content`) usa el sub-campo
  `user_content.raw` (keyword); los `text` puros no permiten Terms.
- **Números que no suman/percentilan** → asegúrate de que el campo es numérico (`long`) en el
  mapping; los templates ya lo definen así para `duration_ms`, `tokens.*`.
- **No veo "Index patterns" en el menú** → está en **Management → Dashboards Management**; y
  requiere permisos de escritura en el tenant.
