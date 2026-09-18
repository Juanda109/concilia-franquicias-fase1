# TXNR — Clientes de prueba del simulador (E2E) y cobertura

> Congruente con `DATOS_PRUEBA_POSTGRES.md`: mismos `customer_id`, `contract_id`
> (por últimos 4 = `last_four_pan_id`) y `card_id (PAN)`. El módulo trx (F2) enlaza
> Postgres→financial-overview por los **últimos 4** (`contracts[].number` ==
> `last_four_pan_id`) y toma el `card_id` de `contracts[].id`. Fecha de prueba con
> movimientos: **06/08/2026**.

## Matriz de clientes
> **Fecha a ingresar** = la que el cliente debe escribir en `2.4.0.1.7` para que el
> flujo traiga (o no) movimientos. Con movimientos: **06/08/2026**. H fuerza vencida
> con una fecha vieja; A/B salen antes de pedir fecha.

| Cliente | customer_id | card_id (PAN) | brand | Escenario simulador | Fecha a ingresar | Nodo final esperado |
|---|---|---|---|---|---|---|
| A | 1013634958 | — | VISA | Salesforce subject "…no reconoce…" reciente (≤6m) | (no aplica: sale en recurrencia) | `2.4.0.pqr_recurrencia` |
| B | 1013634959 | — | VISA | (Postgres) `card_flag=false` → sin productos válidos | (no aplica: sale sin productos) | `2.4.0.1.4.exit` |
| C | 1013634960 | 4912680517940060 | VISA | 3 movs; detalle eci=5, eCard=true, Exitosa | **06/08/2026** | `2.4.0.1.20` (devolución) |
| D | 1013634961 | 4912680517940061 | VISA | 1 mov; eci=1 (contracargable) | **06/08/2026** | `2.4.0.1.19.pqr` |
| E | 1013634962 | 4912680517940062 | VISA | 1 mov; eCard=false | **06/08/2026** | `2.4.0.1.19.1` (presencial) |
| F | 1013634963 | 4912680517940063 | VISA | 1 mov; responseOperati=Reversado | **06/08/2026** | `2.4.0.1.19.2` (reversado) |
| G | 1013634964 | 4912680517940064 | VISA | 1 mov; responseOperati=pendiente (TDC) | **06/08/2026** | `2.4.0.1.12.exit` |
| H | 1013634965 | 5412680517940065 | MASTERCARD | vigencia 120 días → vencida (no consulta ASO) | **01/01/2025** (cualquiera > 120 días) | `2.4.0.1.7.exit` |
| I | 1013634966 | 4912680517940066 | VISA | transactions vacío | **06/08/2026** (cualquiera; devuelve vacío) | `2.4.0.1.8.return` |
| Tres | 98787954 | 4916555123453399 | VISA | 1 mov 150.000; eci=5, eCard=true, Exitosa | **06/08/2026** | `2.4.0.1.20` (devolución) |
| Uno | 10482895 | 4916555110255079 | VISA | 1 mov 200.000; eCard=false | **06/08/2026** | `2.4.0.1.19.1` (presencial) |
| Dos | 01576905 | 4916555117389461 | VISA | 1 mov 89.990; eci=1 (contracargable) | **06/08/2026** | `2.4.0.1.19.pqr` |

`J (>3)`: cualquier cliente vigente (p.ej. C) eligiendo "Más de 3" en `2.4.0.1.1` → `2.4.0.1.1.pqr`.

## Data del simulador (archivos)
- `data/salesforce/1013634958.json` (A).
- `data/financial_overview/{1013634960..64,66}.json` (C–G, I).
- `data/transactions/{PAN}.json`: C (3 movs), D/E/F/G (1 mov), I (vacío).
- `data/operations/{PAN}.json`: C/D/E/F/G (detalle con eci/eCard/responseOperati por rama).
- `data/block_failures.json`: tarjetas cuyo bloqueo (PATCH/POST) simula fallo (vacío por defecto; agregar un PAN para probar `…16.1.pqr` / `…17.1.pqr`).

## Cómo probar E2E (local, hybrid)
1. Postgres: correr el `ALTER TABLE … ADD card_flag` e insertar los clientes (ver `DATOS_PRUEBA_POSTGRES.md`).
2. Levantar simulador (`uvicorn … --port 8050`) + back_trx (`ASO_SOURCE=simulator`, base URL al simulador) + agente + front (usar `scripts/run_local.py`).
3. En el front: escribir "no reconozco una compra" → menú → op4 → seguir la rama del cliente elegido.

## Notas de congruencia
- Los `card_id` (PAN) del simulador terminan en los mismos 4 dígitos que
  `last_four_pan_id` de Postgres (0060, 0061, …), que es la llave de enlace por defecto.
- El `id` de cada transacción (`TXC01`, `TXD01`, …) es el mismo en `transactions`
  y en `operations` (llave `TX_OP_ID_FIELD`), para el cruce del detalle.
- Bloqueos (temporal/permanente) SIEMPRE contra el simulador en dev.
