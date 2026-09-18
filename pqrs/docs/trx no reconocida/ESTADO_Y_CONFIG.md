# TXNR — Estado, persistencia y configuración global

## 1. Estado en vuelo por conversación (`trx_case_state`)
Se guarda como JSON dentro de `conversation.captured_data["trx_case_state"]`,
que **ya se persiste por turno** en el índice de conversaciones (OpenSearch).
No usar variables globales de proceso (rompe con multi-pod/HPA y no es apto prod).

Esquema (todas opcionales, se van llenando por nodo):
```json
{
  "entered_at": "ISO-8601",
  "recurrence": {"salesforce": false, "bot_count": 0, "redirected_pqr": false},
  "cantidad": 2,
  "tx_index": 1,
  "producto": {
    "contract_id": "...", "origin_flag": "TDC|Pasivo",
    "product_desc": "...", "card_brand": "VISA|MASTERCARD",
    "card_flag": true, "last_four_contract": "1234"
  },
  "fecha": "DD/MM/AAAA",
  "vigencia": {"franquicia": "VISA", "max_dias": 180, "dias": 12, "vencida": false},
  "card_id": "4912...4979",
  "movimiento": {"id": "...", "descripcion": "...", "valor": 120000, "fecha": "..."},
  "detalle": { "...": "campos de operations (descProvision, placeOperation, dateOper, hourOperation, responseOperati, eci, eCard, amountDonation) ..." },
  "validaciones": {"pendiente_tdc": false, "eci": "5", "ecard": true, "reversado": false, "resultado": "devolucion_automatica|pqr|no_devolucion"},
  "bloqueo": {"tipo": "temporal|permanente|null", "resultado": "ok|error|null"},
  "desenlace": "satisfaction_check|pqr|exit|devolucion",
  "por_transaccion": [ { "...": "copia por cada tx del bucle (1..N)" } ]
}
```

## 2. Registro durable (cross-sesión, sin TTL de 30 días)
El control-table tiene `ttl_days=30`. Para NO perder el rastro (recurrencia-bot,
"llegó hasta bloqueo", etc.) usamos un **índice OpenSearch dedicado
`trx-no-reconocida-cases` SIN ILM/TTL** + **copia durable en el bucket (MinIO)**.

Documento por caso (id = `{customer_id}_{YYYYMMDD}_{tx_index}` o similar):
```json
{
  "customer_id": "...", "conversation_id": "...",
  "created_at": "ISO-8601", "updated_at": "ISO-8601",
  "milestones": ["entered_op4","reached_block","completed_report"],
  "recurrence_bot_count": 1,
  "outcome": "devolucion_automatica|pqr|exit|...",
  "trx_case_state_snapshot": { "...": "copia del estado final" }
}
```
- Se escribe en hitos: entró a op4, llegó a bloqueo, completó reporte/devolución.
- La **recurrencia-bot** lee este índice: si el cliente ya tiene un caso con hito
  relevante dentro de la ventana y `recurrence_bot_count >= MAX_TRX_BOT_RECURRENCE`
  (=1), la próxima entrada se redirige a PQR.
- Retención: el índice NO tiene política de borrado a 30 días (a diferencia de
  `client-control-table`). La copia en bucket es permanente para auditoría/RPA.

## 3. Trazas / logs (patrón centrales de riesgo)
Reutilizar el patrón de trazas de `centrales_de_riesgo` (agente → error_handler →
bucket) para dejar el **paso a paso** del cliente y el **debug de cada respuesta
ASO** (enmascarada/truncada). Un solo log/traza consolidada por turno indica
"dónde quedó / qué hizo".

## 4. Configuración global (variables — configmap/env)

> **Valores verificados contra los configmaps de dev el 2026-08-24.**
> Donde prod difiere, se indica.

### 4.1 Agente (`IaC/backend/co_pqrs_back_agent/01-configmap.yaml`)
| Variable | dev | prod | Uso |
|---|---|---|---|
| `TRX_SERVICE_URL` | `...pqr-genai-dev...:8004` | `...pqr-genai...:8004` | Back de TXNR |
| `TRX_FLOW_ENABLED` | `true` | **`false`** | Portón: `false` manda las 4 opciones al formulario PQR |
| `TRX_CANARY_TOKEN` | `BLUE-TRX-PILOTO-2026` | igual | Token que abre el flujo por conversación |
| `TRX_CASES_INDEX` | `trx-no-reconocida-cases` | igual | Índice durable, sin TTL |
| `MAX_TRX_BOT_RECURRENCE` | `20` | igual | Tope de entradas al flujo por cliente |
| `DIAS_HABILES_TARJETA` | `5` | igual | Días hábiles para la tarjeta |
| `DIAS_HABILES_DEVOLUCION` | `40` | igual | Días hábiles de la devolución |
| `VIGENCIA_VISA_DIAS` | `180` | igual | Vigencia VISA |
| `VIGENCIA_MASTER_DIAS` | `120` | igual | Vigencia MASTER |
| `GUARDRAIL_JUDGE_ENABLED` | `true` | `true` | Juez de alcance por LLM |
| `LLM_CLOSURE_ENABLED` | `false` | `false` | `false` = el cierre de flujos guía **no** lo redacta el LLM |

### 4.2 Back TXNR (`IaC/backend/co_pqrs_back_trx_noreconocida/01-configmap.yaml`)
| Variable | dev | prod | Uso |
|---|---|---|---|
| `TRX_PRODUCTS_SOURCE` | `postgres` | `postgres` | Origen de productos |
| `TRX_ALLOW_MOCKS` | `true` | **`false`** | Interruptor global anti-mock |
| `TRX_SALESFORCE_SOURCE` | `mock` | **`aso_real`** | Recurrencia de Salesforce |
| `ASO_SOURCE` | `simulator` | **`real`** | En prod no existe el simulador |
| `ASO_SIMULATOR_URL` | service del simulador | **comentada** | — |
| `ASO_REAL_URL` | `dev-arqaso.work...:8050` | `arqaso.live...:8000` | Pasarela ASO |
| `TRX_API_TIMEOUT` | `30` | `30` | ⚠️ Ver §4.5 |
| `TRX_API_VERIFY_SSL` | `false` | `false` | Verificación TLS |
| `ASO_TRACE_FULL_BODY` | `true` | **`false`** | Volcado del cuerpo en trazas |
| `TRX_POSTGRES_TABLE` | `ada_info_detail` | igual | Tabla de productos |
| `DB_HOST` | `postgresql.pqr-genai-dev...` | `postgresql.pqr-genai...` | Postgres |

Rutas del ASO (`ASO_FO_PATH`, `ASO_TRANSACTIONS_PATH`, `ASO_OPERATIONS_PATH`,
`ASO_SALESFORCE_PATH`, `ASO_ACTIVATIONS_PATH`, `ASO_REISSUANCE_PATH`) son
configurables para no depender de cambios en el contrato.

### 4.3 Exportador CSV Tantia
Ver [`CSV_TANTIA.md`](./CSV_TANTIA.md) §4. Cambios clave respecto a lo que decía
antes este documento:

| | Antes | Ahora |
|---|---|---|
| `TANTIA_CRON` | `45 23 * * *` (diario) | **`0 16 * * 1-5`** (días hábiles) |
| Subcarpeta | pendiente | **`ficheros_rpa`** |
| Formato | Excel | **CSV `;`** |

### 4.4 Filtro de productos vigentes
`aso_rules.filtrar_productos` acepta en `contract_status_type_desc` tanto
**`VIGENTE`** como **`ACTIVO`**. La Postgres real trae `ACTIVO`; los seeds de dev
se sembraron con `VIGENTE`. Se aceptan ambos porque el peor error aquí es dejar sin
productos a un cliente que sí los tiene. La comparación es en mayúsculas y sin
espacios. Cualquier otro estado (`CANCELADO`, `INACTIVO`, vacío) queda excluido.

### 4.5 Advertencia sobre los timeouts
| Capa | Tiempo |
|---|---|
| Agente → back_trx | **10 s** |
| back_trx → ASO | **30 s** |

El timeout interno supera al externo, así que el agente abandona antes de que
`back_trx` termine. Agravado porque el TSEC no se cachea y se pide en cada
operación. Pendiente de corregir — ver
[`../ARQUITECTURA_BACK_AGENT.md`](../ARQUITECTURA_BACK_AGENT.md) §7.
