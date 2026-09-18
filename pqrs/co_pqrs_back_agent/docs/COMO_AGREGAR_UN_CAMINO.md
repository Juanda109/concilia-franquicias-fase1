# Cómo agregar un nuevo camino (workflow) al agente

Guía práctica para añadir un camino conversacional nuevo a `co_pqrs_back_agent`.
El ruteo es **100% data-driven**: en la mayoría de los casos NO se toca código Python,
solo YAML. Se usa como ejemplo real el camino `trx_no_reconocida`.

> **Regla de oro:** la fuente de verdad del ruteo son los YAML del repo
> (`general.yml` + `routing_prompt.yml`). **Prohibido** que el agente dependa de un
> `.csv`/`.xlsx` en el repositorio. El Excel de ruteo (`routing_catalog_base_PQRS.xlsx`)
> es **solo material de referencia externo**; su contenido se transcribe a mano a
> `general.yml`.

---

## 1. Puntos de contacto (checklist)

| # | Archivo | Qué se hace | ¿Obligatorio? |
|---|---------|-------------|----------------|
| 1 | `src/domain/workflow/general.yml` | Nuevo **grupo** y/o **opción** (workflow) del catálogo, con `routing_criteria`, `limit_category`, `description`, `preconditions`, `no_usar`, `se_confunde_con`, `examples`, `contraejemplos`, `workflow`. | Sí |
| 2 | `src/domain/workflow/<grupo>/<workflow>.yml` | El **árbol del flujo** (pasos, opciones, textos UX, pasos `terminal`). | Sí |
| 3 | `src/domain/workflow/routing_prompt.yml` | 1–2 `few_shots` de negocio (opcional, mejora el ruteo). | Opcional |
| 4 | `src/domain/workflow/general_messages.yml` | Solo si el camino necesita mensajes compartidos nuevos. | Opcional |
| 5 | `src/infrastructure/persistence/<x>_client.py` + `core/config.py` + `entrypoint/api/dependencies.py` | Si el camino consume un servicio/datos externos: cliente fail-open + URL en config + provider de dependencia (+ microservicio nuevo si aplica). | Solo si jala datos |
| 6 | (automático) `limit_category` | El conteo/tope diario por categoría es **automático** al declarar un `limit_category`. | — |
| 7 | Tests | Ver sección 4. | Sí |
| 8 | `IaC/backend/...` | Manifiestos + env vars por ambiente (aditivo). | Al desplegar |

---

## 2. Convenios importantes

### Ruta del archivo de flujo (`WorkflowEngine._resolve_workflow_path`)
El loader busca, en este orden:
1. **nested:** `domain/workflow/<grupo>/<workflow>/<workflow>.yml`
2. **grouped:** `domain/workflow/<grupo>/<workflow>.yml`  ← recomendado
3. **legacy:** `domain/workflow/<workflow>.yml`

Ejemplo: grupo `trx_no_reconocida`, workflow `trx_no_reconocida` →
`domain/workflow/trx_no_reconocida/trx_no_reconocida.yml`.

### Capa de conteo diario (`limit_category`)
- Cada **grupo** en `general.yml` declara un `limit_category` (p. ej. `general`,
  `centrales`, `trx_no_reconocida`).
- `WorkflowEngine.get_limit_category(workflow)` resuelve la categoría del grupo dueño.
- `WorkflowEngine.get_all_limit_categories()` las enumera.
- `ControlTableStore` lleva `daily_categories[dia][categoria]`; el tope es
  `MAX_DAILY_CATEGORY_INTERACTIONS` (default **3**).
- **Declarar un `limit_category` nuevo crea automáticamente su propio contador y tope
  diario, independiente de las demás capas.** No hay que tocar código de caps.
  > Si algún día se quiere un tope **distinto** por categoría, habría que reintroducir
  > un mapa de topes por categoría en `config.py` + `control_table_store.py`.

### Pasos `terminal`
Un paso con `input_type: "terminal"` (o `terminal: true`) muestra su `question` y
**cierra la consulta** (`ConversationStatus.CLOSED`). Útil para mensajes WIP o de cierre.

---

## 3. Clases clave

| Clase / módulo | Rol |
|----------------|-----|
| `domain/workflow/models.py` → `WorkflowSelectorGroup`, `WorkflowSelectorOption`, `WorkflowStep`, `WorkflowRoutingEntry` | Esquema del catálogo y de los pasos (Pydantic, `extra="forbid"`). |
| `domain/workflow/workflow_engine.py` → `WorkflowEngine` | Carga los YAML (`_load_catalog`, `_resolve_workflow_path`), construye el catálogo de ruteo (`build_routing_catalog`), maneja los pasos (`generate_response`) y resuelve `get_limit_category` / `get_all_limit_categories`. |
| `domain/workflow/routing_prompt_builder.py` | Ensambla el prompt de ruteo (persona + few-shots + catálogo). |
| `application/chat/chat_service.py` → `ChatService` | Orquesta start/turn/end, el ruteo y la capa de cap (`_maybe_handle_category_cap`, warning SÍ/NO). |
| `infrastructure/persistence/control_table_store.py` → `ControlTableStore` | Contadores diarios por categoría y rechecks. |
| `infrastructure/persistence/*_client.py` | Clientes HTTP fail-open hacia los servicios de datos (p. ej. `back_data_client.py`, `trx_client.py`). |

---

## 4. Tests que SIEMPRE hay que ajustar al agregar un camino

En `tests/test_domain/test_workflow/test_routing_catalog.py`:
- **`test_catalog_has_all_workflows`**: sube el **conteo total** de workflows (p. ej. 18 → 19).
- **`test_contraejemplos_reference_existing_workflows`**: valida que cada `-> clave`
  dentro de `contraejemplos` **exista** en el catálogo. Por eso los contraejemplos que
  apuntan a caminos que aún no existen deben escribirse **sin la flecha `->`** (como
  negativos descriptivos), o apuntar a un workflow ya existente.

Además, según el camino:
- Un test de flujo (engine-driven, sin LLM), p. ej. `tests/test_application/test_trx_flow.py`.
- Un test de la capa de cap, p. ej. en `tests/test_application/test_category_cap_flow.py`.
- Si hay cliente nuevo: `tests/test_infrastructure/test_persistence/test_<x>_client.py`.

Comando de pruebas (el venv no trae pytest, hay que pasar `--with pytest`):
```bash
cd co_pqrs_back_agent
uv run --with pytest python -m pytest -q
```

---

## 5. Ejemplo aplicado: `trx_no_reconocida`

1. **Catálogo** (`general.yml`): grupo `trx_no_reconocida` con `limit_category: "trx_no_reconocida"`
   y una opción/workflow `trx_no_reconocida` (20 `examples`, negativos saneados).
2. **Flujo** (`trx_no_reconocida/trx_no_reconocida.yml`): paso `1` (choice) con las 4 opciones
   (Cambiazo / Hurto o pérdida / Ingeniería social / Compra presencial o por internet) →
   pasos `1.1`–`1.4` **terminales** con "Estamos trabajando en este proceso." (WIP).
3. **Few-shot** en `routing_prompt.yml`.
4. **Cliente** `trx_client.py` (fail-open) + `TRX_SERVICE_URL` en `config.py` + `get_trx_service_url()`
   en `dependencies.py`. (Aún **no** cableado al flujo: es MOCK.)
5. **Microservicio mock** `co_pqrs_back_trx_noreconocida` (puerto 8004).
6. **Tests** actualizados (conteo 19, flujo, capa de cap, cliente).

---

## 6. Fase 2 pendiente (reorganización sugerida por el Excel de ruteo)

El Excel de referencia ya insinúa una **consolidación** del catálogo. Pendientes:
- Reescribir/consolidar descripciones del catálogo (versión más concisa).
- Crear el workflow **`faq_cuenta_embargada`** bajo `guia_rapida` (hoy el embargo lo maneja
  `centrales_de_riesgo`). Ojo: mover el embargo cambia su `limit_category` de `centrales`
  a `general` — es un cambio de comportamiento que requiere aprobación.
- Definir las **rutas de reclamación de transacción reconocida** (cobro duplicado, valor
  incorrecto, reclamación al comercio) y la **ruta de seguridad/bloqueo preventivo**
  (hoy referenciadas como negativos sin flecha en `trx_no_reconocida`).
- Al implementar cada camino de `trx_no_reconocida`, reemplazar los 4 pasos WIP por su
  lógica real, cableando `trx_client` (consultar_trx / ASOS / análisis).

### Bonus organización
Estandarizar todos los caminos al convenio `domain/workflow/<grupo>/<workflow>.yml`
(hoy `pqrs/centrales_de_riesgo` está anidado un nivel extra). Refactor de bajo riesgo,
documentar antes de mover archivos (el loader soporta las 3 rutas, así que se puede migrar
de forma incremental).
