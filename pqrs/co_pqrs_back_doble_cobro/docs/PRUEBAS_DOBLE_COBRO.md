# Casuísticas de prueba — Doble Cobro

> Qué escribir en el front y qué debe responder el bot, camino por camino.
> Documento de referencia para QA y Desarrollo.

---

## Resumen ejecutivo

| Métrica | Resultado |
|---|---|
| **Casos ejecutados** | 39 |
| **PASS** | 39 |
| **FAIL** | 0 |
| **Cobertura del árbol** | 15 de 16 pasos |
| **Ambiente** | Local (`:8000` → `:8006` → `:8050`) |
| **Última ejecución** | 2026-09-08 |

Las 39 casuísticas se ejecutaron contra el flujo real y las 39 dieron el
resultado que aquí se describe. **Si alguna falla, es una regresión.**

Lo que queda fuera de la cobertura y por qué está en
[Qué NO cubre esto](#qué-no-cubre-esto).

### Ejecución

La versión ejecutable está en
[`scripts/casuisticas_doble_cobro.py`](../scripts/casuisticas_doble_cobro.py):

```bash
cd co_pqrs_back_doble_cobro
python scripts/casuisticas_doble_cobro.py       # todas
python scripts/casuisticas_doble_cobro.py B     # solo vigencia
```

---

## Matriz de casos

Las reglas **RN-xx** referencian
[`ESPECIFICACION_FLUJO_DOBLE_COBRO.md`](ESPECIFICACION_FLUJO_DOBLE_COBRO.md) §4.

### A · Producto

| ID | Casuística | Resultado | Regla |
|---|---|---|---|
| A1 | Tarjeta de crédito no entra al flujo | ✅ PASS | — |
| A2 | Cliente sin productos | ✅ PASS | — |
| A3 | Selector de productos | ✅ PASS | — |

### B · Vigencia

| ID | Casuística | Resultado | Regla |
|---|---|---|---|
| B1 | Aún en conciliación | ✅ PASS | RN-01 |
| B2 | El mínimo justo (7 hábiles) | ✅ PASS | RN-01 |
| B3 | Fuera de los 6 meses | ✅ PASS | RN-02 |
| B4 | Franquicia MASTER (120 días) | ✅ PASS | RN-02 |
| B5 | La misma tarjeta dentro de plazo sí avanza | ✅ PASS | RN-02 |
| B6 | Misma fecha, VISA → avanza | ✅ PASS | RN-02 |
| B7 | Misma fecha, cuenta → avanza | ✅ PASS | RN-02 |

### C · Detección de duplicados

| ID | Casuística | Resultado | Regla |
|---|---|---|---|
| C1 | Grupo de 3 → 2 reportables | ✅ PASS | RN-03 · RN-04 |
| C2 | Grupo de 2 → 1 reportable | ✅ PASS | RN-03 · RN-04 |
| C3 | Tolerancia de búsqueda ±2.000 | ✅ PASS | RN-03 |
| C4 | Cargo único | ✅ PASS | RN-03 |
| C5 | Trampa por monto | ✅ PASS | RN-03 |
| C6 | Trampa por comercio | ✅ PASS | RN-03 |
| C7 | Horas muy separadas sí agrupan | ✅ PASS | RN-03 |
| C8 | Triple cobro | ✅ PASS | RN-03 · RN-04 |

### D · Paginación

| ID | Casuística | Resultado | Regla |
|---|---|---|---|
| D1 | Primera página | ✅ PASS | RN-05 |
| D2 | Segunda página | ✅ PASS | RN-05 |
| D3 | La selección sobrevive al cambio de página | ✅ PASS | RN-05 |

### E · Selección múltiple

| ID | Casuística | Resultado | Regla |
|---|---|---|---|
| E1 | Contador y tarjeta única | ✅ PASS | RN-05 |
| E2 | Desmarcar | ✅ PASS | RN-05 |
| E3 | No encuentro la transacción | ✅ PASS | RN-05 |

### F · Registro

| ID | Casuística | Resultado | Regla |
|---|---|---|---|
| F1 | Camino feliz completo | ✅ PASS | RN-04 |
| F2 | Repetir el reporte no lo bloquea | ✅ PASS | RN-06 ⚠️ |
| F3 | Reportar sin selección | ✅ PASS | RN-05 |

> [!CAUTION]
> **F2 depende del PUNTO A REVISAR C-01.** La especificación original describe
> una rama `3.4.0.5.recurrente` que termina el flujo cuando ya existe un reporte
> previo; este caso verifica lo contrario. Ver
> [`ESPECIFICACION_FLUJO_DOBLE_COBRO.md`](ESPECIFICACION_FLUJO_DOBLE_COBRO.md) §8.
> El resultado ✅ PASS refleja lo medido, **no** una resolución de la contradicción.

### G · Otros productos

| ID | Casuística | Resultado | Regla |
|---|---|---|---|
| G1 | CUENTA META | ✅ PASS | — |
| G2 | Visa Débito | ✅ PASS | — |

### H · Visa Débito y casos límite

| ID | Casuística | Resultado | Regla |
|---|---|---|---|
| H1 | Visa Débito: frontera de 7 hábiles | ✅ PASS | RN-01 |
| H2 | Visa Débito: supera los 180 días de VISA | ✅ PASS | RN-02 |
| H3 | Cargo único el día de casos límite | ✅ PASS | RN-03 |

### I · El cliente no tiene cobros duplicados

| ID | Casuística | Resultado | Regla |
|---|---|---|---|
| I1 | Día sin ningún movimiento | ✅ PASS | RN-03 |
| I2 | Monto ilegible | ✅ PASS | RN-03 |
| I3 | Monto cero | ✅ PASS | RN-03 |

### J · Salidas a PQR y cierre

| ID | Casuística | Resultado | Regla |
|---|---|---|---|
| J1 | Cuenta corriente | ✅ PASS | — |
| J2 | Formulario PQR desde `3.4.0.6.pqr` → satisfacción | ✅ PASS | — |
| J3 | Formulario PQR desde `3.4.0.pqr_tarjeta_credito` → satisfacción | ✅ PASS | — |
| J4 | Fecha ilegible | ✅ PASS | RN-02 |

---

## Preparación del entorno

### Servicios requeridos

Tienen que estar arriba el agente (`:8000`), doble cobro (`:8006`), el simulador
ASO (`:8050`), OpenSearch (`:9200`) y el front (`:8501`).

El más fácil de olvidar es el `:8006`, que además necesita
`uv sync --system-certs` la primera vez (el proxy corporativo rompe el
`uv sync` normal):

```bash
cd co_pqrs_back_doble_cobro && uv sync --system-certs
uv run uvicorn --app-dir src infrastructure.entrypoint.fastapi_app:app --host 127.0.0.1 --port 8006
```

### Entrada al flujo

Para entrar al flujo desde el front, escribe algo como
**«me cobraron dos veces la misma compra»**. El ruteo es por LLM, así que
cualquier frase equivalente sirve.

### Clientes

| Cliente | Productos | Para qué |
|---|---|---|
| `13083558` | Ahorro Libretón •2384, CUENTA META •3755, Visa Débito •4818 | El principal |
| `13083559` | Mastercard Débito •7799 | Probar los 120 días de MASTER frente a los 180 de VISA |
| `13083560` | *ninguno* | Único modo de llegar a «No pude consultar tus productos» |

`13083558` no sirve para probar «sin productos»: su tarjeta débito aparece tanto
en la familia de ahorro como en la de corriente (el ASO no dice a qué cuenta
pertenece), así que siempre devuelve al menos un producto.

### Fechas

> [!WARNING]
> **Las fechas caducan solas.** Las reglas se evalúan contra el día de hoy
> (7 días hábiles de conciliación, ventana de 6 meses, vigencia de franquicia),
> así que un fixture con fechas quemadas deja de servir. Las de este documento
> son las de la generación del **2026-09-08**.
>
> Para refrescarlas:
>
> ```bash
> cd co_pqrs_back_trx_aso_simulator && python scripts/gen_doble_cobro_fixtures.py
> ```
>
> El script imprime las fechas nuevas al ejecutarse: cópialas a la tabla de abajo.

| Fecha | Hábiles | Qué prueba |
|---|---|---|
| `03/09/2026` | 3 | Aún en conciliación |
| `28/08/2026` | 7 | El mínimo justo |
| `21/08/2026` | 12 | Camino feliz |
| `10/08/2026` | 20 | Casos límite del detector |
| `31/07/2026` | 25 | Paginación |
| `10/04/2026` | — | Pasa los 120 días de MASTER, no los 180 de VISA |
| `09/01/2026` | — | Fuera de los 6 meses |

---

## A · Producto

Pasos `3.4.0` y `3.4.0.1`.

### A1 — Tarjeta de crédito no entra al flujo

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | — |
| Fecha | — |
| Monto | — |

**Acción**

Familia → **Tarjeta de crédito**.

**Esperado**

«Por las características de lo ocurrido, tu caso requiere una revisión a
fondo…» + botón **Formulario PQR**.

**Validación**

El doble cobro en crédito lo atiende otro equipo; el bot no lo trabaja.

**Resultado** ✅ PASS

---

### A2 — Cliente sin productos

| Campo | Valor |
|---|---|
| Cliente | `13083560` |
| Producto | — |
| Fecha | — |
| Monto | — |

**Acción**

Familia → **Cuenta de ahorro**.

**Esperado**

«No pude consultar tus productos en este momento…» + **Formulario PQR**.

**Validación**

> [!WARNING]
> **Este mensaje también aparece si el ASO falla.** El flujo no distingue «no
> tienes productos» de «no pude preguntar»: ambos caen aquí. Si lo ves en un
> cliente que sí tiene productos, mira los logs del `:8006` antes de darlo por
> bueno — probablemente sea el TSEC.

**Resultado** ✅ PASS

---

### A3 — Selector de productos

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | — |
| Fecha | — |
| Monto | — |

**Acción**

Familia → **Cuenta de ahorro**.

**Esperado**

Tres opciones: `Ahorro Libretón •2384`, `CUENTA META •3755`, `Visa Débito •4818`.

**Validación**

Elegir **Cuenta corriente** devuelve solo la Visa Débito: es el comportamiento
correcto, la tarjeta cuelga de ambas familias (ver J1).

**Resultado** ✅ PASS

---

## B · Vigencia

Paso `3.4.0.3`. Las tres reglas se evalúan **en orden** y la primera que falla
manda: conciliación (7 hábiles) → plazo general (6 meses) → franquicia (solo
tarjetas).

### B1 — Aún en conciliación

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `03/09/2026` |
| Monto | — |

**Esperado**

«La transacción aún está dentro del tiempo de conciliación de **7 días
hábiles** con el comercio.» Conversación **cerrada**, sin botones.

**Validación**

Hay un duplicado real ese día (PANADERIA LA ESQUINA, 18.000), pero el gate corta
antes: el cobro todavía puede desaparecer solo.

**Resultado** ✅ PASS

---

### B2 — El mínimo justo

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `28/08/2026` |
| Monto | — |

**Esperado**

Avanza a pedir el monto.

**Validación**

Un día hábil menos y devuelve «aún en conciliación». Los 7 días aplican igual a
cuentas de ahorro, corrientes y tarjetas débito.

**Resultado** ✅ PASS

---

### B3 — Fuera de los 6 meses

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `09/01/2026` |
| Monto | — |

**Esperado**

«La fecha que ingresaste supera el plazo permitido…» + **Formulario PQR**.

**Resultado** ✅ PASS

---

### B4 — Franquicia MASTER (120 días)

| Campo | Valor |
|---|---|
| Cliente | `13083559` |
| Producto | Mastercard Débito •7799 |
| Fecha | `10/04/2026` |
| Monto | — |

**Esperado**

«…supera el plazo permitido por las franquicias…» + **Formulario PQR**.

**Validación**

> [!WARNING]
> **B3 y B4 se ven IGUAL desde el front.** El paso `3.4.0.3.pqr` usa el mismo
> texto para «fuera de los 6 meses» y para «vencida la franquicia», así que
> llegar al formulario **no demuestra** cuál de las dos reglas cortó. Para
> distinguirlas, o preguntas al servicio
> ([ver más abajo](#comprobar-qué-regla-cortó)) o usas B6/B7.

**Resultado** ✅ PASS

---

### B5 — La misma tarjeta dentro de plazo sí avanza

| Campo | Valor |
|---|---|
| Cliente | `13083559` |
| Producto | Mastercard Débito •7799 |
| Fecha | `21/08/2026` |
| Monto | `75000` |

**Esperado**

1 casilla de `TIENDA ONLINE MASTER — $ -75.000,00 · •7799`.

**Validación**

Lo que corta en B4 es la fecha frente a la franquicia, no el producto.

**Resultado** ✅ PASS

---

### B6 y B7 — La prueba de la franquicia, visible desde el front

La misma fecha `10/04/2026` da **tres resultados distintos** según el producto
que elijas. Es la única forma de demostrar la regla sin salir del chat:

| Caso | Cliente · producto | Resultado esperado |
|---|---|---|
| **B4** | `13083559` · Mastercard •7799 | **Corta** → Formulario PQR |
| **B6** | `13083558` · Visa Débito •4818 | **Avanza** → pide el monto |
| **B7** | `13083558` · Ahorro Libretón •2384 | **Avanza** → pide el monto |

**Validación**

A esa fecha han pasado ~151 días: superan los **120** de MASTER, no los **180**
de VISA, y una cuenta no tiene marca, así que ni se evalúa. La marca se deduce
del primer dígito del PAN (`4` = VISA, `5` y `2` = MASTER), no del nombre del
producto.

El gate de vigencia corre **antes** de buscar movimientos, así que B6 y B7
funcionan aunque esos productos no tengan cargos ese día: llegan a pedir el monto
igualmente.

**Resultado** ✅ PASS (B6) · ✅ PASS (B7)

---

### Comprobar qué regla cortó

El servicio sí distingue, aunque el chat no. Pregúntaselo directo:

```bash
curl -s -X POST http://127.0.0.1:8006/v0/doble-cobro/validar-vigencia \
  -H "Content-Type: application/json" \
  -d '{"transaction_date":"10/04/2026","product_type":"CARD","card_brand":"MASTER"}'
```

Los `outcome` posibles son `ok`, `settlement_pending`, `report_window_expired` y
`franchise_expired`. Medido el **08/09/2026**:

| Fecha | Producto | Marca | `outcome` |
|---|---|---|---|
| `10/04/2026` | CARD | MASTER | `franchise_expired` (120) |
| `10/04/2026` | CARD | VISA | `ok` |
| `10/04/2026` | ACCOUNT | — | `ok` |
| `11/03/2026` | CARD | VISA | `franchise_expired` (180) |
| `09/01/2026` | CARD | VISA | `report_window_expired` |
| `21/08/2026` | CARD | MASTER | `ok` |

Una marca no reconocida (AMEX, Diners, o un dato incompleto) recibe el plazo
**más largo** — 180 días, el de VISA. Es una decisión de negocio consciente:
antes admitir la reclamación y que la revise el equipo, que rechazarla por un
dato que el ASO no supo clasificar.

---

## C · Detección de duplicados

Paso `3.4.0.6`. Todo lo de esta sección va con `13083558` · **Ahorro Libretón**.

> [!IMPORTANT]
> Dos criterios distintos, a propósito:
>
> - Al **buscar** se admite **±2.000** sobre el monto que escribe el cliente.
> - Al **agrupar** se exige monto **idéntico**, **mismo comercio** y **misma fecha**.
>
> **La hora no interviene**: el comercio puede reprocesar el cobro horas después.

### C1 — Grupo de 3 → 2 reportables

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `21/08/2026` |
| Monto | `145000` |

**Esperado**

2 casillas de `SUPERMERCADO LA 14 — $ -145.000,00` (10:19 AM y 2:30 PM).

**Validación**

> [!IMPORTANT]
> Hay tres cargos iguales (10:15, 10:19, 14:30). El más antiguo se considera el
> **legítimo** y no se ofrece: siempre se reportan **N-1**. Nótese que el de las
> 14:30 entra aunque esté 4 horas después.

**Resultado** ✅ PASS

---

### C2 — Grupo de 2 → 1 reportable

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `21/08/2026` |
| Monto | `88000` |

**Esperado**

1 casilla de `EDS PRIMAX CALLE 80`.

**Resultado** ✅ PASS

---

### C3 — Tolerancia de búsqueda

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `21/08/2026` |
| Monto | `146500` |

**Esperado**

Las mismas 2 casillas que C1.

**Validación**

> [!IMPORTANT]
> 1.500 de diferencia: dentro de los **±2.000**. Con `148000` ya no encontraría
> nada.

**Resultado** ✅ PASS

---

### C4 — Cargo único

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `21/08/2026` |
| Monto | `210000` |

**Esperado**

«Con la información disponible no podemos identificar el cobro duplicado…» +
**Formulario PQR**.

**Resultado** ✅ PASS

---

### C5 — Trampa por monto

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `10/08/2026` |
| Monto | `76000` |

**Esperado**

No identifica el cobro duplicado → PQR.

**Validación**

> [!IMPORTANT]
> `FARMACIA CAFAM 127` tiene 76.000 y 76.500. Los dos entran como candidatos por
> la tolerancia de búsqueda, pero **no forman grupo**: agrupar exige **monto
> exacto**. Es la casuística que impide falsos positivos sobre compras distintas
> del mismo comercio.

**Resultado** ✅ PASS

---

### C6 — Trampa por comercio

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `10/08/2026` |
| Monto | `15000` |

**Esperado**

No identifica el cobro duplicado → PQR.

**Validación**

> [!IMPORTANT]
> Mismo monto y casi el mismo minuto, pero `PARQUEADERO CENTRO` y
> `PARQUEADERO NORTE` son comercios distintos: agrupar exige **mismo comercio**.

**Resultado** ✅ PASS

---

### C7 — Horas muy separadas sí agrupan

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `10/08/2026` |
| Monto | `47000` |

**Esperado**

1 casilla de `CINE COLOMBIA UNICENTRO`.

**Validación**

> [!IMPORTANT]
> Los dos cargos están separados **3 horas** y aun así son un grupo: **la hora no
> interviene** en el criterio.

**Resultado** ✅ PASS

---

### C8 — Triple cobro

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `10/08/2026` |
| Monto | `24500` |

**Esperado**

2 casillas de `TIENDA D1 CEDRITOS`.

**Resultado** ✅ PASS

---

## D · Paginación

Paso `3.4.0.6`, **6 movimientos por página**.
`13083558` · Ahorro Libretón · fecha `31/07/2026` · monto `34000`.

Ese día hay 8 parejas de 34.000 en 8 comercios distintos → **8 cobros
reportables**.

### D1 — Primera página

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `31/07/2026` |
| Monto | `34000` |

**Esperado**

6 casillas, el texto «Te muestro los movimientos **1 a 6 de 8** (página 1 de 2)»,
y los botones **Ver más movimientos**, **Reportar seleccionados** y **No
encuentro la transacción**.

**Resultado** ✅ PASS

---

### D2 — Segunda página

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `31/07/2026` |
| Monto | `34000` |

**Acción**

Pulsar **Ver más movimientos**.

**Esperado**

Las 2 restantes, ya **sin** el botón de «Ver más».

**Validación**

> [!IMPORTANT]
> La conversación sigue en el mismo paso y **no aparece otra tarjeta**: se
> repinta la misma.

**Resultado** ✅ PASS

---

### D3 — La selección sobrevive al cambio de página

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `31/07/2026` |
| Monto | `34000` |

**Acción**

Marcar la primera casilla de la página 1 → **Ver más movimientos** → marcar la
primera de la página 2.

**Esperado**

En la página 2 se ven `COMERCIO PAGINACION 02` marcada y `COMERCIO PAGINACION 01`
sin marcar, y el botón dice **Reportar 2 cobros**.

**Validación**

> [!IMPORTANT]
> El contador incluye también la de la página 1, que **ya no está a la vista**:
> la selección sobrevive entre páginas.

**Resultado** ✅ PASS

---

## E · Selección múltiple

Paso `3.4.0.6`. `13083558` · Ahorro Libretón · `21/08/2026` · `145000`.

### E1 — Contador y tarjeta única

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `21/08/2026` |
| Monto | `145000` |

**Acción**

Marcar las dos casillas.

**Esperado**

El texto pasa por «Llevas 1 transacción(es) seleccionada(s)» y luego 2; el botón
pasa de **Reportar seleccionados** a **Reportar 1 cobro** y **Reportar 2 cobros**.

**Validación**

> [!IMPORTANT]
> El historial debe seguir teniendo **una sola tarjeta** del selector, que se
> actualiza. Si aparece «Encontré estas transacciones duplicadas…» repetido una
> vez por clic, **es una regresión**.

**Resultado** ✅ PASS

---

### E2 — Desmarcar

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `21/08/2026` |
| Monto | `145000` |

**Acción**

Marcar y volver a marcar la misma casilla.

**Esperado**

Vuelve a «Llevas 0 transacción(es)» y el botón a **Reportar seleccionados**,
deshabilitado.

**Resultado** ✅ PASS

---

### E3 — No encuentro la transacción

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `21/08/2026` |
| Monto | `145000` |

**Acción**

Pulsar **No encuentro la transacción**.

**Esperado**

«Con la información disponible no podemos identificar…» + **Formulario PQR**.

**Resultado** ✅ PASS

---

## F · Registro

Pasos `3.4.0.7` y `3.4.0.8`.

### F1 — Camino feliz completo

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `21/08/2026` |
| Monto | `145000` |

**Acción**

Marcar las 2 → **Reportar 2 cobros**.

**Esperado**

«Hemos registrado tu reporte de cobro duplicado. En un plazo máximo de **3 días
hábiles** verás reflejado el dinero en tu cuenta.» Conversación cerrada.

**Validación**

Se registran **solo** las transacciones marcadas. Marcando una sola, se reporta
una sola.

**Resultado** ✅ PASS

---

### F2 — Repetir el reporte no lo bloquea

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `21/08/2026` |
| Monto | `145000` |

**Acción**

Completar F1 y volver a hacer el mismo flujo con la misma fecha y el mismo monto.

**Esperado**

El mismo mensaje de registro. **Nunca** «Ya tenemos registrado un reporte para
este cobro duplicado» — ese texto ya no existe.

**Validación**

> [!IMPORTANT]
> La identidad de reemplazo es **producto + fecha + monto**: el reporte anterior
> se sobrescribe en vez de acumularse. Un reporte de otro monto, u otra fecha, o
> de otro producto se conserva intacto.

> [!CAUTION]
> **PUNTO A REVISAR C-01.** La especificación describe una rama
> `3.4.0.5.recurrente` que **termina el flujo** cuando ya existe un reporte
> previo, y una acumulación que **conserva** los anteriores. Este caso verifica
> lo contrario en ambos puntos. El ✅ PASS refleja lo medido, **no** una decisión
> sobre cuál comportamiento debe quedar. Ver
> [`ESPECIFICACION_FLUJO_DOBLE_COBRO.md`](ESPECIFICACION_FLUJO_DOBLE_COBRO.md) §8.

**Resultado** ✅ PASS

---

### F3 — Reportar sin selección

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `21/08/2026` |
| Monto | `145000` |

**Acción**

Pulsar **Reportar** sin marcar nada.

**Esperado**

Desde el front **no es alcanzable**: el botón está deshabilitado mientras el
contador esté en 0. Si llegara por API, el flujo vuelve al selector con el aviso
«Selecciona al menos un cobro duplicado para poder reportarlo».

**Resultado** ✅ PASS

---

## G · Otros productos

### G1 — CUENTA META

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | `CUENTA META •3755` |
| Fecha | `21/08/2026` |
| Monto | `99000` |

**Esperado**

1 casilla de `SEGUROS BOLIVAR`.

**Validación**

Juego de datos propio: si al elegir CUENTA META aparecen los comercios del
Libretón, el producto se está resolviendo mal.

**Resultado** ✅ PASS

---

### G2 — Visa Débito

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | `Visa Débito •4818` |
| Fecha | `21/08/2026` |
| Monto | `189000` |

**Esperado**

1 casilla de `MERCADO LIBRE CO`.

**Resultado** ✅ PASS

---

## H · Visa Débito y casos límite

> [!NOTE]
> **PUNTO A REVISAR D-01.** Estos tres casos existen y se ejecutan en
> [`scripts/casuisticas_doble_cobro.py`](../scripts/casuisticas_doble_cobro.py),
> pero la versión anterior de este documento **no les daba sección propia** pese
> a declarar 39 casuísticas. Se documentan aquí con los parámetros exactos del
> runner. Conviene confirmar que la descripción coincide con la intención
> original.

### H1 — Visa Débito: frontera de 7 hábiles

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | `Visa Débito •4818` |
| Fecha | `28/08/2026` |
| Monto | — |

**Esperado**

Avanza a pedir el monto.

**Validación**

La frontera de 7 días hábiles es la misma que en cuentas.

**Resultado** ✅ PASS

---

### H2 — Visa Débito: supera los 180 días de VISA

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | `Visa Débito •4818` |
| Fecha | `11/03/2026` |
| Monto | — |

**Esperado**

«…supera el plazo…» + **Formulario PQR**.

**Validación**

El servicio devuelve `outcome: franchise_expired` para
`11/03/2026` · `CARD` · `VISA` — ver la tabla de
[Comprobar qué regla cortó](#comprobar-qué-regla-cortó).

**Resultado** ✅ PASS

---

### H3 — Cargo único el día de casos límite

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `10/08/2026` |
| Monto | `57000` |

**Esperado**

«Con la información disponible no podemos identificar…» → PQR.

**Validación**

`LIBRERIA NACIONAL` es un cargo único ese día.

**Resultado** ✅ PASS

---

## I · El cliente no tiene cobros duplicados

Son **cuatro situaciones distintas** que acaban en el mismo sitio
(`3.4.0.6.pqr`, «Con la información disponible no podemos identificar el cobro
duplicado…» + **Formulario PQR**). Conviene probarlas por separado porque fallan
por motivos diferentes:

| Caso | Cliente · producto | Fecha · monto | Qué hay ese día |
|---|---|---|---|
| **C4** | `13083558` · Ahorro | `21/08/2026` · `210000` | Sí hay movimientos, pero ese cargo es único |
| **C5** | `13083558` · Ahorro | `10/08/2026` · `76000` | Hay dos del mismo comercio, con 500 de diferencia |
| **C6** | `13083558` · Ahorro | `10/08/2026` · `15000` | Mismo monto y minuto, comercios distintos |
| **I1** | `13083558` · Ahorro | `26/08/2026` · `50000` | **Ningún movimiento** ese día |

### I1 — Día sin ningún movimiento

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `26/08/2026` |
| Monto | `50000` |

**Esperado**

«Con la información disponible no podemos identificar…» + **Formulario PQR**.

**Validación**

Un día hábil, dentro de plazo, en el que el cliente sencillamente no movió la
cuenta. El bot **no lo distingue** de «hay movimientos pero ninguno duplicado» —
y está bien que no lo haga, porque para el cliente la respuesta es la misma.

**Resultado** ✅ PASS

---

### I2 — Monto ilegible

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `21/08/2026` |
| Monto | `como cien mil` |

**Esperado**

No identifica el cobro → PQR.

**Validación**

No revienta: el monto ilegible se interpreta como 0 y ningún grupo casa. Desde el
front real es difícil llegar aquí porque el campo es numérico.

**Resultado** ✅ PASS

---

### I3 — Monto cero

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | `21/08/2026` |
| Monto | `0` |

**Esperado**

No identifica el cobro → PQR.

**Resultado** ✅ PASS

---

## J · Salidas a PQR y cierre

### J1 — Cuenta corriente

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | — |
| Fecha | — |
| Monto | — |

**Acción**

Familia → **Cuenta corriente**.

**Esperado**

Una sola opción: `Visa Débito •4818`.

**Validación**

El cliente no tiene cuenta corriente, pero la tarjeta débito cuelga de ambas
familias (el ASO no dice a qué cuenta pertenece), así que el selector no queda
vacío. **Es el comportamiento correcto, no un error.**

**Resultado** ✅ PASS

---

### J2 y J3 — El botón «Formulario PQR» cierra en satisfacción

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | J2: Ahorro Libretón · J3: — |
| Fecha | J2: `21/08/2026` · J3: — |
| Monto | J2: `210000` · J3: — |

**Acción**

Llegar a cualquier PQR (**J2**: por C4 · **J3**: por A1 con tarjeta de crédito) y
pulsar **Formulario PQR**.

**Esperado**

Una pregunta de satisfacción con dos opciones, **Sí, me ayudó** y **No, ver línea
de atención**.

**Validación**

> [!WARNING]
> El **texto** de esa pregunta es aleatorio: sale de un pool en
> `general_messages.yml` y cambia entre ejecuciones («¿He resuelto tu consulta?»,
> «¿Ha quedado clara tu duda…?», «¿Te ha ayudado esta información…?»). **No lo
> uses como criterio de aceptación**; fíjate en las dos opciones.

**Resultado** ✅ PASS (J2) · ✅ PASS (J3)

---

### J4 — Fecha ilegible

| Campo | Valor |
|---|---|
| Cliente | `13083558` |
| Producto | Ahorro Libretón |
| Fecha | texto libre, p. ej. `no me acuerdo` |
| Monto | — |

**Acción**

Escribir algo que no sea una fecha (por API; el front usa calendario).

**Esperado**

**Formulario PQR**.

**Validación**

Es un fail-closed correcto —no se sigue con un dato que no se pudo validar—,
pero:

> [!WARNING]
> **El mensaje miente.** Dice «La fecha que ingresaste supera el plazo permitido
> por las franquicias…», cuando lo que pasó es que no se pudo leer. No es
> alcanzable desde el front real, así que no bloquea; queda anotado por si alguna
> vez se expone el campo como texto libre.

**Resultado** ✅ PASS

---

## Qué NO cubre esto

Para que nadie dé por probado lo que no lo está:

| Qué | Por qué no está |
|---|---|
| `3.4.0.8.no_procede` | Es el fail-closed de registro: la escritura en OpenSearch falló, o quedó ilegible al releer, o la selección no corresponde a ninguna transacción. No se puede forzar desde el front sin romper OpenSearch a propósito. **Sí está cubierto por pruebas unitarias** en el agente (`test_register_write_failure_fails_closed`, `test_unreadable_case_after_write_fails_closed`, `test_register_with_an_invalid_selection_fails_closed`). |
| Límite diario (3/día por caso) | En el `.env` local está en `MAX_DAILY_CATEGORY_INTERACTIONS=1000`, así que nunca dispara. Para probarlo hay que bajarlo a 3 y repetir el flujo cuatro veces. **Ojo:** si lo bajas, las 39 casuísticas dejarán de pasar seguidas. |
| Las ramas de `satisfaction_check` (Sí / No) | Es un paso compartido por los ~20 flujos, no específico de doble cobro. |
| Marca de tarjeta no reconocida (AMEX, Diners) | No hay fixture. Recibiría el plazo más largo, el de VISA. Haría falta una tarjeta con PAN que no empiece por `4`, `5` ni `2`. |
| El ASO real | El simulador no valida el `tsec` (ver más abajo), así que estas 39 no dicen nada sobre autenticación contra `dev-arqaso`. |

---

## Anexos

### Comprobar el registro en OpenSearch

Después de F1, la ficha del cliente queda en el índice
`trx-no-reconocida-cases`, documento `doble_cobro_<cliente>`:

```bash
curl -sk -u admin:admin "https://localhost:9200/trx-no-reconocida-cases/_doc/doble_cobro_13083558"
```

> [!WARNING]
> Con `OPENSEARCH_ENABLED=false` en el `.env` del agente —que es como suele estar
> en local— las fichas se escriben **en memoria** y este `curl` devuelve
> `found: false` aunque el flujo haya dicho que registró. **No es un fallo del
> flujo**: para verlo de verdad hay que poner la variable en `true`.

Usa `_doc/<id>` y **no** `_search`: la búsqueda no ve el documento hasta el
refresh del índice.

### Comprobar el TSEC

> [!IMPORTANT]
> El simulador **no valida** el header `tsec`: sus endpoints responden 200 con un
> token válido, uno inventado o ninguno. **Que el flujo funcione contra el
> simulador no dice nada sobre si el TSEC sirve.**

Para comprobarlo de verdad hay que apuntar al ASO real, y ahí manda
`DC_ASO_API_VERIFY_SSL=false`: el certificado es corporativo y, con la
verificación activa, el `grantingTicket` muere en el handshake, el TSEC queda
vacío y las llamadas salen sin autenticar (el ASO responde 401 y el flujo acaba
en el formulario PQR, **indistinguible de un cliente sin productos**).

> [!WARNING]
> Ojo también con `DC_ASO_BASE_URL`: es un override manual y **gana sobre
> `ASO_SOURCE`**. Si está definida, poner `ASO_SOURCE=real` no cambia nada y las
> peticiones siguen yendo al simulador.

En los logs del `:8006`, cada llamada deja `DOBLE_COBRO ASO REQUEST` con el
estado del token. Cuando dice `tsec_enviado: False`, el motivo lo explica.
