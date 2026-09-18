# Arquitectura del `co_pqrs_back_agent` — análisis

> **Estado: 2026-08-24**, rama `feature/PQRSdev`.
> `chat_service.py` tiene ~5.960 líneas y concentra la conducción de la
> conversación. Este documento explica **el orden en que se toman las decisiones**
> en un turno, porque ese orden es la parte más difícil de inferir leyendo el
> código.

---

## 1. Secuencia de un turno

Cada mensaje del cliente atraviesa estas etapas **en este orden**. La primera que
resuelve, corta el turno:

| # | Etapa | Determinista | Qué hace |
|---|---|---|---|
| 1 | **Token de canario** | Sí | Si el texto es `TRX_CANARY_TOKEN`, desbloquea el flujo TXNR para esa conversación. Va **primero**, antes del guardrail, para que no lo bloquee. |
| 2 | **Guardrail de entrada** (`screen_user_input`) | Sí | Entrada vacía, demasiado larga, inyección de prompt o petición de datos de terceros. |
| 3 | **Saludo puro** | Sí | Si todos los tokens son de cortesía y estamos en un punto neutro, re-saluda sin rutear. |
| 4 | **Entrada sin letras** | Sí | `9+`, `...`, `??` → pide aclaración sin gastar LLM. |
| 5 | **Juez de alcance** (LLM) | No | Clasifica si el tema es del banco. Tiene red de seguridad determinista (§3). |
| 6 | **Enrutador** (LLM) | No | Elige el workflow del catálogo con nivel de confianza. |
| 7 | **Rescate de centrales** | Sí | Si el LLM no matcheó pero el texto menciona `centrales/datacredito/transunion/cifin`, se rescata. |
| 8 | **Meta-petición pelada** | Sí | "tengo una queja" sin motivo → pide el motivo con botón Continuar. |
| 9 | **Reintento de aclaración** | Sí | 1er no-match → pide reformular. 2º consecutivo → formulario PQR. |

Etapas 1-4 y 7-9 son **deterministas**: mismo texto, mismo resultado. Solo 5 y 6
dependen del modelo.

### Desenlaces registrados para analítica
El campo `routing_outcome` deja rastro de qué camino tomó el turno:

`matched` · `confirmation` · `no_match` · `clarify_retry` ·
`clarify_unintelligible` · `pqrs_clarify` · `greeting` · `guardrail_blocked` ·
`in_flow` · `trx_canary_enabled` · `other`

---

## 2. Ruteo: qué es del LLM y qué no

El enrutador LLM devuelve `is_match`, `workflow`, `confidence`, `rationale`,
`assistant_message` y `clarification_message`. **De todo eso, al cliente solo
llegan textos del catálogo**, nunca redactados por el modelo:

| Campo del LLM | Uso |
|---|---|
| `is_match`, `workflow`, `confidence` | **Decisión** de ruteo |
| `rationale` | **Señal interna** para elegir sub-flujo (`_resolve_routing_entry_hint`) y analítica |
| `assistant_message` | **No se usa.** Se eliminó de la firma para que nadie lo reintroduzca |
| `clarification_message` | **No se usa.** Ver §5 |

Usar la salida del LLM para **decidir** es distinto de **mostrar** su texto. Lo
primero se mantiene; lo segundo se eliminó por decisión de negocio.

### Umbrales de confianza
| Confianza | Comportamiento |
|---|---|
| `high` / `medium` | Auto-arranca el flujo |
| `low` | **Confirma** con el cliente: "¿Te refieres a {hint}?" + botones Continuar/Salir. El `hint` sale de `confirmation_hints` en `general_messages.yml`, no del LLM |
| `none` / sin match | Reintento de aclaración → formulario |

---

## 3. Guardrails: dos capas y sus redes de seguridad

### Capa 1 — `input_screen.py` (determinista, 0 tokens)
Cuatro bloqueos, cada uno con su mensaje fijo:

| Causa | Mensaje |
|---|---|
| Entrada vacía | `EMPTY_INPUT_MESSAGE` |
| Más de 2000 caracteres | `TOO_LONG_INPUT_MESSAGE` |
| Inyección de prompt / jailbreak | mensaje de fuera de alcance |
| Datos de terceros | `THIRD_PARTY_DATA_MESSAGE` (habeas data) |

**Lección aprendida (caso real 98909004_20260820).** El patrón `\bDAN\b`, puesto
para el jailbreak "DAN" y compilado con `IGNORECASE`, coincidía con el **verbo
español "dan"**. El mensaje *"en el banco no me **dan** razón"* —una queja
legítima por un CDT de 50 millones— se bloqueó como inyección. Medido sobre un
corpus de quejas reales: **8 de 12 frases legítimas quedaban bloqueadas**.

Tres reglas de diseño que quedaron escritas en el módulo:
1. Nada de siglas sueltas que coincidan con palabras comunes. `DAN` exige contexto
   (`modo DAN`, `eres DAN`, `actúa como DAN`).
2. `ignora`/`olvida` solo cuentan si el objeto es una instrucción, regla, prompt o
   sistema. *"olvida lo anterior, mejor quiero..."* es una corrección normal de un
   cliente, no un ataque.
3. `actúa/compórtate como` exige un objeto de persona o sistema. *"el banco actúa
   como intermediario"* no es un ataque.

Verificado: **0 falsos positivos** en 13 frases legítimas y **0 falsos negativos**
en 14 ataques reales.

### Capa 2 — `judge.py` (juez de alcance con LLM)
Opcional (`GUARDRAIL_JUDGE_ENABLED`), clasifica si el mensaje es del banco.

**Red de seguridad determinista:** aunque el juez diga "fuera de alcance", el
mensaje **no se bloquea** si contiene cualquier señal bancaria — producto, monto,
PQRS, central de riesgo, fraude o canal (~150 términos en
`_BANKING_SIGNAL_WORDS`). El costo de un falso positivo (echar a un cliente con
una queja real) es muy superior al de dejar pasar un mensaje ajeno, que el
enrutador resolverá de todos modos.

> **Límite conocido y documentado:** un mensaje sin señales bancarias, como
> *"hola, puedes escribirme en paisa"*, **no** está cubierto por esa red. Queda
> protegido solo por el prompt del juez. Está registrado como test explícito para
> que el límite sea visible.

---

## 4. Detección de saludo: por qué no usa similitud ciega

El detector de saludo tolera typos (`Bns días`, `Bule`, `Hoka`), pero **la
similitud difusa no se aplica a palabras de contenido**.

Un umbral bajo de similitud para mensajes de un solo token producía esto:

| El cliente escribe | Se parecía a | Similitud | Resultado |
|---|---|---|---|
| `queja` | `que` | 0.75 | se le respondía con un **saludo** |
| `saldo` | `saludo` | 0.91 | ídem |
| `cuenta` | `buena` | 0.73 | ídem |
| `estafa` | `esta` | 0.80 | ídem |

Hoy los typos se resuelven con una **lista explícita** (`_GREETING_ABBREVIATIONS`)
y `_is_content_token` impide que cualquier palabra con señal bancaria entre por
similitud. Es menos elegante que un umbral, pero es auditable y no tiene falsos
positivos.

---

## 5. Camino de aclaración: el formulario es el último recurso

QA reportó 8 casos en un mes con el mismo patrón: cualquier cosa que el bot no
entendiera —`Bule`, `9+`, `Quitar bloqueo`, `hola, puedes escribirme en paisa`—
caía **directo al formulario PQR**. El cliente nunca tenía una segunda
oportunidad de explicarse.

Causa raíz: el enrutador **ya redactaba** un `clarification_message` para el
no-match y el código lo descartaba.

Comportamiento actual:

```
1er no-match  → mensaje FIJO del catálogo pidiendo reformular
                (routing_outcome = clarify_retry)
2º no-match consecutivo → formulario PQR (routing_outcome = no_match)
```

El contador vive en `captured_data` (por conversación, seguro con usuarios
concurrentes) y se reinicia con cualquier match, saludo o clarify.

**El mensaje no lo redacta el LLM.** Aunque el modelo entregue su
`clarification_message`, no se usa: el texto sale de `routing_retry_messages` en
`general_messages.yml`. Dos tests blindan la decisión, uno de ellos verificando
por introspección que la firma de la función no acepta la decisión del modelo.

---

## 6. Texto generado por el LLM que llega al cliente

Auditoría completa de las vías por las que texto del modelo podía llegar al
cliente:

| Vía | Estado |
|---|---|
| `clarification_message` del enrutador | **Eliminada** |
| `assistant_message` del enrutador | **Eliminada** (era parámetro muerto: el engine ya lo ignoraba) |
| `_build_default_routing_message` | **Eliminada** (29 líneas de código muerto que concatenaban el `rationale`) |
| Cierre de flujos guía (`generate_final_response_with_usage`) | **Apagado por defecto** con `LLM_CLOSURE_ENABLED=false` |

El cierre por LLM era la fuente del comportamiento observado en el que el bot
**imitaba el dialecto del cliente**: recibía la conversación completa como
contexto. Apagado, se conserva el mensaje determinista del YAML que ya venía
calculado, así que no hay hueco.

---

## 7. Presupuestos de tiempo — inconsistencia detectada

| Capa | Tiempo permitido |
|---|---|
| Turno completo (tope duro) | 120 s |
| Agente → `back_trx` | **10 s** (`trx_client.py`) |
| `back_trx` → ASO | **30 s** (`TRX_API_TIMEOUT`) |

**El timeout interno es tres veces mayor que el presupuesto externo.** El agente
abandona a los 10 s mientras `back_trx` sigue esperando hasta 30. Un timeout
interior nunca debe superar al exterior.

Se agrava porque **el TSEC del ASO no se cachea**: se solicita en cada operación
(6 puntos de llamada). Un paso del flujo puede encadenar TSEC + financial-overview
+ TSEC + operations + TSEC + detalle. Con el ASO respondiendo a 2 s por llamada ya
se supera el presupuesto de 10 s del agente.

**Pendiente**, en orden de impacto:
1. Cachear el TSEC durante la vida de la petición (elimina la mitad de las llamadas).
2. Corregir el anidamiento: `TRX_API_TIMEOUT` por debajo del timeout del agente.
3. Alinear la lectura del token con `back_data`, que cae al cuerpo de la respuesta
   si la cabecera `tsec` no viene; `back_trx` solo lee la cabecera.

---

## 8. Evaluación del ruteo

Existe un harness offline con **376 casos reales de producción**:

```bash
cd co_pqrs_back_agent && PYTHONPATH=src uv run python tests/eval_routing.py
```

Métricas actuales:

| Categoría | Resultado |
|---|---|
| Saludos | 32/32 (100%) |
| Meta-peticiones | 228/229 (99.6%) |
| Negativos del catálogo | 6/6 |
| Desambiguación | 5/5 |

Única falla: `hola, quieroradicar un pqr` (typo concatenado, requeriría partir
tokens).

> El harness mide **solo las capas deterministas**. La calidad del ruteo del LLM
> no está medida offline: casos como `cuota de manejo` o `paz y salvo hipotecario`
> tienen flujo en el catálogo y el modelo no los matcheó en producción. Medirlo
> requiere ejecutar el set contra el modelo.

---

## 9. Fallas conocidas de la suite (no son regresiones)

La suite del agente corre 386 tests con **12 fallas preexistentes**, estables y
documentadas: `permanencia_centrales`, `central_risk`, `test_prompt`,
`sold_portfolio`, `trx_movement_confirmation`, `trx_product_selector`,
`chat_turn_background`, `embargo`, `first_chat`, `guide_shortcut`, `id_msg_12`.

Cualquier número distinto de 12 indica una regresión introducida.

```bash
cd co_pqrs_back_agent && PYTHONPATH=src uv run python -m unittest discover -s tests -p 'test_*.py'
```
