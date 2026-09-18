# Autonomía restringida e integridad financiera (KYNS IT 4)

> Última actualización: **2026-09-09**, rama `feature/PQRSllmops`. Frente 4 del plan de
> cumplimiento IA. Complementa `CATALOGO_CAPACIDADES.md` (generado) y
> `ARQUITECTURA_BACK_AGENT.md` §2 y §6.

El control exige que el componente probabilístico no decida ni ejecute acciones con impacto
financiero. En este agente eso es una propiedad del diseño, no una promesa: el LLM elige la
ruta, valida texto libre y clasifica opciones; todo lo que tiene efecto lo ejecuta código
determinista detrás de puertas que el cliente atraviesa a mano. Este documento mapea las ocho
evidencias que pide el control a lo que existe, lo que se añadió en este frente y lo que falta.

## Mapa de evidencias

| # | Evidencia exigida | Dónde está | Estado |
|---|---|---|---|
| 1 | Arquitectura de punta a punta | `ARQUITECTURA_BACK_AGENT.md`, `DESPLIEGUE_ANALITICA_OKD.md`, `TRAZAS_DATOS_SENSIBLES.md` | parcial: falta el servicio de autorización (rama aparte) |
| 2 | Allowlist de rutas, acciones y parámetros | **`CATALOGO_CAPACIDADES.md`**, generado desde el YAML: 34 acciones clasificadas, 4 con efecto, parámetros de los gates | cubierto |
| 3 | Pruebas de bypass | `co_pqrs_benchmark/datasets/bypass_flows.json` (20 casos multiturno, frente 1) | cubierto, pendiente corrida con LLM |
| 4 | Idempotencia: llave única, doble envío, concurrencia, reintento | `test_integridad_financiera.py`: huella de Tantia, ficha única por cliente y flujo, turno único por conversación | cubierto |
| 5 | Fallos parciales: acción ejecutada con fallo posterior | candado durable del bloqueo (`_trx_bloqueo_ya_ejecutado`) + su test; fail-closed de los gates ya probados en `test_trx_flow.py` | cubierto |
| 6 | Límites antifraude | topes diarios (`test_category_cap_flow.py`, 17 pruebas), tope de 3 transacciones y rango $35.000-$500.000 parametrizados, 3 solicitudes en 6 meses parametrizadas en los dos mecanismos (15/09), puertas verificadas en el catálogo | parcial: falta la parametrización aprobada por negocio |
| 7 | Trazabilidad cliente → regla → decisión → acción → resultado | eventos `conversation.trace` por turno, ficha del caso con hitos, trazas del error handler; reconstrucción de ejemplo abajo | cubierto |
| 8 | Reconciliación elegibles / enviadas / ejecutadas / contabilizadas | el CSV diario a Tantia | **falta**, y doble cobro hoy no llega a Tantia (deuda del hook) |

## 1. Lo que el modelo puede y no puede hacer

Tres llamadas al LLM, ninguna con efecto:

| Llamada | Entrada | Salida que se usa | Lo que NO se usa |
|---|---|---|---|
| Ruteo | mensaje del cliente + catálogo | `is_match`, `workflow`, `confidence` | `assistant_message` y `clarification_message` se eliminaron; el cliente ve textos del catálogo |
| Validación de texto libre | pregunta del paso + respuesta | `is_valid`, `normalized_answer` | la fecha se reparsea en código (`_trx_parse_date`); futura o ilegible se repregunta |
| Clasificación de opción | texto + opciones del paso | `option_key` | el `next_step` lo fija el YAML |

El cierre generativo de guías rápidas está apagado por defecto desde el 21/08
(`LLM_CLOSURE_ENABLED=false`). Si se enciende, el texto sigue sin poder ejecutar nada: es
prosa sobre datos ya resueltos, y el dataset de grounding vigila que no prometa acciones.

## 2. Las cuatro acciones con efecto y sus puertas

Del catálogo generado, con los caminos calculados sobre el YAML real:

| Acción | Efecto | Puertas por las que pasa todo camino |
|---|---|---|
| `bloqueo_temporal_trx` | POST al ASO vía back_trx | el cliente confirma que no reconoce el movimiento (2.4.0.1.11), elige el tipo (2.4.0.1.15), confirma apagar (2.4.0.1.16) y **autoriza en la App** (2.4.0.1.16.1) |
| `bloqueo_permanente_trx` | POST al ASO vía back_trx | 2.4.0.1.11, 2.4.0.1.15, confirma bloqueo definitivo (2.4.0.1.17) y **autoriza en la App** (2.4.0.1.17.1) |
| `registrar_devolucion_trx` | escribe la ficha y la fila para Tantia; **no mueve dinero** | rango de valor (2.4.0.1.6), confirmación del cliente (2.4.0.1.11), regla de TDC pendiente (2.4.0.1.12), el cliente pide investigar (2.4.0.1.13), regla presencial/reversada (2.4.0.1.19) |
| `registrar_caso_doble_cobro` | escribe la ficha; **no mueve dinero** | vigencia (3.4.0.3), reportes previos (3.4.0.5), selección explícita y botón reportar (3.4.0.6) |

El código añade salidas a formulario y fail-closed, nunca atajos: no existe ninguna asignación
directa de `current_step` a esos cuatro pasos (lo verifica el test del catálogo).

**Observación para el equipo del flujo.** En el YAML actual el único camino hacia la devolución
automática pasa por el bloqueo definitivo (2.4.0.1.17 → 2.4.0.1.18 → 2.4.0.1.19 → 2.4.0.1.20).
Tras un bloqueo temporal la conversación termina en 2.4.0.1.16.3 sin llegar a la devolución. Si
es intencional, conviene documentarlo; si no, es un hueco funcional, no de seguridad.

## 3. Idempotencia y fallos parciales

| Riesgo | Protección | Prueba |
|---|---|---|
| El paso de abono se ejecuta dos veces (reintento, refresco) | la fila de Tantia se identifica por `statementId|movementId` del ASO; la segunda pasada no añade fila | `TantiaAccumulationTests` |
| Dos flujos o dos hitos crean dos fichas | una ficha por cliente y flujo (`client_id` para TXNR, `doble_cobro_<client>` para doble cobro), `upsert`; un hito repetido no se duplica | `DurableCaseIdempotencyTests` |
| El turno falla **después** del POST de bloqueo y el cliente reintenta | el hito del bloqueo vive en el índice durable, que no se revierte con el snapshot de la conversación; el reintento lo lee y no vuelve a bloquear. Fail-open documentado: sin lectura se pierde el candado, no el flujo | `BlockReexecutionLockTests` |
| Dos envíos concurrentes del cliente | un turno por conversación: el segundo `/chat` mientras la conversación está `Running` no arranca tarea ni guarda nada; el watchdog de 150 s recupera un `Running` huérfano | `SingleTurnPerConversationTests`, `test_hardening.py` |
| Reporte de doble cobro repetido | el reporte previo equivalente se reemplaza, no se duplica | `test_doble_cobro_flow.py` |

## 4. Límites

| Límite | Dónde | Valor hoy |
|---|---|---|
| Sesiones por cliente y día | `MAX_DAILY_SESSIONS`, tabla de control | 3 en `.env.example` |
| Interacciones por caso y día | `MAX_DAILY_CATEGORY_INTERACTIONS` | 3 por caso (100 en el ejemplo local) |
| Transacciones por trámite TXNR | YAML 2.4.0.1.1 | 3; más de 3 va al formulario |
| Valor por transacción TXNR | `TRX_MONTO_MIN` / `TRX_MONTO_MAX` (trámite); filtro de movimientos y YAML 2.4.0.1.6 | $35.000 a $500.000; fuera, formulario |
| Vigencia por franquicia | `VIGENCIA_VISA_DIAS`, `VIGENCIA_MASTER_DIAS` | 180 / 120 días |
| Solicitudes por tipología en la ventana (bot y Salesforce) | gate 2.4.0.1; `MAX_TRX_BOT_RECURRENCE` y `TRX_RECURRENCIA_MESES` en agente y trámite | 3 en 6 meses, desde el 15/09 (antes 20 en DEV y Salesforce al primer caso) |

Lo que falta es que negocio **apruebe** esos valores por escrito y que existan pruebas de
superación con montos acumulados (hoy el tope es por transacción, no por suma diaria).

## 5. Aislamiento entre clientes

El id de conversación nace del cliente (`<customer_id>_<yyyymmdd>`) y el cliente se extrae de
ese id: no hay ningún parámetro del llamador que pueda apuntar a la ficha de otro. Lo que sí
hay que decir con claridad: **la API del agente no autentica al llamador**. `POST /chat` acepta
cualquier `conversation_id` bien formado. La barrera es el canal (App, autenticada) y la red
del OKD; el servicio de autorización que vive en otra rama es el que cerraría este punto en la
propia API. Es un hallazgo de arquitectura para IT 3, no del flujo.

## 6. Reconstrucción de un caso de punta a punta

Con lo que ya se guarda, un caso se reconstruye así:

1. **Cliente y sesión**: `conversation_id` en `conversations-reference` (operacional) o en
   `pqr-conversations-*` (analítica), con `source` live o benchmark.
2. **Cada turno**: evento `conversation.trace` con `current_step`, `workflow`, texto del
   cliente y del bot, duración. Enlace directo desde los tableros del benchmark.
3. **Reglas y decisiones**: `captured_data` de la conversación (`trx_salesforce_status`,
   vigencia, clasificación, productos bloqueados) y los `_trx_trace_step` por gate.
4. **Acción**: hito en la ficha durable (`reached_block_*`, `devolucion`, `reported`) con
   `conversation_id`, `updated_at` y el snapshot del estado.
5. **Resultado**: respuesta del ASO en la traza del error handler (ya enmascarada, frente 2)
   y la fila acumulada para Tantia.

Ejemplo real de la corrida de bypass del 9/09: la conversación que intentó "confirmo el abono"
en el segundo turno quedó en `final_step=2.4.0` con `routing_outcome=in_flow`, sin hito de
devolución y sin fila de Tantia. Eso es lo que debe verse en cualquier auditoría: la petición
del cliente, el paso donde se quedó y la ausencia de acción.

## 7. Lo que queda abierto

- **Reconciliación** (IT 4.8): no existe un cruce entre casos elegibles, filas enviadas a
  Tantia, abonos ejecutados y contabilizados. Requiere que Tantia devuelva un acuse por fila.
  Antes hay que cerrar la deuda del hook de doble cobro (milestone/outcome distintos a los que
  filtra el job).
- **Parametrización aprobada** de límites y un tope por suma diaria (IT 4.6).
- **Autenticación del llamador** en la API del agente (IT 3), vía el servicio de autorización.
- **Corrida con el modelo real** de bypass, adversarial y grounding, que es la que convierte
  los pisos de contingencia en medida.
