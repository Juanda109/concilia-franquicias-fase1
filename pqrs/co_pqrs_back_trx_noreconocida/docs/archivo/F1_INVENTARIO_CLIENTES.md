# F1 — Inventario de clientes de prueba

**Fecha:** 20/08/2026 · Primera fase del `PLAN_EVALUACION_PRE_IMAGENES.md`.
**Objetivo:** clasificar los clientes en «llega hasta aquí **por diseño**» o «llega hasta aquí
**porque falta un dato**», y completar los segundos.

> **Resultado: ningún hueco de fixture, pero un defecto grave que sólo se ve haciendo este
> inventario** — cualquier `customer_id`, incluso inventado, recibía los productos de otra
> persona. Está corregido (§3).

---

## 1 · Los 19 clientes, y hasta dónde llega cada uno

| Cliente | Marca | Llega hasta | Por qué | Veredicto |
|---|---|---|---|---|
| `1013634958` | VISA | recurrencia → PQR | Salesforce reporta gestión reciente; se desvía antes del ASO | ✅ diseño |
| `1013634959` | VISA | «no tienes productos activos» | **`card_flag = false`** → el filtro lo descarta | ✅ diseño |
| `1013634960` | VISA | flujo completo → **PQR** | `eci=5`, fuera del conjunto contracargable | ✅ |
| `1013634961` | VISA | flujo completo → **devolución** | `eci=1` | ✅ |
| `1013634962` | VISA | flujo completo | rango de importe | ✅ |
| `1013634963` | VISA | flujo completo | rango de importe | ✅ |
| `1013634964` | VISA | `.12.exit` compra pendiente | `responseOperati=pendiente` | ✅ diseño |
| `1013634965` | **MASTERCARD** | `.7.exit` fuera de plazo | vigencia 120 días | ✅ diseño |
| `1013634966` | VISA | `.8.return` sin compras | **transactions con 0 movimientos** | ✅ diseño |
| `1013634967` | VISA | flujo completo | **cliente J**: ADA dice 9999, el PAN es 4321 | ✅ |
| `1013634968` | VISA | listado con 10 movimientos | tope de 5 + aviso de resto (H-14) | ✅ |
| `1013634969` | VISA | `.8.return` **fuera de rango** | 2 movimientos, de $18.000 y $890.000 | ✅ diseño |
| `1013634970` | VISA | flujo completo → **devolución** | **cliente M**: `eci=0`, 3 movimientos | ✅ |
| `1013634971` | VISA | flujo completo → **presencial** | **cliente N**: `eci=9` | ✅ |
| `1013634972` | VISA | flujo completo → **reversado** | **cliente O**: reversa + `dateReverse` | ✅ |
| `01576905` | VISA | flujo completo → devolución | `eci=1` | ✅ |
| `10482895` | VISA | flujo completo → devolución | `eci=7` | ✅ |
| `98787954` | VISA | flujo completo → PQR | `eci=5` | ✅ |
| `1010223694` | VISA + MASTER | flujo completo | cliente de **bloqueos** de Luis; **2 productos** (TDC + Pasivo) | ⚠️ ver §3 |

**Los cuatro desenlaces están cubiertos**, cada uno por al menos un cliente:
devolución (`…961`, `…970`, `01576905`, `10482895`), PQR (`…960`, `98787954`),
presencial (`…971`) y reversado (`…972`).

### Sobre `1576905`

Es un duplicado de `01576905` **sin el cero inicial**, con el mismo PAN. Sirve de red por si
el identificador llega normalizado. No es un cliente: es una salvaguarda. Se deja.

---

## 2 · Correcciones a mis propias suposiciones

Este inventario desmintió dos cosas que yo daba por hechas:

1. **`1013634969` parecía un hueco** — tenía `transactions` pero no `operations`, así que
   supuse que reventaría al pedir el detalle. **Falso**: sus dos movimientos son de $18.000 y
   $890.000, ambos **fuera del rango** 35.000–500.000, y el servicio lo dice
   (`fuera_de_rango: 2`). Es el cliente del hallazgo H-14 y **no necesita `operations`**.
2. **`1010223694` parecía inutilizable** — no tiene fila en `ada_info_detail`, así que supuse
   que no devolvería productos. **Falso**: devolvía dos. Y averiguar por qué es lo que destapó
   el defecto de §3.

Anoto las dos porque el patrón se repite: **el hueco aparente suele ser diseño, y el defecto
de verdad estaba donde no miraba.**

---

## 3 · El defecto: cualquier cliente recibía productos ajenos

### Qué pasaba

```python
rows = self._load_products_from_postgres(case.customer_id)
if not rows:
    logger.info("Postgres products empty; using mock fallback ...")
    rows = mock_rows          # <- productos de OTRA persona
```

Si Postgres no devolvía nada, el servicio **sustituía en silencio** por dos productos del
mock. Medido:

```
customer_id=abcdef      -> ok · 2 productos · *4979, *4567
customer_id=9999999999  -> ok · 2 productos · *4979, *4567
```

**Un identificador inventado recibía los últimos 4 de las tarjetas de otro.**

### Tres consecuencias, cada una peor que la anterior

1. **Se muestran datos de otra persona.** Es exactamente lo que Fabián prohibió, y en su forma
   más grave: no es un mensaje equivocado, son dígitos de una tarjeta ajena.
2. **El paso `2.4.0.1.4.exit` era inalcanzable.** «Actualmente no tienes productos activos» no
   podía salir nunca, porque el vacío siempre se rellenaba con el mock. Un camino entero del
   flujo estaba muerto sin que nadie lo supiera.
3. **La auditoría mentía.** La respuesta y la traza publicaban
   `source: postgres` aunque los datos vinieran del mock, así que ni siquiera revisando los
   logs se podía detectar.

### Qué se hizo

- **Se retira el rescate**: si Postgres no tiene productos, se responde **sin productos** y se
  registra un `logger.warning`. El cliente ve el mensaje honesto.
- **Se publica la fuente real**: `fuente_real` sustituye al valor configurado en los tres
  sitios donde se publicaba (respuesta con productos, respuesta vacía y traza de auditoría).
- **Se siembra `1010223694` en Postgres** (`dev/postgres/07-seed-cliente-bloqueos.sql`) con los
  dos productos que traía el mock, para que el cliente de bloqueos de Luis siga funcionando
  sin depender del rescate.

### Verificado

```
abcdef       -> not_found · 0 productos
9999999999   -> not_found · 0 productos
1010223694   -> ok · 2 productos · *4979, *4567   (ahora desde Postgres de verdad)
1013634960   -> ok · 1 producto                    (sin cambios)
```

Unitarias del servicio: **42/42**.

---

## 4 · Lo que queda para F2

Ninguna acción sobre clientes: **los 19 están clasificados y no hay fixtures que completar**.
La cobertura de datos es correcta.

Lo que sí queda pendiente, y era el otro requisito de F1:

- **`2.4.0.1.4.exit` ya es alcanzable**, y hasta hoy no lo era. Hay que **añadirlo a la
  cobertura** con un cliente sin productos en Postgres — el `1013634959` no sirve, porque su
  salida es por `card_flag=false` y pasa por el filtro, no por el vacío. Conviene un cliente
  nuevo que sencillamente no exista en ADA.
- Ese es precisamente el tipo de arista que el medidor de F2 debe detectar como no pisada.
