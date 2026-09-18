# Plan — Módulo Transacción No Reconocida (TXNR)

Rama: `feature/trxnoreconocida`. Estado: **plan para VoBo** (no implementado aún). client de prueba 1013634958

./scripts/local_stack.sh hybrid --engine podman --insecure

./scripts/local_stack.sh down

python scripts/run_local.py 
python scripts/run_local.py down
## 1. Objetivo y alcance
Construir el flujo guiado de “transacción no reconocida” con dos módulos que se
hablan como back_agent ↔ back_data:

- **back_agent** orquesta la conversación (UI: botones de selección única + texto
  abierto) y llama a **back_trx** por HTTP.
- **co_pqrs_back_trx_noreconocida** integra los ASO (Salesforce, Financial
  Overview) y Postgres (ADA), con **modo mock** para probar sin ASO de dev.

**Fase 1 (este alcance):** llegar hasta **listar los movimientos del día** para que
el cliente elija (paso ~13/14 del diagrama), **todo mockeado**. Deja el esqueleto
completo con textos (hoja *Agente TX Textos quemados V.2*) y todos los off-ramps.
**Fase 2 (después):** de la selección del movimiento en adelante (descripción,
pendiente TDC, proteger/bloquear tarjeta, investigación, abono/formulario).

## 2. Nomenclatura (aprobada)
- Menú de entrada: **`2.4.0`**.
- Cada **llamada a backend** es incremental: `2.4.0.1`, `2.4.0.2`, `2.4.0.3`, …
- Pasos de UI intermedios cuelgan como sub-nodos (`2.4.0.3.1` selección de
  producto), espejando centrales (`1.4.1.x`).
- Ramas de radicación directa: `2.4.1` (cambiazo), `2.4.2` (hurto/pérdida),
  `2.4.3` (ingeniería social) → botón **Formulario PQR** → `satisfaction_check`.

## 3. Identidad → `targetUserId`
- `targetUserId = {docType}-{docNumber}`.
- `docNumber`: se le quita el `0` inicial. `personal_id`: se le quitan los 5 ceros
  iniciales. La consulta se arma por el `customer` que envía el front.
- Tabla docType: `A` T. Diplomática · `00` NUIP · `01` Cédula · `02` Céd.
  Extranjería · `03` NIT · `04` T. Identidad · `05` Pasaporte · `06` NIT Ext · …

## 4. Contrato ASO (del Postman)
- **TSEC:** `POST https://dev-arqaso…:8050/TechArchitecture/co/grantingTicket/V02`
  (userID `ZM12035`, consumerID `12000035`, authType `04`) → header `tsec`.
- **Recurrencia (Salesforce):** `GET /salesforce-issue-tracker/v0/issues?targetUserId={docType-docNumber}`
  (y `…/issues/{issueId}` para detalle). Se valida tipología ≈ “Transacción no
  reconocida” en los **últimos 6 meses**.
- **Movimientos (Financial Overview):** `GET /accounts/v2/accounts/{contractId}/transactions`
  y `GET /cards/v2/cards/{contractId}/transactions`.
- Los config maps ya traen estos endpoints (`COMMERCIAL_INFO_*` / `TRX_*`).

## 5. Estrategia de mock (natural para migrar a Postgres/ASO)
Como back_data (`*_SOURCE = api|mock`). Variables de fuente en back_trx:
- `TRX_SALESFORCE_SOURCE=mock` → usa `data/aso_salesforce.json` (recurrencia).
- `TRX_PRODUCTS_SOURCE=postgres|mock` → productos ADA (tabla `ada_info_detail`).
- **NUEVA** `TRX_MOVEMENTS_SOURCE=mock|aso` → movimientos por fecha.
  Mock = consulta a un JSON local `data/movimientos_mock.json` (simula la BD),
  para que al pasar a `postgres`/`aso` el cambio sea solo de variable.

### Esquema propuesto del mock de movimientos (estilo ADA; campos a ajustar luego)
Nueva “tabla” lógica `trx_movements` (por ahora JSON):
```
customer_id, personal_id, personal_type,       -- identidad (como ada_info_detail)
contract_id, contract_id_last_4, product_type, -- producto (TDC / CUENTA_AHORROS / CUENTA_CORRIENTE)
card_bin_number, card_franchise,               -- VISA / MASTER (para vigencia contracargo)
movement_id, movement_date, movement_datetime,
amount, currency,                              -- COP
description, merchant_name,
movement_type,                                 -- DEBITO / ABONO (se listan inclusive los abonos)
movement_status,                               -- POSTED / PENDING (pendiente TDC = Tx MC30)
channel,                                       -- PRESENCIAL / INTERNET / CHIP
authorization_code
```
Vigencia contracargo (paso 11): VISA 180 días · MASTER 120 días (tabla BIN, mock).

## 6. Intro, valor y "una transacción a la vez" (paso 5–7)  [DECIDIDO]
Front: botón de selección única + texto abierto. Alineado a V.2:
1. `2.4.0.1.1` INTRO/confirmación (V.2 16): "hasta 3 tx de $35k–$500k; confirmas
   que tus datos/dirección están actualizados… ¿Continuar?" → **Sí, continuar** /
   **Finalizar conversación**.
2. `2.4.0.1.2` "¿Cuántas transacciones? 1/2/3/Más de 3" (V.2 5.0). **Más de 3 → PQR** (V.2 7.0).
3. `2.4.0.1.3` "Revisaremos **una transacción a la vez**… ▶️ Empezar ahora" (V.2 6.0).
── Por CADA transacción (bucle i = 1..N): ──
4. **Valor = rango por BOTONES** (V.2 22): `<$35k / entre $35k–$500k / >$500k`.
   - **Fuera de rango** → **Formulario PQR** para ESA transacción; si quedan más,
     botón **[Continuar con la siguiente transacción]**; si no, **Finalizar**.
   - “entre” → continúa.
5. **Selección de PRODUCTO** (va **después** del valor, por transacción): productos
   vigentes; es el producto sobre el que se consultan los movimientos. Sin
   productos → mensaje de cierre.
6. **Fecha = texto `DD/MM/AAAA`** (V.2 10.0). **Vigencia:** desde esa fecha se
   cuentan **VISA 180 / MASTER 120** días atrás; si se pasó → “venció el plazo”
   (V.2 11.0).
7. **Movimientos por PRODUCTO + FECHA** (V.2 13.0) → lista de botones para
   seleccionar. El rango de valor es **compuerta de elegibilidad**, no filtro del
   listado (a confirmar si además quieres resaltar/filtrar por valor).

Ajustar `evaluar_transaccion_individual` a “rango por transacción” + “>3 → PQR”.

## 7. ÁRBOL 1 — hasta listar/confirmar movimientos (Fase 1)
```
2.4.0  Menú "¿fuiste víctima de…?"  (save: evento_trx_no_reconocida)
  ├─ Cambiazo/Hurto/Ingeniería social → 2.4.1 / 2.4.2 / 2.4.3 [Formulario PQR] → satisfaction
  └─ Compra presencial/internet → 2.4.0.1
2.4.0.1   [BACK_TRX] recurrencia Salesforce (tsec + issues?targetUserId; TXNR ≤6m)   (V.2 4.0)
  ├─ SÍ recurrencia → [Formulario PQR] → satisfaction
  └─ NO → 2.4.0.1.1
2.4.0.1.1 INTRO/confirm → (Finalizar → fin) / (Sí, continuar → 2.4.0.1.2)             (V.2 16)
2.4.0.1.2 "¿Cuántas transacciones? 1/2/3/Más de 3"                                    (V.2 5.0)
  ├─ Más de 3 → [Formulario PQR]                                                      (V.2 7.0)
  └─ N∈{1,2,3} → 2.4.0.1.3
2.4.0.1.3 "Revisaremos una transacción a la vez… ▶️ Empezar ahora"                    (V.2 6.0)
╔═ BUCLE por transacción  i = 1..N ══════════════════════════════════════════════════╗
║ 2.4.0.1.4 Valor (botones): <$35k / entre $35k–$500k / >$500k                        (V.2 6.0/22)
║   ├─ <35k o >500k → [Formulario PQR de esa tx] + (si quedan) [Continuar con la siguiente] / Finalizar
║   └─ entre → 2.4.0.2
║ 2.4.0.2   [BACK_TRX] productos vigentes activos (excluye card_status_type=6)        (V.2 8.0)
║   ├─ sin productos → msg "no hay productos vigentes" → fin                          (V.2 9.0)
║   └─ con productos → 2.4.0.2.1 selecciona producto                                  (V.2 9.0)
║ 2.4.0.2.2 Fecha (texto DD/MM/AAAA)                                                  (V.2 10.0)
║ 2.4.0.3   [BACK_TRX] vigencia (VISA180/MASTER120 desde la fecha) + movimientos      (V.2 11.0/13.0)
║   ├─ fuera de plazo → msg "venció el plazo" → [Elegir otra fecha / Fin]             (V.2 11.0)
║   ├─ sin movimientos → msg → [Otra fecha / Otro producto / Terminar]                (V.2 13.0)
║   └─ con movimientos → ★ LISTA (botones: [desc — $valor — fecha] ×N + "No encuentro…")  ← META FASE 1  (V.2 13.0)
║ 2.4.0.3.1 selecciona movimiento → CONFIRMACIÓN "¿Es la tx a reportar?" (Sí / No, ya la reconozco)  (V.2 14.0)
╚═ al confirmar (Sí) → Fase 2 ;  luego siguiente transacción i+1 ═════════════════════╝
```

## 8. ÁRBOL 2 — después del paso 14 (Fase 2)
```
2.4.0.6  Lista de movimientos → "¿el movimiento está en los mostrados?"                (diag. 14)
  ├─ NO → "no es posible continuar; revisa extractos; vuelve a iniciar" → fin
  └─ SÍ → 2.4.0.6.1 selecciona movimiento → 2.4.0.7
2.4.0.7  [BACK_TRX] descripción clara de la tx por tipo de producto (TDC: cards MCDTCRD / cuenta: accounts)
         → "¿movimiento pendiente en TDC?"                                             (diag. 12, V.2 12.0)
  ├─ pendiente (Tx MC30, ≤7 días cruce) → texto quemado "hasta 7 días…" → fin
  └─ no pendiente → 2.4.0.8 "¿Reconoces este movimiento?" (Sí/No)                       (V.2 14.0)
      ├─ SÍ reconoce → cierre "gracias" → fin
      └─ NO reconoce → PROTEGER TARJETA (apagar temporal / bloquear definitivo + reexpedición)  (V.2 19–21)
          → 2.4.0.9 INVESTIGACIÓN (V.2 22) → resultado:
             • chip/punto físico (23)     → mensaje + PQR/cierre
             • anulada/reversada (24)      → abono (28/29)
             • no elegible automático (25) → Formulario PQR (26)
             • elegible automático (27)    → abono exitoso/fallido (28/29)
          → fin
```

## 9. Componentes a construir (Fase 1)
**back_trx (`co_pqrs_back_trx_noreconocida`):**
1. Exponer en `trx_router` los endpoints por paso: recurrencia (✓), evaluar-tx,
   productos-activos, movimientos-por-fecha. Contrato `TrxResult` (status/id_message/step/data).
2. `TRX_MOVEMENTS_SOURCE` + `data/movimientos_mock.json` (esquema §5).
3. Parser real de `aso_salesforce.json` por tipología TXNR ≤6 meses (refinar).
4. Vigencia por franquicia (VISA 180 / MASTER 120) desde BIN (mock).
5. Ajustar `evaluar_transaccion_individual` a la regla por-tx §6.

**back_agent:**
6. Completar `trx_no_reconocida.yml` con el Árbol 1 y la nomenclatura.
7. Acciones en `workflow_actions.py` que llamen back_trx (vía `trx_service_url`),
   con fallback in-process ya existente.
8. Bucle de captura de N valores (paso 6) y lista dinámica de productos/movimientos.
9. Textos exactos desde la hoja *Agente TX Textos quemados V.2*.

## 10. Preguntas abiertas / a confirmar
- Regla exacta de valor (por-tx $35k–$500k confirmado; ¿se descarta la de acumulado?).
- ¿Las tx fuera de rango se **excluyen** del reporte o el flujo continúa igual? (hoy: continúa e informa).
- Campos finales del esquema de movimientos (los de §5 son propuesta; se ajustan luego).
- Textos definitivos (se toman de V.2; confirmar los IDs 5.0–14.0).
