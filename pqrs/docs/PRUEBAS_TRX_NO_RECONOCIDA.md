# Pruebas locales — Transacción No Reconocida (TXNR)

Guía paso a paso para probar **todo el Árbol 1** en local (rama `feature/PQRStrxno`),
incluyendo el camino feliz (hasta listar/confirmar movimientos con bucle) y todas
las ramas que van a **Formulario PQR** + la satisfacción **Sí/No**.

## 0. Levantar el stack (un comando)
```bash
python scripts/run_local.py            # o: uv run python scripts/run_local.py
#   --insecure   en la red corporativa BBVA (podman pull --tls-verify=false)
#   --no-spawn   no abre terminales; imprime los comandos del host
```
Levanta OpenSearch + back_trx en contenedor y abre 2 terminales (agente `:8000`,
front `:8501`). Front: `http://localhost:8501` · API/docs: `http://localhost:8000/docs`.
Parar: cerrar las terminales y `python scripts/run_local.py down`.

> En el front escribe algo como **“no reconozco una compra”** para caer al flujo TXNR.
> Por `curl`: `POST /start` con `user_id` y luego `POST /chat` con `content` = la **key** del botón.

## 1. Datos de prueba (mock)
| `user_id` | Recurrencia (paso 2.4.0.1) | Productos | Fechas con movimientos |
|---|---|---|---|
| **`1013634958`** | **NO** → sigue el flujo | Tarjeta *4979 (VISA) · Cuenta *4567 (MASTER) | Tarjeta: **`15/07/2026`** (3 movs) · Cuenta: **`02/06/2026`** (2 movs) |
| **`80425247`** | **SÍ** → va a Formulario PQR | (no llega a productos) | — |

Fechas especiales (con `1013634958` → Tarjeta *4979):
- **`01/01/2025`** → vencida (VISA > 180 días) → “venció el plazo”.
- **`20/07/2026`** → sin movimientos ese día.

Movimientos mock:
- Tarjeta *4979 (VISA) · `15/07/2026`: FALABELLA $120.000 (POSTED), MERCADOLIBRE $89.990 (PENDING), ABONO/REVERSO $45.000 (POSTED).
- Cuenta *4567 (MASTER) · `02/06/2026`: RETIRO ATM $250.000, PAGO PSE $300.000.

## 2. Camino feliz completo (bucle de 2 transacciones) — `1013634958`
1. `POST /start {"user_id":"1013634958"}` → bienvenida.
2. “no reconozco una compra” → **menú 2.4.0** (4 botones).
3. **“Compra presencial o por internet”** (`compra_presencial_o_internet`) → recurrencia (NO) → intro.
4. **“Sí, continuar”** (`continuar`) → “¿Cuántas transacciones?”.
5. **“2”** (`2`) → “Revisaremos una a la vez… Empezar ahora”.
6. **“Empezar ahora”** (`empezar`) → rango de valor.
7. **“Entre $35.000 y $500.000”** (`entre_35000_500000`) → productos.
8. **“Tarjeta … *4979”** (`producto_1`) → pide fecha.
9. Escribe **`15/07/2026`** → **lista de movimientos** (3 botones + “No encuentro…”).
10. **“COMPRA FALABELLA …”** (`movimiento_1`) → confirmación con el detalle.
11. **“Sí, continuar con el reporte”** (`si_reportar`) → arranca la **transacción 2 de 2** (vuelve al rango de valor).
12. Repite 7→11 para la 2ª → al confirmar la última → **cierre** (satisfacción).

Variante en 10: **“No encuentro la transacción en este listado”** (`no_encuentro`) → “Elegir otra fecha” (`otra_fecha`) / “Terminar consulta” (`terminar`).

## 3. Ramas a Formulario PQR (y satisfacción Sí/No)
Cada una muestra **“Formulario PQR”** (`pqr`); al oprimirlo pasa a **satisfacción**
(pregunta si fue útil → responde **Sí** o **No** para ver ambos cierres).

- **Sucesos 1–3** (menú): `cambiazo` / `hurto_o_perdida` / `ingenieria_social` → mensaje + **Formulario PQR** → satisfacción.
- **Recurrencia**: `user_id=80425247` → `compra_presencial_o_internet` → **recurrencia detectada** → **Formulario PQR**.
- **Más de 3**: op4 → `continuar` → “¿Cuántas?” → **“Más de 3”** (`mas_de_3`) → **Formulario PQR**.
- **Valor fuera de rango**: en el rango elige **“Menor a $35.000”** (`menor_35000`) o **“Mayor a $500.000”** (`mayor_500000`) → mensaje + **“Formulario PQR”** (`pqr`) ó **“Continuar con la siguiente transacción”** (`continuar_siguiente`, si pediste >1).
- **Finalizar en el intro**: en “¿Quieres continuar?” elige **“Finalizar conversación”** (`finalizar`) → cierre.

## 4. Off-ramps por fecha (con `1013634958` → Tarjeta *4979)
- **Vencida**: fecha **`01/01/2025`** → “superó el plazo (VISA 180)” → `otra_fecha` / `terminar`.
- **Sin movimientos**: fecha **`20/07/2026`** → “No encontramos movimientos” → `otra_fecha` / `terminar`.
- **MASTER 120 días**: producto **“Cuenta … *4567”** (`producto_2`) + fecha **`02/06/2026`** → 2 movimientos.

## 5. Keys de opciones (para `curl /chat`)
```
menú:        cambiazo | hurto_o_perdida | ingenieria_social | compra_presencial_o_internet
recurrencia: continuar
intro:       continuar (Sí) | finalizar
conteo:      1 | 2 | 3 | mas_de_3
"una a la vez": empezar
valor:       menor_35000 | entre_35000_500000 | mayor_500000
productos:   producto_1 (Tarjeta *4979, VISA) | producto_2 (Cuenta *4567, MASTER)
fecha:       texto DD/MM/AAAA (p.ej. 15/07/2026)
movimientos: movimiento_1 | movimiento_2 | movimiento_3 | no_encuentro
confirmación: si_reportar | ya_reconozco
PQR:         pqr | continuar_siguiente
off-ramps:   otra_fecha | terminar
```

Ejemplo `curl` de un turno:
```bash
CID="1013634958_YYYYMMDD"   # el que devolvió /start
curl -s http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d "{\"conversation_id\":\"$CID\",\"content\":\"compra_presencial_o_internet\"}"
```

## Notas
- Todo esto corre **mockeado**: recurrencia (`data/aso_salesforce.json`), productos
  (mock inline) y movimientos (`data/movimientos_mock.json`) en `co_pqrs_back_trx_noreconocida`.
- Al pasar a datos reales: `TRX_PRODUCTS_SOURCE=postgres` + `DB_*` (tabla `ada_info_detail`)
  y `TRX_SALESFORCE_SOURCE=aso`; el **fetch real de movimientos** (Financial Overview)
  está pendiente de implementar (hoy solo `mock`).
