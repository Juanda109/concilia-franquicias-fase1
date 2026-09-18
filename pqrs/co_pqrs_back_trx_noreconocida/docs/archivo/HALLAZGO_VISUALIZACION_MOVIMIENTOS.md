# ¿Se visualizan todos los movimientos? — respuesta verificada

**Fecha:** 19/08/2026 · Responde a la pregunta de Fabián. La respuesta era **no**: la
pérdida ocurría en **tres puntos encadenados**, ninguno visible para el cliente.

> **Estado (19/08, tarde):** los puntos **1 y 2 están corregidos y verificados**. El
> listado muestra hasta 5 movimientos y avisa del resto; cuando el filtro de importe deja
> el día vacío, se le dice al cliente en vez de responder "no hay compras". **Queda
> abierto el punto 3** (abonos), que es decisión de negocio.

---

## La evidencia (cliente K, `1013634968`, creado para esto)

Un día con **7 movimientos** reales en el ASO:

| Movimiento | Importe | Tipo | ¿Llega al cliente? |
|---|---|---|---|
| COMPRA ALKOSTO AV 68 | $120.000 | compra | ✅ |
| COMPRA RAPPI BOGOTA | $89.990 | compra | ✅ |
| COMPRA D1 CHAPINERO | $45.000 | compra | ✅ |
| **COMPRA HOMECENTER CALLE 80** | **$210.000** | compra | ❌ **se pierde por el truncado** |
| COMPRA TIENDA ESQUINA | $20.000 | compra | ❌ filtro de monto mínimo |
| COMPRA ELECTRODOMESTICOS | $750.000 | compra | ❌ filtro de monto máximo |
| ABONO/DEVOLUCION COMERCIO | $60.000 | **abono** | ❌ filtro `moneyFlow=EXPENSE` |

**Resultado medido: el ASO devuelve 7 · el servicio entrega 4 · el cliente ve 3.**

---

## Los tres puntos de pérdida

### 1 · Truncado a 3 en la presentación — 🔴 el más grave

`workflow_actions.py` corta el listado a `movimientos[:3]` porque el YAML sólo define
`movimiento_1..3`. El cuarto movimiento **está dentro de rango, es reportable y el
servicio lo entregó**, pero el cliente no lo ve ni sabe que existe.

Hasta hoy no se había detectado porque **ningún cliente de la matriz tenía más de 3
movimientos**.

### 2 · Filtro de importe sin aviso — 🟠

Las compras fuera de `$35.000–$500.000` no aparecen. La regla de negocio es correcta
—no son reportables por este canal— pero el cliente ve *"estas son tus transacciones"*
sin saber que su compra de $750.000 quedó fuera. Si busca precisamente esa, concluirá
que el banco no la tiene.

### 3 · Los abonos se excluyen, y el tablero pide incluirlos — 🟠

La consulta va con `moneyFlow.id=EXPENSE`, que deja fuera los abonos. El tablero dice
literalmente: *"son todos los movimientos, **inclusive los abonos**"*. **Contradicción
entre el tablero y el código**, no un descuido de implementación: hay que decidir.

---

## Propuestas

| # | Punto | Propuesta | Coste |
|---|---|---|---|
| 1 | Truncado | Ampliar el YAML a `movimiento_1..5` **y** avisar cuando haya más: *"Te muestro los 5 más recientes de ese día"*. Con paginación real si negocio la quiere. | 2-3 h |
| 2 | Filtro de importe | Cuando el ASO devuelva movimientos pero el filtro los deje fuera, decirlo: *"Sólo puedo gestionar compras entre $35.000 y $500.000"*. Hoy el cliente recibe el mismo mensaje que si no hubiera nada. | 1 h |
| 3 | Abonos | **Decisión de negocio**: si se incluyen, quitar `moneyFlow=EXPENSE`; si no, dejarlo y corregir el tablero para que no prometa lo contrario. | 30 min tras la decisión |

**Recomendación:** el 1 y el 2 son de riesgo bajo y quitan dos formas de que el cliente
crea que su compra no existe. El 3 no lo tocaría sin decisión expresa.

---

## Cómo reproducirlo

```bash
./reset_cliente.sh 1013634968
# UI: "No reconozco esta compra" → Compra presencial → 1 → Empezar ahora →
#     Sí, continuar → Tarjeta *4444 → Entre $35.000 y $500.000 → 06/08/2026
```

Se ven 3 de los 7. El cliente K queda en la matriz para que esto no vuelva a pasar
inadvertido: `dev/postgres/04-seed-cliente-k.sql` y fixtures del PAN
`4912680517944444`.
