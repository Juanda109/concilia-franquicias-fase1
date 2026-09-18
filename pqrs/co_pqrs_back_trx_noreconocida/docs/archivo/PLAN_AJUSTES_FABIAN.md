# Plan — ajustes solicitados por Fabián (validación silenciosa, últimos 4, trazas)

**Estado:** propuesta para ejecutar hoy. Cada punto está verificado contra el código
antes de estimar — dos de los tres esconden más de lo que se ve en la UI.

---

## 1 · Eliminar el mensaje "estoy validando…" (la validación sigue en backend)

### Qué pasa hoy, exactamente

Hay **tres** mensajes de validación en el YAML, pero **sólo uno se ve**:

| Paso | Texto | ¿Se ve? |
|---|---|---|
| `2.4.0.1` | *"Gracias. Estoy validando tu caso para continuar con el análisis."* + botón Continuar | **Sí** — es el que Fabián señala |
| `2.4.0.1.4` | *"Estoy validando tus productos activos."* | No: su gate reescribe el paso al llegar y muestra directamente el selector |
| `2.4.0.1.12` | *"Estoy validando el estado de la compra."* | No: ídem, muestra el resultado |

**Por qué `.1` sí se ve:** su gate (recurrencia Salesforce + recurrencia-bot) ejecuta al
llegar, pero en la rama "sin recurrencia" **no reescribe `current_step`** — se queda en
`.1` y pinta su pregunta con el botón. Los otros dos gates sí reescriben. Es una
inconsistencia del esqueleto, no un diseño.

### El cambio

En la rama sin recurrencia del gate `.1`: `current_step = "2.4.0.1.1"` (cantidad) —
**el mismo patrón que ya usan `.4` y `.12`**. La validación ejecuta igual (Salesforce,
bot, hito, trazas); el cliente pasa de elegir el suceso directamente a "¿Cuántas
transacciones…?". Un turno menos.

Los textos de `.4`/`.12` se quedan: sólo aparecen si los gates se saltan
(`TRX_SERVICE_URL` ausente) y ahí **avisan de un despliegue roto** — útil, no ruido.

### Impacto que hay que arrastrar (es lo laborioso, no el cambio)

- **La suite asertaba el mensaje como esperado** (`expect:validando tu caso` +
  `pick:continuar` en el tramo común de ~12 casos): se recorta el tramo común.
- Protocolo: columna "Recorrido" de la tabla E1–E16.
- Excel: columna "Pregunta realizada a Blue" de las filas que citan el camino, y
  **fila nueva** verificando que la validación ya no muestra turno (y que con
  recurrencia el desvío a PQR sigue saliendo directo).
- `verificar_contrato.py`: su CAMINO incluye el "Continuar" — quitarlo.

**Estimación: ~1 h** (10 min el cambio, el resto arrastre + regresión completa).

---

## 2 · Mostrar sólo los últimos 4 dígitos del producto

### Lo que encontré al aterrizarlo — peor que un tema de copy

El builder del selector (`workflow_actions.py:1330`):

```python
last4 = _last4(str(product.get("last_four_pan_id") or product.get("product_id") or ""))
```

Dos problemas reales:

1. **`last_four_pan_id` llega vacío** desde el servicio (publica `last_four` — el
   mismo desajuste de claves que H-08), así que **cae a `product_id`**…
2. …y `product_id` aquí es el **contrato completo** (`00131003201300060`). Hoy "funciona"
   por coincidencia: los contratos sembrados terminan en los mismos 4 que el PAN. Con
   datos reales de ADA, **mostraría los últimos 4 del contrato, no de la tarjeta** — y
   si algún día el label cayera al identificador entero, expondríamos un contrato
   completo en pantalla.

### El cambio

- Leer `last_four` (con `last_four_pan_id` de respaldo), **nunca** `product_id`.
- Sin últimos 4 → `"****"`, jamás un identificador crudo.
- Auditar los otros 3 puntos que pintan `*{last4}` (detalle, contrato-embargos, mapa)
  con el mismo criterio: **ningún identificador completo sale a pantalla**.

### ❓ Una decisión de formato para Fabián antes de tocar

*"Mostrar sólo los últimos cuatro"* admite dos lecturas:

- **(a)** `Tarjeta de Crédito *0060` — tipo + últimos 4 (lo de hoy, con la fuente
  corregida). **Recomendada**: con tarjeta y cuenta en la lista, sólo `*0060` no permite
  distinguirlas, y el tablero muestra `[Producto] •[xxxx]`.
- **(b)** `*0060` a secas — literal a su comentario.

Implementamos (a) salvo que confirme (b); el cambio entre ambas es una línea.

**Estimación: ~45 min** con casos (fila nueva en Excel: "el selector nunca muestra un
identificador completo", verificada con un producto sin `last_four`).

---

## 3 · Trazas de cada paso del flujo

### Inventario real de hoy (por eso el punto de Fabián es justo)

- **Servicio**: bien cubierto — `trace_audit` en `aso_client` (operación, URL, outcome,
  ms por llamada ASO) y 5 eventos en `analysis_service`.
- **Agente**: `_trx_trace_step` existe pero **sólo en 7 puntos**: recurrencia, productos,
  vigencia/fecha-ilegible, bloqueos, devolución, bucle. **Sin traza**: cantidad, rango,
  fecha aceptada, listado mostrado, movimiento elegido, detalle, confirmación, y las
  salidas (.exit/.pqr/reenganches). Un caso a mitad de flujo hoy no se puede reconstruir
  desde logs.

### El cambio (dos capas, patrón ya existente)

1. **Traza genérica de transición** para el flujo trx: al almacenar la respuesta de un
   paso `2.4.*` (motor) y en cada reescritura de gate, un evento uniforme:
   `paso_origen → paso_destino, save_as, valor (enmascarado), outcome`. Un solo punto de
   emisión — no 20 llamadas dispersas que se desincronizan.
2. **Línea consolidada por turno** ("dónde quedó / qué hizo"), como pide
   `ESTADO_Y_CONFIG.md` §3 imitando el patrón de centrales → error_handler → bucket.

**Regla de datos:** en trazas nunca viaja PAN/contrato completo ni texto libre del
cliente — identificadores enmascarados (`*0060`), fechas y outcomes sí.

**Verificación:** caso nuevo de suite que recorre el camino feliz y comprueba contra
`docker logs` que cada paso dejó su línea (el guion ya sabe leer los logs del agente).

**Estimación: ~2 h.** Es el más valioso para OKD: sin esto, el primer incidente en dev
se investiga a ciegas.

---

## Orden propuesto y entrega

| # | Qué | Por qué en este orden |
|---|---|---|
| 1 | Punto 2 (últimos 4) | el más corto y corrige un riesgo de datos real, no sólo copy |
| 2 | Punto 1 (validación silenciosa) | cambia el camino común → conviene antes de re-grabar la suite una sola vez |
| 3 | Regresión completa + arrastre (suite, protocolo, Excel, contrato) | una pasada única con ambos cambios |
| 4 | Punto 3 (trazas) + su caso de verificación | independiente de los otros dos |
| 5 | Push al PR #75 + Excel regenerado | commits separados por punto, como siempre |

**Total estimado: media jornada**, regresión incluida. Único bloqueo posible: la
decisión (a)/(b) del formato — si no hay respuesta, seguimos con (a) y es una línea
cambiarlo.

**Para responder a Fabián con precisión** ("¿lo sabíamos?"): el mensaje de validación lo
teníamos **normalizado como esperado** en la suite — lo vimos y no lo cuestionamos, punto
para él; el desajuste de claves de los últimos 4 es **el tercer caso del mismo patrón**
(products_map, H-08, y ahora el selector) — propondremos en el PR unificar la lectura del
producto en un solo helper para que no haya cuarta; y de las trazas éramos conscientes a
medias (servicio sí, agente incompleto).
