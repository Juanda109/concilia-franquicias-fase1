# TXNR — Datos de prueba en Postgres (`ada_info_detail`)

## 1. Reconciliación de schema
La DDL actual (`co_pqrs_back_load_ada_data/main.py`) tiene exactamente las 63
columnas del SELECT del usuario. Los campos que el flujo consume:
`customer_id`, `contract_id`, `origin_flag`, `contract_status_type_desc`,
`product_desc`, `card_brand`, `personal_type`, `personal_id`, `last_four_pan_id`
**ya existen**. El único que falta es **`card_flag`**.

- `card_active_flag` (BOOLEAN, ya existe) = la tarjeta está *activa* (estado).
- `card_flag` (FALTA) = el contrato *tiene una tarjeta asociada* (estructural, filtro del doc).
Son semánticamente distintos → **se agrega `card_flag BOOLEAN`**.

> No hay un "segundo" campo faltante para este flujo: todos los demás que el flujo
> usa ya están en el schema. (Si el usuario prefiere reutilizar `card_active_flag`
> como filtro en vez de agregar `card_flag`, es cambio de 1 línea en el servicio;
> dejamos `card_flag` por fidelidad al doc.)

### Cambio de schema (agregar `card_flag`)
```sql
ALTER TABLE public.ada_info_detail ADD COLUMN IF NOT EXISTS card_flag BOOLEAN;
```
Y en la DDL del job `co_pqrs_back_load_ada_data/main.py` (F2) agregar
`card_flag BOOLEAN,` en `TABLE_COLUMNS_DDL`.

## 2. IDs canónicos (congruentes con el simulador F1)
Estos `customer_id` / `contract_id` / `card_id (PAN)` DEBEN coincidir con la data
del simulador (`CLIENTES_SIMULADOR.md`). El enlace Postgres→financial-overview se
hace por `contract_id` (campo configurable `FO_CONTRACT_MATCH_FIELD`), y el
simulador devuelve el `card_id` (PAN) asociado.

| Cliente | customer_id | doc (type-num) | contract_id (Postgres) | card_id/PAN (sim FO) | brand | origin | Fecha a ingresar | Nodo esperado / valida |
|---|---|---|---|---|---|---|---|---|
| A recurrencia | 1013634958 | 01-1013634958 | 00131001201300001 | 4912680517944979 | VISA | TDC | (no aplica) | 2.4.0.pqr_recurrencia (salesforce TXNR ≤6m) |
| B sin productos | 1013634959 | 01-1013634959 | 00131002201300002 | (n/a) | VISA | TDC | (no aplica) | 2.4.0.1.4.exit (card_flag=false / no vigente) |
| C devolución auto | 1013634960 | 01-1013634960 | 00131003201300060 | 4912680517940060 | VISA | TDC | 06/08/2026 | 2.4.0.1.20 (eci no contracargable, eCard=true) |
| D eci contracargable | 1013634961 | 01-1013634961 | 00131004201300061 | 4912680517940061 | VISA | TDC | 06/08/2026 | 2.4.0.1.19.pqr (eci ∈ {0,1,2,3,7}) |
| E eCard=false | 1013634962 | 01-1013634962 | 00131005201300062 | 4912680517940062 | VISA | TDC | 06/08/2026 | 2.4.0.1.19.1 (presencial) |
| F reversado | 1013634963 | 01-1013634963 | 00131006201300063 | 4912680517940063 | VISA | TDC | 06/08/2026 | 2.4.0.1.19.2 (reversado) |
| G pendiente-TDC | 1013634964 | 01-1013634964 | 00131007201300064 | 4912680517940064 | VISA | TDC | 06/08/2026 | 2.4.0.1.12.exit (pendiente) |
| H fecha vencida | 1013634965 | 01-1013634965 | 00131008201300065 | 5412680517940065 | MASTERCARD | TDC | 01/01/2025 (>120 días) | 2.4.0.1.7.exit (fecha > vigencia) |
| I sin movimientos | 1013634966 | 01-1013634966 | 00131009201300066 | 4912680517940066 | VISA | TDC | 06/08/2026 (cualquiera) | 2.4.0.1.8.return (sin movs esa fecha) |

`J (mas_de_3)`: cualquier cliente vigente (p.ej. C) eligiendo "Más de 3" → `2.4.0.1.1.pqr`.

## 3. INSERTs de prueba
Solo se pueblan las columnas relevantes (el resto queda NULL). Fecha de prueba
recomendada para clientes con movimientos: **la que el simulador tenga cargada**
(ver CLIENTES_SIMULADOR.md, p.ej. `06/08/2026`). Para H usar una fecha vieja
(> 180 días) para forzar vencida.

```sql
-- Requiere: ALTER TABLE ... ADD COLUMN card_flag BOOLEAN;  (ver §1)

INSERT INTO public.ada_info_detail
  (key_id, contract_id, contract_status_type, contract_status_type_desc,
   card_type, card_type_desc, card_brand, card_status_type, last_four_pan_id,
   card_active_flag, card_flag, origin_flag, customer_id, personal_id,
   personal_type, personal_type_desc, customer_name, first_last_name,
   second_last_name, customer_mail, commercial_product_desc, product_desc,
   seizure_flag, audit_date)
VALUES
 -- A recurrencia (VISA/TDC vigente)
 ('KTRXA','00131001201300001','01','VIGENTE','M','CREDITO','VISA','1','4979',
  true,true,'TDC','1013634958','1013634958','1','Cedula Ciudadania',
  'CLIENTE A','A','TRX','a@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now()),
 -- B sin productos válidos (card_flag=false)
 ('KTRXB','00131002201300002','01','VIGENTE','M','CREDITO','VISA','1','0002',
  true,false,'TDC','1013634959','1013634959','1','Cedula Ciudadania',
  'CLIENTE B','B','TRX','b@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now()),
 -- C devolución automática
 ('KTRXC','00131003201300060','01','VIGENTE','M','CREDITO','VISA','1','0060',
  true,true,'TDC','1013634960','1013634960','1','Cedula Ciudadania',
  'CLIENTE C','C','TRX','c@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now()),
 -- D eci contracargable -> PQR
 ('KTRXD','00131004201300061','01','VIGENTE','M','CREDITO','VISA','1','0061',
  true,true,'TDC','1013634961','1013634961','1','Cedula Ciudadania',
  'CLIENTE D','D','TRX','d@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now()),
 -- E eCard=false -> presencial
 ('KTRXE','00131005201300062','01','VIGENTE','M','CREDITO','VISA','1','0062',
  true,true,'TDC','1013634962','1013634962','1','Cedula Ciudadania',
  'CLIENTE E','E','TRX','e@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now()),
 -- F reversado
 ('KTRXF','00131006201300063','01','VIGENTE','M','CREDITO','VISA','1','0063',
  true,true,'TDC','1013634963','1013634963','1','Cedula Ciudadania',
  'CLIENTE F','F','TRX','f@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now()),
 -- G pendiente-TDC
 ('KTRXG','00131007201300064','01','VIGENTE','M','CREDITO','VISA','1','0064',
  true,true,'TDC','1013634964','1013634964','1','Cedula Ciudadania',
  'CLIENTE G','G','TRX','g@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now()),
 -- H fecha vencida (MASTERCARD, vigencia 120)
 ('KTRXH','00131008201300065','01','VIGENTE','M','CREDITO','MASTERCARD','1','0065',
  true,true,'TDC','1013634965','1013634965','1','Cedula Ciudadania',
  'CLIENTE H','H','TRX','h@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now()),
 -- I sin movimientos en la fecha
 ('KTRXI','00131009201300066','01','VIGENTE','M','CREDITO','VISA','1','0066',
  true,true,'TDC','1013634966','1013634966','1','Cedula Ciudadania',
  'CLIENTE I','I','TRX','i@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now());
```

## 4. Notas
- `personal_type='1'` en Postgres → para Salesforce `targetUserId` se normaliza a
  `01` (0 a la izquierda) y `personal_id` se usa sin los 5 ceros a la izquierda.
- `contract_status_type_desc='VIGENTE'` es el valor que el filtro de productos
  considera vigente (confirmar el catálogo real de `contract_status_type_desc`).
- Para B: `card_flag=false` fuerza el `2.4.0.1.4.exit`. También se puede probar con
  `contract_status_type_desc` NO vigente.
- Las diferencias de desenlace C–G dependen de la data del **simulador** (eci,
  eCard, responseOperati) por `card_id`; en Postgres son productos VISA/TDC vigentes
  equivalentes. Ver `CLIENTES_SIMULADOR.md`.


---

## 5. Clientes de prueba REALES del usuario (Fase 2)
Data del simulador ya creada (financial_overview / transactions / operations) y
verificada por E2E (desenlace por `card_id`/últimos-4). Fecha de la compra: **06/08/2026**.

| Cliente | doc | customer_id | PAN (card_id, sim FO) | last4 | brand | origin | Fecha a ingresar | Desenlace |
|---|---|---|---|---|---|---|---|---|
| Tres | CC 1216963399 | 98787954 | 4916555123453399 | 3399 | VISA | TDC | **06/08/2026** | **DEVOLUCIÓN** (eci=5, eCard=true, Exitosa) |
| Uno  | CE 1025079    | 10482895 | 4916555110255079 | 5079 | VISA | TDC | **06/08/2026** | PRESENCIAL (eCard=false) |
| Dos  | CC 17389461   | 01576905 | 4916555117389461 | 9461 | VISA | TDC | **06/08/2026** | PQR (eci=1 contracargable) |

> `01576905` tiene cero a la izquierda: la FO se resuelve por `customer_id` exacto.
> Se dejó también `financial_overview/1576905.json` (alias sin el cero) por si el
> canal normaliza el id. Enlace Postgres→FO por **últimos-4** (`last_four_pan_id` ==
> FO `number`) → `card_id` = FO `id` (PAN).

### INSERTs (requiere `ALTER TABLE ... ADD COLUMN card_flag BOOLEAN;` — ver §1)
```sql
INSERT INTO public.ada_info_detail
  (key_id, contract_id, contract_status_type, contract_status_type_desc,
   card_type, card_type_desc, card_brand, card_status_type, last_four_pan_id,
   card_active_flag, card_flag, origin_flag, customer_id, personal_id,
   personal_type, personal_type_desc, customer_name, first_last_name,
   second_last_name, customer_mail, commercial_product_desc, product_desc,
   seizure_flag, audit_date)
VALUES
 -- TRES: devolución automática (CC 1216963399)
 ('KTRX3','00130067000200943399','01','VIGENTE','M','CREDITO','VISA','1','3399',
  true,true,'TDC','98787954','1216963399','1','Cedula Ciudadania',
  'CLIENTE PRUEBA TRES','PRUEBA','TRES','tres@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now()),
 -- UNO: presencial (CE 1025079)   [personal_type de CE: confirmar catálogo ADA]
 ('KTRX1','00130067000200945079','01','VIGENTE','M','CREDITO','VISA','1','5079',
  true,true,'TDC','10482895','1025079','4','Cedula Extranjeria',
  'CLIENTE PRUEBA UNO','PRUEBA','UNO','uno@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now()),
 -- DOS: PQR eci contracargable (CC 17389461)
 ('KTRX2','00130067000200949461','01','VIGENTE','M','CREDITO','VISA','1','9461',
  true,true,'TDC','01576905','17389461','1','Cedula Ciudadania',
  'CLIENTE PRUEBA DOS','PRUEBA','DOS','dos@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now());
```

Notas:
- `customer_id` va como **texto** (respeta el cero a la izquierda de `01576905`).
- `card_flag=true` + `contract_status_type_desc='VIGENTE'` + `origin_flag='TDC'`
  hacen que `filtrar_productos` los deje pasar (nodo productos → selector).
- `customer_name`/`customer_mail` alimentan el Excel Tantia (Nombre del Titular / Correo de Alerta).
- **CE (Cédula de Extranjería)**: el código `personal_type='4'` es tentativo; ajustar
  al catálogo real de ADA. No afecta el desenlace (el flujo enruta por `card_id`/últimos-4).
