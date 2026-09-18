# Estrategia — simplificación de llamadas, filtro de montos, descripción y fechas

**Fecha:** 18/08/2026 · Responde a los cinco puntos planteados por Fabián. Cada uno se
ha **verificado contra el código antes de proponer nada**: dos ya están hechos, uno no se
puede hacer como se plantea, y dos son trabajo real.

---

## Resumen ejecutivo

| # | Petición | Estado verificado |
|---|---|---|
| 1 | Fusionar listado y confirmación en una sola llamada ASO | ⚠️ **son dos servicios ASO distintos** — se propone otra simplificación que sí aplica |
| 2 | Listar sólo compras entre $35.000 y $500.000 | ✅ **ya se hace** — el filtro viaja al ASO |
| 3 | `[Descripción]` desde `descProvision` | 🔧 hoy usa `concept`; propuesta de cascada |
| 4 | Fechas resilientes: aceptar `DD-MM-AAAA` | ✅ **ya se acepta** — y dos formatos más |
| 5 | ¿Los mensajes dinámicos se presentan bien? | ✅ verificado con 61 comprobaciones automáticas |

---

## 1 · Fusionar las dos llamadas — el matiz que cambia la conclusión

**Lo que se propone:** que el listado (`2.4.0.1.9`) y la confirmación (`2.4.0.1.11`) usen
una sola llamada, porque atacan el mismo servicio ASO.

**Lo que hay:** no es el mismo servicio. Son dos, con contratos distintos:

| Paso | Servicio ASO | Ruta | Qué devuelve |
|---|---|---|---|
| Listado `.9` | `transaction-cards` (SMGG20239270) | `/cards/v2/cards/{card_id}/transactions` | lista del día: `id`, `concept`, importe, fecha, estado |
| Detalle `.10 → .11` | `detalle-transaccion` (SMGG20262667) | `/cards/v2/operations` | por operación: `descProvision`, `eci`, `eCard`, `responseOperati`, `dateOper`… |

Los campos que deciden el flujo de Luis —**ECI, eCard y `responseOperati`**— sólo existen
en el **segundo**. El listado no los trae. Por eso no se pueden fusionar sin perder la
clasificación (devolución / PQR / presencial / reversado).

### La simplificación que SÍ aplica, y es la mitad de las llamadas

Hoy el detalle se pide **una vez por movimiento elegido**, y `/cards/v2/operations`
devuelve **todas las operaciones del día** (`operationDate` + `cardId`, `pageSize=100`).
Es decir: ya traemos las 3 y usamos 1.

**Propuesta:** pedir `operations` **una sola vez**, junto al listado, y cachear el
resultado por `(card_id, fecha)`. La confirmación se compone del caché, sin segunda
llamada. Efecto:

- **Una llamada ASO menos por cada transacción reportada** (y el bucle admite hasta 3).
- El listado puede enriquecerse con `descProvision` desde el primer momento — que es
  justo el punto 3.
- Si el cliente vuelve por un reenganche a la misma fecha, tampoco se repite.

**Riesgo a vigilar:** `operations` pagina (`pageSize=100`). Con un día de muchos
movimientos habría que recorrer páginas; hoy no se hace y con una sola operación no se
nota. Se añade el caso de prueba.

---

## 2 · Listar sólo entre $35.000 y $500.000 — ya está

El filtro **ya viaja al ASO** como parámetros de la propia consulta, no se hace en
memoria:

```
GET /cards/v2/cards/{card_id}/transactions
    ?fromOperationDate=…&toOperationDate=…
    &operationAmount.fromAmount=35000.0
    &operationAmount.toAmount=500000.0
    &moneyFlow.id=EXPENSE
```

Los valores salen de `TRX_MONTO_MIN` / `TRX_MONTO_MAX` (35.000 / 500.000 por defecto),
parametrizables por entorno.

**Dos consecuencias que conviene que negocio conozca**, porque hoy son invisibles:

1. Un movimiento **fuera de rango no aparece en la lista** y el cliente no sabe por qué:
   ve "no encontramos compras" aunque su compra exista. Propongo **decirlo en el mensaje**
   cuando el listado sale vacío ("sólo se muestran compras entre $35.000 y $500.000").
2. `moneyFlow.id=EXPENSE` excluye los **abonos**, pero el tablero pide *"son todos los
   movimientos, inclusive los abonos"*. **Contradicción entre el tablero y el código** —
   hay que decidir cuál manda.

---

## 3 · `[Descripción]`: hoy `concept`, propuesta de cascada

| Origen | Campo | Valor en el fixture |
|---|---|---|
| Listado (`transactions`) | `concept` | `COMPRA FALABELLA CALLE 80` |
| Detalle (`operations`) | `descProvision` | `COMPRA FALABELLA CALLE 80` |

En el simulador **coinciden**, así que hoy no se nota la diferencia. Con ASO real pueden
divergir: `descProvision` es la glosa del establecimiento y suele ser más precisa.

**Propuesta:** `descProvision` cuando esté disponible (que con el punto 1 lo estará ya en
el listado), y `concept` como respaldo. Nunca vacío. Una línea, con prueba de
degradación.

---

## 4 · Fechas resilientes — ya se acepta `DD-MM-AAAA`

El parser admite hoy **tres formatos**:

```python
for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
```

Es decir, `06/08/2026`, `2026-08-06` y `06-08-2026` funcionan (verificado en la ejecución
del 18/08, casos U-9c y U-9d). Lo que **no** se acepta es `6/8/2026` sin ceros.

**Propuesta:** añadir los formatos sin ceros (`%-d/%-m/%Y` vía normalización) y **dejar el
mensaje pidiendo `DD/MM/AAAA`** — se es tolerante al recibir y estricto al pedir, que es
lo correcto. Lo que **no** haría es aceptar formatos ambiguos como `03/04/2026` con
interpretación variable: eso ya está resuelto porque el día va primero, y conviene no
tocarlo.

**Y un hueco real detectado:** una **fecha futura** (`31/12/2099`) hoy responde "no
encontramos compras" en vez de rechazarla. Propongo rechazo explícito.

---

## 5 · ¿Se presentan bien los mensajes dinámicos?

Sí, y con red permanente: `verificar_mensajes.py` comprueba **61 puntos** en los cuatro
mensajes con datos del cliente —selector, reprompt de fecha, listado y confirmación—
verificando **procedencia** (que cada dato salga de la clave correcta), **formato** del
tablero, **degradación** (nunca un crudo en pantalla) y **ciclo de vida**.

Los tres defectos que hubo en esta área están cerrados: fecha en ISO (H-03), aviso
pegado (H-07) y `*XXXX` literal (H-08).

---

## Plan de ejecución

| # | Trabajo | Estimación |
|---|---|---|
| 1 | Caché de `operations` por `(card_id, fecha)`: una llamada en vez de N | 2 h |
| 2 | `descProvision` con respaldo a `concept`, y en el listado | 45 min |
| 3 | Fechas sin ceros + rechazo de fecha futura | 45 min |
| 4 | Mensaje explícito cuando el listado sale vacío por el filtro de montos | 30 min |
| 5 | Casos nuevos: paginación, fecha futura, formato sin ceros, listado vacío por rango | 1 h |
| 6 | Actualizar plan de UI, Excel y documento único | 45 min |

**≈ 1 jornada.** Dos decisiones de negocio pendientes, que no bloquean:

- **¿Los abonos se listan o no?** El tablero dice que sí; el código los excluye.
- **¿Se avisa al cliente del filtro de montos** cuando su compra queda fuera?

---

## Contrastación (double check) — a rellenar al ejecutar

Cada afirmación de este documento se re-verifica **después** de implementar, con el
comando que la prueba. Si algo no cuadra, se anota aquí antes de dar la fase por buena.

| # | Afirmación a contrastar | Cómo se comprueba | Resultado | Fecha |
|---|---|---|---|---|
| 1 | El detalle se pide **una sola vez** por fecha, no una por movimiento | `docker logs trx-esqueleto \| grep -c "operations"` durante un recorrido con 3 movimientos → debe ser **1** | ✅ **1 llamada** · 3 detalles distintos (TXC01/02/03) → una sola petición a `/cards/v2/operations` | 18/08 |
| 2 | La confirmación se compone del caché y **coincide** con la llamada directa | `verificar_mensajes.py` (procedencia contra la fuente) | ✅ · `verificar_mensajes.py` 61/61; la confirmación muestra `descProvision` | 18/08 |
| 3 | El filtro de montos sigue viajando al ASO | `grep "operationAmount.fromAmount" ` en el log del simulador | ✅ · `operationAmount.fromAmount=35000.0&toAmount=500000.0` en la consulta al ASO | 18/08 |
| 4 | `[Descripción]` usa `descProvision` y cae a `concept` si falta | prueba de degradación con payload sin `descProvision` | ✅ · `descProvision` con respaldo a `concept`; prueba de degradación incluida | 18/08 |
| 5 | Los formatos de fecha aceptados son los previstos, ni más ni menos | tabla de formatos en prueba unitaria: `06/08/2026`, `06-08-2026`, `2026-08-06`, `6/8/2026` ✔ · `31/12/2099` ✘ | ✅ · `06/08/2026`, `06-08-2026`, `2026-08-06`, `6/8/2026` ✔ · `31/12/2099` ✘ con aviso propio | 18/08 |
| 6 | Ningún caso del documento de UI quedó desalineado | `contrastar.py`: los recorridos documentados vs la realidad → **25/25** | ✅ **25/25** · `contrastar.py` tras actualizar el documento por el nuevo aviso | 18/08 |
| 7 | Sin regresión en lo ya cerrado | suite 17/17 · contrato 25/25 · mensajes 61/61 · unitarias | ✅ · suite 17/17 · contrato 25/25 · mensajes 61/61 · servicio 40 · agente 314 | 18/08 |
| 8 | El diagrama refleja el flujo implementado, no el deseado | recorrer el mermaid contra el YAML paso a paso | ✅ · 13/13 nodos clave del YAML reflejados (verificado por script) | 18/08 |

**Criterio de cierre:** las 8 casillas marcadas, con la evidencia pegada en la columna de
resultado. Lo que no se pueda contrastar se declara aquí como tal, en vez de darse por
hecho.
