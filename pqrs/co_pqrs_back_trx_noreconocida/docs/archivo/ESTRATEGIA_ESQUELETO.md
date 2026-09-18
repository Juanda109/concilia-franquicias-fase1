# Estrategia — verificar el esqueleto del flujo trx en local y llevarlo a OKD

**Fecha:** 13/08/2026 · **v2**, tras verificación adversarial multi-agente (8 agentes
releyendo `origin/feature/PQRSdev` de forma independiente; 25 correcciones sobre la v1).

> **La corrección más importante sobre la v1:** el esqueleto está **mucho más completo**
> de lo que decía. Las tres acciones que di por no-op **están implementadas** — no en el
> dispatch de `workflow_actions.py`, sino como **gates por step-id** en
> `chat_service._prefetch_trx_data_if_needed` (líneas 410-645). Mi criterio de
> inventario ("está en el if-chain = implementada") era el instrumento equivocado.
> El trabajo cambia de *implementar* a **verificar y endurecer lo que ya existe**.

---

## 1 · Qué cambió el 13/08

1. **El esqueleto está en `feature/PQRSdev`** — 43 pasos, flujo entero, con:
   - un **servicio simulador nuevo**: `co_pqrs_back_trx_aso_simulator` (fixtures por PAN:
     `transactions/` ×9, `operations/` ×8, `financial_overview/` ×10,
     `block_failures.json`), con IaC propia. **No** es el `commercial_info_simulator`.
   - costura ASO real en el servicio trx: `ASO_SOURCE=simulator|real`, TSEC (granting
     ticket) **ya implementado** para las 4 llamadas — sólo faltan credenciales.
   - router del servicio reescrito: **8 endpoints bajo `/v1/trx`** (los `/v0` legacy en
     `trx_client` son código muerto a limpiar).
2. **El tablero se movió** (17 capturas del 13/08). Trae la **tabla de vigencias
   completa** (VISA nacional 180 / interoperable 120 / internacional 120; MASTER 120) —
   sólo queda abierto de qué campo sale el *ámbito* de una transacción.
3. **Nicolás publicó el mapeo ASO** (~80 %): financial-overview y Salesforce en verde;
   transaction-cards, transaction-account y detalle en desarrollo; bloqueos pendientes.
4. **Frontera nueva:** lo mío hasta la **confirmación de la compra (`2.4.0.1.11`)**;
   de `validar_pendiente` (`2.4.0.1.12`) en adelante, Luis. Sólo el flujo **sin fondo de
   color**; lo verde (abonos, contracargos, OPS) queda fuera para ambos.
5. **`origin/feature/trxnoreconocida` fue borrada.** Mis 17 commits sólo existen en esta
   máquina.

---

## 2 · Inventario real del esqueleto (v2, verificado por 4 agentes)

### Cómo funciona de verdad

Las acciones trx **no** viven (sólo) en `execute_workflow_action`. El patrón del
esqueleto es: al **llegar** la conversación a un step-id concreto,
`_prefetch_trx_data_if_needed` dispara el gate correspondiente, llama al servicio por
HTTP (`/v1/trx/*`), y **reescribe `current_step`** según el resultado. Once pasos del
YAML no tienen arista entrante: sólo se llega a ellos por esa reescritura programática.

### Mi tramo — todo implementado; el trabajo es verificarlo

| Gate (paso) | Qué hace ya | Riesgo a verificar |
|---|---|---|
| 2.4.0.1 | recurrencia Salesforce | ventana de 6 meses **no acotada** (el tablero la pide; `grep '6 mes'` = 0) |
| 2.4.0.1.4 | productos → `2.4.0.1.5` o `.4.exit` | productos de back_data llevan `last_four_pan_id=''` → card-id `None` → "sin movimientos" falso |
| 2.4.0.1.8 | vigencia (VISA 180/MASTER 120) + card-id + movimientos → `.9` / `.8.return` / `.7.exit` | el simulador **ignora `operationDate`** (devuelve el fichero entero por card_id); los defaults `TRX_MONTO_MIN/MAX` **excluyen movimientos en silencio** |
| 2.4.0.1.10 | detalle → guarda `trx_detalle_result` + `trx_clasificacion` → `.11` / `.10.pqr` | `.10.pqr` **no existe en el tablero** en este tramo (el copy PQR aparece después, en la zona ECI de Luis) |
| 2.4.0.1.11 | confirmación (2 botones) | el tablero marca el detalle como **"Pendiente"** (círculo rojo) y las opciones "en validación por Data" |

**Defectos de presentación ya localizados** (evidencia en código):
- El botón *"No encuentro la transacción"* sólo se añade con **exactamente 3**
  movimientos (`workflow_actions.py:1538`) — con 1-2, la salida `.9.exit` es
  **inaccesible por botones**.
- Más de 5 productos o más de 3 movimientos quedan **truncados** fuera del selector.

### El tramo de Luis — también mayormente implementado

`2.4.0.1.12` rutea offline sobre `trx_clasificacion.pendiente_tdc`; los bloqueos
(`16.1`/`17.1`) llaman HTTP real con `block_temporary/block_permanent` ya en el
servicio; `.19` rutea por `trx_clasificacion.resultado`; `.20` arma el payload Tantia.
**Lo que falta de verdad es la regla MC30 / 7 días** (`grep -i 'mc30|7 dias'` = 0 en
toda la rama): hoy `pendiente_tdc = TDC && responseOperati=='pendiente'`, sin fechas.
El doble rombo del tablero ("¿Compra con TC?" → "¿Pendiente?") se colapsa en ese gate
único — equivalente topológico, a documentar en el contrato.

### Sobrevivió la verificación (sigue siendo cierto)

`2.4.0.1.14` no existe y nada lo referencia · el YAML es estructuralmente sano (cero
`next_step` rotos) · D-01a resuelto por renombre del `save_as` · **D-02 y D-03 siguen
ausentes** · todos los finales convergen en `satisfaction_check` · la topología cubre el
tablero completo hasta `2.4.0.1.11` con copys fieles en la muestra verificada.

### ⚠️ La trampa que explica diagnósticos falsos

Los gates **sólo corren** tras `if trx_service_url or back_data_service_url`
(`chat_service.py:2688`). Sin `TRX_SERVICE_URL` en el `.env`, **todos** los gates —
incluidos los offline de Luis — se saltan y la conversación queda plantada en el nodo:
*parece* no-op sin serlo. Ídem el simulador: su URL por defecto es **DNS de k8s**
(`co-pqrs-back-trx-aso-simulator.pqr-genai-dev.svc.cluster.local:8050`), inalcanzable en
local → fail-open silencioso. **Primera tarea de F0: fijar el entorno antes de sacar una
sola conclusión.**

---

## 3 · Qué portar (sólo 4 de los 17 commits siguen vivos)

`git diff --stat` entre mi rama y el esqueleto: `workflow_actions.py` 7160 líneas,
`analysis_service.py` 892, el YAML 539 — reescritos. De mis 17 commits:

| Portable | Cómo |
|---|---|
| `f64aaa4` D-02 (etiquetas dinámicas) | cherry-pick limpio — 42 líneas en `workflow_engine.py`, exactamente el diff entre ramas |
| `32e333b` D-03 (RUNNING→ACTIVE) | re-aplicación manual trivial; re-verificado: sigue ausente y el síntoma de 150 s es exacto |
| `3aa9370` `DECISIONES_NEGOCIO.md` | tal cual |
| `f512d3b` seed Postgres | sigue útil: dev mantiene `DEFAULT_PRODUCTS_SOURCE='postgres'` |

El resto es papel mojado (el esqueleto lo reescribió) — **incluidos los docs de
pruebas**, que documentan pasos que ya no existen: hay que renumerarlos, no copiarlos.
`_resolve_selected_trx_product_id` (mi arreglo D-01b) es **código muerto** en el
esqueleto: el camino vivo resuelve por índice → last_four → `GET /card-id`.

---

## 4 · Fases (re-presupuestadas)

### F0 · Entorno correcto + ports (1 día) — 🚦 bloquea todo

1. Rama local desde `origin/feature/PQRSdev`.
2. **Stack local completo**: servicio trx + `co_pqrs_back_trx_aso_simulator` +
   `TRX_SERVICE_URL` + `ASO_SIMULATOR_URL` apuntando a local (el default es k8s).
   Los scripts de arranque de mi rama vieja no existen en esta: rehacer mínimos.
3. Humo-test con la **matriz de 12 clientes de Fabián**
   (`docs/trx no reconocida/CLIENTES_SIMULADOR.md`): A=recurrencia, B=sin productos,
   G=pendiente, H=MASTERCARD vencida, I=sin movimientos… — esos son los datos canónicos
   ahora, no los nuestros.
4. Portar D-02 y D-03 (re-verificados) y **entregarlos el día 1**: arreglan todos los
   flujos, no sólo trx.

### F1 · Recorrido y endurecimiento de mi tramo (1,5–2 días)

Un caso por **rama de gate** (no por botón — 11 pasos sólo se alcanzan forzando la
respuesta del backend). Prioridad a los riesgos de §2:

fechas ignoradas por el simulador · montos min/max tragándose movimientos · botón
"No encuentro" con ≠3 movimientos · truncados >5/>3 · `last_four` vacío · formato
compuesto de labels (`[Descripción] — $[valor] [DD/MM/AAAA]`) y viñetas del detalle ·
fecha mal formada en `2.4.0.1.7` (input libre, sin rama de error; el tablero pide
calendario) · `.10.pqr` sin respaldo en el tablero.

Las fechas de los fixtures del simulador son **absolutas (todas 2026-08-06)**: los casos
tecléan `06/08/2026` y morirán ~feb-2027 con la vigencia VISA.

### F2 · De simulator a real donde se pueda (0,5–1 día)

TSEC ya está implementado para las 4 llamadas: en cuanto Nicolás pase credenciales
(`TRX_API_USER_ID/CONSUMER_ID/PASSWORD` + `ASO_REAL_URL`), conmutar financial-overview y
Salesforce (verdes en su mapeo) y comparar respuesta real vs fixture campo a campo.
Movimientos y detalle siguen en simulator (servicios en desarrollo).

### F3 · Contrato con Luis (½ día, en paralelo) — reformulado

No un JSON abstracto: **versionar las claves de `captured_data` que cruzan la frontera**
— `trx_detalle_result`, `trx_clasificacion`, `trx_card_id`, `trx_movimientos_result`,
producto seleccionado, `trx_fecha`, `trx_cantidad`. Huecos concretos a pactar:
1. `origin_flag`/tipo de producto (sin él Luis no evalúa "¿Compra con TC?")
2. la **fecha de referencia para los 7 días** — hoy no existe en ninguna respuesta
3. si el contrato es `trx_clasificacion` precalculada (lo que su gate ya consume) o el
   crudo — pactar sólo el crudo le obliga a reimplementar `aso_rules`
4. la arista de vuelta `2.4.0.1.20.1 → 2.4.0.1.3` (bucle multi-transacción) es
   **alcance compartido**, y `satisfaction_check`/`shared_steps` zona de acuerdo a tres.

**Cómo no pisarnos:** los puntos de colisión son `_prefetch_trx_data_if_needed` (una
sola función con gates de ambos), el if-chain y los helpers compartidos. Propuesta a
Fabián: dispatch `{step: handler}` con handlers en módulos por dueño; si no hay tiempo,
propiedad por bloques comentados y PRs pequeños.

### F4 · Documentación de casos (transversal)

Protocolo, generador y `suite.py` **renumerados al árbol `2.4.0.1.x` sobre la matriz de
12 clientes de Fabián**. `suite.py` además debe aprender que los gates reescriben
`current_step` (fue escrita contra pasos estáticos). Inconsistencias → hoja `Hallazgos`.

### F5 · Entrega y OKD

- **Resuelto el 13/08:** el push directo a ramas *feature* nuevas **funciona** — la
  protección (allowlist + firmas) aplica a las ramas de entorno, no a las nuevas.
  `feature/trx-esqueleto` está en el remoto; la entrega es ahora **PR contra
  `feature/PQRSdev`**. Los bundles quedan como respaldo local.
- IaC: sólo carpeta trx + la del simulador nuevo si toca; el agente lo despliega Fabián.
- Checklist de arranque en OKD: los logs de fail-open silencioso (§2, la trampa).

---

## 5 · Decisiones/preguntas del día 1 (actualizadas)

**A Fabián:**
1. ¿`2.4.0.1.14` no existe a propósito? *(confirmación de intención; nada lo referencia)*
2. ¿Confirmas frontera en `2.4.0.1.11→12` y el mecanismo anti-colisión de F3?
3. ¿Bundle + rama de integración remota?
4. `.10.pqr`: el tablero no trae salida PQR entre listado y confirmación — ¿se queda?
5. ¿El calendario de fecha lo pinta el front, o el bot valida texto libre?
6. Botón "No encuentro" sólo con 3 movimientos y truncado a 3/5 — ¿deliberado?

**A Nicolás:**
7. **Contradicción tablero-vs-mapeo:** el tablero asigna productos a *Consulta ADA* y
   movimientos a *ASO Financial Overview*; tu Excel lo trae al revés. El código actual
   se alinea con el tablero (productos=Postgres/ADA). ¿Cuál manda?
8. ¿Credenciales TSEC para local, o sólo desde el clúster?
9. ¿Esquemas de transaction-cards y detalle estables para construir contra el ejemplo?
10. ¿De qué campo sale el **ámbito** (nacional/interoperable/internacional)? La tabla ya
    está en el tablero; sólo falta eso.
11. Nota roja del tablero: *"Revisar con Manuel Villamil: productos con bloqueo,
    ¿se puede generar abono?"* — condiciona qué lista `2.4.0.1.5`.

**Copys pendientes de fuente única** (a `Hallazgos`, no bloquean): 2.4.2/2.4.3 vs
tablero · dos copys de fecha vencida (el esqueleto ya eligió uno) · si PQR/vencida/
pendiente llevan `satisfaction_check` (hoy el YAML lo aplica a todos los finales).

---

## 6 · Riesgos (v2)

| Riesgo | Mitigación |
|---|---|
| Concluir sobre gates sin `TRX_SERVICE_URL`/simulador local — **todo parece no-op** | F0.2 primero; checklist de env antes de cualquier veredicto |
| Mis 17 commits en una sola máquina, rama remota borrada | bundle + rama de integración **el día 1** |
| Verificar contra la fuente equivocada (ADA vs financial-overview) | pregunta 7 antes de F2 |
| `suite.py` contra pasos estáticos cuando los gates reescriben `current_step` | adaptarla en F4 antes de fiarse de una regresión |
| Fixtures absolutos (2026-08-06) envejecen | anotado en protocolo; regenerables |
| Pisarnos con Luis en `_prefetch`/helpers | mecanismo F3 acordado antes de que él empiece |
| El tablero marca el detalle de `2.4.0.1.11` como "Pendiente" y las opciones "en validación por Data" | dependencia externa visible en el plan; no dar por cerrado mi último paso hasta que Data valide |
