# TXNR (Transacción No Reconocida) — Especificación del flujo (Fase 2)

> Fuente de verdad del flujo completo. Basado en la planeación del usuario
> (`Proyecto/planeaciontrxnoreconocida.md`). Nomenclatura integral bajo `2.4.0.1`.
> Rama de trabajo: `feature/PQRSdev`. No se hacen commits/push (los hace el usuario).

## 1. Arquitectura
- **`co_pqrs_back_agent`**: orquesta la conversación. Árbol en
  `src/domain/workflow/trx_no_reconocida/trx_no_reconocida.yml`; lógica en
  `application/chat/chat_service.py` (prefetch/bucle) y `workflow_actions.py`
  (render dinámico de botones); cliente HTTP en
  `infrastructure/persistence/trx_client.py`.
- **`co_pqrs_back_trx_noreconocida`**: validaciones de negocio (recurrencia,
  productos, vigencia, movimientos, detalle, bloqueos) consumiendo Postgres
  (`ada_info_detail`) y los ASOs. Toggle `ASO_SOURCE=simulator|real`.
- **`co_pqrs_back_trx_aso_simulator`** (NUEVO, F1): simula los ASOs para dev/E2E.

## 2. Menú de entrada
```
2.4.0  Menú (4 sucesos) — save: evento_trx_no_reconocida
├─ cambiazo               → 2.4.1  (Formulario PQR → satisfaction_check)
├─ hurto_o_perdida        → 2.4.2  (Formulario PQR → satisfaction_check)
├─ ingenieria_social      → 2.4.3  (Formulario PQR → satisfaction_check)
└─ compra_presencial_o_internet → 2.4.0.1
```

## 3. Recurrencia (2.4.0.1) — ACTION `consultar_recurrencia_salesforce`
Doble validación:
1. **Salesforce (ASO)**: `GET /salesforce-issue-tracker/v0/issues?targetUserId={doc_type}-{doc_number}`
   - `targetUserId` = `{personal_type con 0 a la izquierda}-{personal_id sin los 5 ceros a la izquierda}` (ambos se extraen de Postgres filtrando por `customer_id` que envía el front).
   - Tipos de documento (personal_type → salesforce): `A`, `00`(NUIP), `01`(CC), `02`(CE), `03`(NIT), `04`(TI), `05`(Pasaporte), `06`(NIT Ext), `07`(SOC), `08`(Fidecomisos), `09`(NIT PN), `0V`(PEP).
   - Criterio recurrencia: existe un `issue` cuyo `subject` corresponde a TXNR
     (lista configurable `SUBJECTS_TXNR`, p.ej. contiene "no reconoce"/"transaccion no reconocida")
     y con `creationDate` dentro de los **últimos 6 meses**.
2. **Recurrencia interna del bot**: si el cliente ya pasó por este flujo (op4) y
   quedó registrado, con tope `MAX_TRX_BOT_RECURRENCE=1` (config). Se lee del
   registro durable (índice `trx-no-reconocida-cases`).

Si hay recurrencia (cualquiera de las dos) → `2.4.0.pqr_recurrencia`
(Formulario PQR). Si no → botón "Continuar" → `2.4.0.1.1`.

TSEC: se genera con `POST /TechArchitecture/co/grantingTicket/V02`
(body con userID/consumerID/authenticationType/password); el TSEC viene en el
header `tsec` de la respuesta.

## 4. Árbol bajo 2.4.0.1 (nomenclatura integral, en aumento)
```
2.4.0.1.1  ¿Cuántas transacciones? (save trx_cantidad)
├─ 1/2/3      → 2.4.0.1.2
└─ mas_de_3   → 2.4.0.1.1.pqr  (Formulario PQR)

2.4.0.1.2  "Revisaremos una transacción a la vez" → empezar → 2.4.0.1.3

2.4.0.1.3  Confirmación de datos ("hasta 3 transacciones $35k–$500k…")
├─ Sí, continuar        → 2.4.0.1.4
└─ Finalizar conversación → satisfaction_check
```

### 2.4.0.1.4 — Verificación Postgres (productos vigentes)
Datos que consultamos de `ada_info_detail` (llave: `customer_id` del front):
- `customer_id`, `contract_id`, `origin_flag` (TDC/Pasivo),
  `contract_status_type_desc` (vigencia), `product_desc`, `card_flag`
  (¿tiene tarjeta asociada?), `card_brand` (VISA/MASTERCARD).

Filtros (todos deben cumplirse): producto **vigente** (`contract_status_type_desc`)
+ `origin_flag` en {TDC, Pasivo} + `card_flag = true`.
- Con productos → `2.4.0.1.5`.
- Sin productos → `2.4.0.1.4.exit`:
  > "Actualmente no tienes productos activos con nosotros para realizar esta
  > solicitud. Si deseas revisar el estado de tus productos o movimientos,
  > puedes ingresar a tu app BBVA. Hasta pronto." → satisfaction_check.

### 2.4.0.1.5 — Mostrar productos
> "Selecciona la cuenta o tarjeta en la que aparece la compra que no reconoces:"
> ▶️ {product_desc} • {últimos 4 del contract_id}  (uno por producto)

Al seleccionar → `2.4.0.1.6`.

### 2.4.0.1.6 — Rango de valor
> "Antes de continuar, selecciona el rango de valor de la transacción que deseas reportar:"
- Menor a $35.000  → `2.4.0.1.6.pqr`
- Entre $35.000 y $500.000 → `2.4.0.1.7`
- Mayor a $500.000 → `2.4.0.1.6.pqr`

`2.4.0.1.6.pqr`:
> "Para validar el reporte de estas compras no reconocidas, necesitamos la
> validación de nuestro equipo especializado. Completa el formulario…" ▶️ Formulario PQR

### 2.4.0.1.7 — Fecha + vigencia por franquicia
> "Escribe la fecha en la que se realizó la compra no reconocida usando el
> formato DD/MM/AAAA. …" (pregunta abierta; formato DD/MM/AAAA obligatorio).

Vigencia por `card_brand`: VISA → máx 180 días; MASTERCARD → máx 120 días.
Si `hoy - fecha_cliente` > máximo → `2.4.0.1.7.exit`; si no → `2.4.0.1.8`.

`2.4.0.1.7.exit`:
> "La fecha que ingresaste supera el plazo permitido por las franquicias… Te
> sugerimos contactar directamente al comercio… Hasta pronto." → satisfaction_check.

### 2.4.0.1.8 — Proceso ASOs (financial-overview + transactions)
1. Generar TSEC (grantingTicket).
2. `GET /financial-overview/v0/financial-overview?customer.id={customer_id}&contracts.productType=CARDS`
   → ubicar el contrato por `contract_id` (de Postgres) y extraer el **número de
   tarjeta (card_id/PAN)** asociado. Campos de match configurables
   (`FO_CONTRACT_MATCH_FIELD`, `FO_CARD_NUMBER_PATH`). En el JSON, el contrato de
   tarjeta trae `id`=PAN y `number`=últimos 4.
3. `GET /cards/v2/cards/{card_id}/transactions` con filtros (query params):
   `fromOperationDate`/`toOperationDate` (día del cliente en ISO-8601),
   `operationAmount.fromAmount=35000` / `operationAmount.toAmount=500000`,
   `moneyFlow.id=EXPENSE`, `operationAmount.id=CONTRACT_AMOUNT`. Si el filtro no
   funciona → traer sin filtros y filtrar localmente por fecha/rango/EXPENSE.
   - Capturar por movimiento: `id` (llave de cruce con detalle), `concept`
     (descripción), `operationAmounts` con `CONTRACT_AMOUNT` (valor), `operationDate`, `status`.
- Con movimientos → `2.4.0.1.9`.
- Sin movimientos → `2.4.0.1.8.return`:
  > "No encontramos compras registradas en la fecha seleccionada para este producto."
  - Elegir otra fecha → `2.4.0.1.7`
  - Seleccionar otro producto → `2.4.0.1.5`
  - Terminar consulta → satisfaction_check

### 2.4.0.1.9 — Mostrar movimientos (botones)
> "Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces:"
> ▶️ [Descripción] — $[valor] [DD/MM/AAAA]  (por cada movimiento)
> ▶️ No encuentro la transacción en este listado.
- Elige movimiento → `2.4.0.1.10`.
- "No encuentro…" → `2.4.0.1.9.exit`:
  > "Para continuar, puedes elegir otra fecha…"
  - Seleccionar una nueva fecha → `2.4.0.1.7`
  - No, finalizar → satisfaction_check

### 2.4.0.1.10 — Detalle del movimiento (operations)
1. TSEC.
2. `GET /cards/v2/operations?paginationKey=1&pageSize=100&operationDate={YYYYMMDD}&cardId={card_id}`
   → **match por el `id`** de la transacción capturado en `2.4.0.1.8`.
   Extraer del `operations[]`: `amountOperation`, `amountDonation`, `amountCommi`,
   `dateOper`, `hourOperation`, `descProvision`, `placeOperation`,
   `responseOperati`, `eci`, `eCard` (mapear rutas en config).
- Data encontrada → `2.4.0.1.11`.
- No encontrada → Formulario PQR (borde improbable).

### 2.4.0.1.11 — Confirmación del movimiento
> "Confirma los datos de la compra seleccionada.
> • [Descripción]  • Valor: $[]  • Fecha: [DD/MM/AAAA]
> • [Producto] terminado en ••••[últimos 4 del card_id]  ¿Es la transacción que deseas reportar?"
- Sí, continuar con el reporte → `2.4.0.1.12`
- No, ya reconozco → satisfaction_check
(Descripción=`descProvision` en `placeOperation`; valor=`amountDonation`;
fecha=`dateOper`+`hourOperation`; producto=últimos 4 del `card_id`.)

### 2.4.0.1.12 — Validación compra con TDC pendiente
Si `origin_flag = "TDC"` y `observations = "pendiente"` → `2.4.0.1.12.exit`
(guardar marca en la trazabilidad); si no → `2.4.0.1.13`.

> Corrección de Fabián (21/08): la señal es **`observations`**, no
> `responseOperati`. En el código se comprueba por **contenido** y no por
> igualdad, porque `observations` nunca vale «pendiente» a secas: en los datos
> reales es texto descriptivo (`OPER PENDIENTE POR CONFIRMAR COMERCIO`,
> `01 REVERSA GESTIONADA`, `OPER FINALIZADA CON EXITO |COMPRA INTERNET`). Con
> igualdad literal la regla no se cumpliría nunca.

`2.4.0.1.12.exit`:
> "Esta compra se encuentra actualmente en estado pendiente… Si la compra se
> confirma… podrás ingresar de nuevo a este chat… Que tengas un buen día."

### 2.4.0.1.13 — Iniciar investigación
> "Para continuar con tu proceso debemos iniciar con la investigación de tu caso,
> ¿quieres continuar con este proceso?"
- Sí → `2.4.0.1.15`
- No → satisfaction_check

### 2.4.0.1.15 — Tipo de bloqueo
> "Para continuar… es necesario bloquear definitivamente tu tarjeta, ¿quieres continuar con este bloqueo?"
- Sí, bloquear definitivamente → **proceso PERMANENTE** (`2.4.0.1.17` → `2.4.0.1.17.1` POST reemisión)
- No, bloquear temporalmente → **proceso TEMPORAL** (`2.4.0.1.16` → `2.4.0.1.16.1` PATCH activations off)

> RESUELTO (confirmado por el usuario): el ruteo es **semántico** — "definitivamente"
> va al ASO/proceso **permanente** y "temporalmente" al **temporal** (se corrige el
> cruce de numeración del doc original).

### 2.4.0.1.16 — (temporal) confirmación de apagado
> "Apagaremos temporalmente tu tarjeta… ¿Quieres continuar?"
- Sí, apagar temporalmente → `2.4.0.1.16.1`
- No, finalizar → satisfaction_check

`2.4.0.1.16.1` — Proceso apagado temporal:
1. TSEC.
2. `PATCH /cards/v1/cards/{card-id}/activations` body:
   `{"root":[{"id":"ON_OFF","isActive":false,"additionalInformation1":null,"additionalInformation2":0,"additionalInformation3":null,"additionalInformation4":null}]}`
- 200 → `2.4.0.1.16.2` ("Tu tarjeta terminada en •[últimos 4 del card-id] quedó apagada temporalmente…")
- !200 → `2.4.0.1.16.1.pqr` ("No hemos podido completar el bloqueo temporal… Formulario PQR")

### 2.4.0.1.17 — (permanente) confirmación de bloqueo definitivo
> "Al continuar, tu tarjeta actual quedará bloqueada definitivamente. Solicitaremos una nueva tarjeta, sin costo. ¿Quieres continuar?"
- Sí, bloquear y continuar → `2.4.0.1.17.1`
- No, finalizar → satisfaction_check

`2.4.0.1.17.1` — Proceso bloqueo permanente:
1. TSEC.
2. `POST /cards/v2/operations` con body de reemisión (mandatorio `card.cardId`
   = número completo de la tarjeta del financial-overview; `reason="Fraude"`, etc.).
- 201/200 → `2.4.0.1.17.2` ("Tu tarjeta terminada en •[últimos 4] quedó cancelada… Tu nueva tarjeta ya está en camino… [X] días hábiles" — X=10 por ahora) → Continuar → `2.4.0.1.18`
- !201/200 → `2.4.0.1.17.1.pqr` ("No hemos podido completar el bloqueo permanente… Formulario PQR")

### 2.4.0.1.18 — Aviso de revisión
> "Ahora revisaremos la información de la transacción para determinar cómo podemos gestionar tu solicitud." → Continuar → `2.4.0.1.19`

### 2.4.0.1.19 — Validaciones sobre el detalle (2.4.0.1.10)
- `eCard = false` → `2.4.0.1.19.1` (compra presencial con chip+clave, no devolución).
- `responseOperati = "Reversado"` → `2.4.0.1.19.2` (ya reversado / reembolso).
- `eci ∈ {null/vacío, 0, 1, 2, 3, 7}` → `2.4.0.1.19.pqr` (Formulario PQR).
- `eci` fuera de ese set → `2.4.0.1.20` (devolución automática).

`2.4.0.1.19.1`:
> "Revisamos la investigación de la transacción [descripción] por $[valor]… la
> compra se valida como autorizada… no es posible realizar la devolución…" → satisfaction_check.

`2.4.0.1.19.2`:
> "Te confirmamos que la compra por $[valor] ya fue devuelta a tu [producto]…"
> ▶️ Ver paso a paso para consultar movimientos (→ guía rápida ver movimientos)
> ▶️ Finalizar (→ satisfaction_check)

`2.4.0.1.19.pqr`:
> "Con la información disponible no podemos resolver esta solicitud en este canal…" ▶️ Formulario PQR

### 2.4.0.1.20 — Devolución automática + Excel/RPA (Tantia)
> "Validamos la información de tu solicitud y tu caso aplica para la devolución
> automática. Gestionaremos el abono… en un máximo de [X] días hábiles…" (X abierto).

Generar la fila del **Excel/RPA Tantia** (job diario 23:45; consolida lo del día
desde el índice durable; se deja en la ruta de Tantia — misma del
`conversation_extractor` con subcarpeta nueva). → `2.4.0.1.20.1`.

### 2.4.0.1.20.1 — Bucle multi-transacción
- Si el cliente eligió 2 o 3 transacciones → "¿Deseas reportar la siguiente transacción?"
  - Sí → `2.4.0.1.3`
  - No → satisfaction_check
- Si eligió solo 1 → satisfaction_check

## 5. ASOs (dev real) y toggle
Base URL real: `https://dev-arqaso.work.co.nextgen.igrupobbva:8050`
- Granting ticket (TSEC): `POST /TechArchitecture/co/grantingTicket/V02`
- Salesforce issues: `GET /salesforce-issue-tracker/v0/issues?targetUserId=01-80425247`
- Financial overview: `GET /financial-overview/v0/financial-overview?customer.id=...&contracts.productType=CARDS`
- Transactions: `GET /cards/v2/cards/{card_id}/transactions`
- Detalle: `GET /cards/v2/operations?pageSize=100&operationDate=YYYYMMDD&paginationKey=1&cardId=...`
- Bloqueo temporal (activations): `PATCH /cards/v1/cards/{card-id}/activations`
- Bloqueo permanente (reemisión): `POST /cards/v2/operations`

Toggle `ASO_SOURCE=simulator|real`. En simulador, base URL apunta al módulo
`co_pqrs_back_trx_aso_simulator`. Nunca apuntar bloqueo/reemisión al ASO real sin OK.

## 6. Shapes de respuesta (de los JSON de ejemplo)
- **financial-overview**: `data.contracts[]` con `id` (PAN 16 díg. para tarjetas),
  `number` (últimos 4), `product.name`, `productType="CARD"`,
  `subProductType.id="CREDIT_CARD"`, `detail.activations[].id="ON_OFF"`.
- **transactions**: `data[]` con `id` (largo, p.ej. `CO0013…098`), `contract.id`,
  `operationDate`, `moneyFlow.id` (EXPENSE/INCOME), `operationAmounts[]`
  (`ORIGIN_AMOUNT`/`CONTRACT_AMOUNT`, montos negativos si egreso), `status.id`
  (PENDING/SETTLED), `concept`.
- **operations (detalle)**: `data[].operations[]` con `id` (corto, p.ej. `101004037`),
  `amountOperation`, `amountCommi`, `amountDonation`, `dateOper`, `hourOperation`,
  `descProvision`, `placeOperation`, `responseOperati`, `eci`, y `eCard` (según doc;
  en el JSON de ejemplo real puede variar → se define en el simulador y se mapea en config).

> Riesgo conocido: el `id` de `transactions` (largo) y el `id` de `operations`
> (corto) difieren en los ejemplos. Por decisión del usuario se asume que son el
> mismo `id` de transacción (campo configurable `TX_OP_ID_FIELD`); se valida con
> el simulador.

## 7. Objetivos transversales
1. Modificar back_agent para este flujo.
2. Modificar el módulo trx (ASOs + Postgres).
3. Trazas/logs tipo centrales de riesgo (con debug de JSON).
4. Guardar la traza de dónde quedó / qué hizo el cliente.
5. Almacenar la info secuencial del cliente (ver ESTADO_Y_CONFIG.md).
6. Módulo simulador de ASOs (dev/E2E) con data suficiente por rama.
7. Toggle real/simulador por config.
8. Data de prueba artificial suficiente.
9. Tests de validación.
10. IaC OKD dev.

## 8. Puntos abiertos / resueltos
- RESUELTO: ruteo 1.15/1.16/1.17 = semántico (definitivo→permanente, temporal→temporal).
- RESUELTO: `card_flag` es columna NUEVA (fiel al doc), distinta de `card_active_flag`.
- RESUELTO: ruta Tantia = PVC `smb-pvc-tx` (subcarpeta nueva); orden de columnas = exacto del xlsx; X días hábiles OK.
- Pendiente F5: nombre exacto de subcarpeta/archivo Tantia y reglas de columnas auxiliares (Control Duplicados, Llave, ANS, Circuito).
