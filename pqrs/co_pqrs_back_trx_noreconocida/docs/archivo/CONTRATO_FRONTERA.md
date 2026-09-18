# Contrato de la frontera — tramo Pablo → tramo Luis · **v1** (13/08/2026)

**La frontera:** la arista `2.4.0.1.11 → 2.4.0.1.12`. Mi tramo termina cuando el cliente
pulsa **"Sí, continuar con el reporte"** en la confirmación; el gate `.12`
(`validar_pendiente_trx`) y todo lo que sigue es de Luis.

**Este contrato no es un JSON inventado**: son las claves que los gates escriben de
verdad en `flow_answers` / `captured_data`, capturadas de una conversación real
(cliente C, 13/08) y **fijadas con un verificador ejecutable**:
`docs/pruebas/verificar_contrato.py` — 25 comprobaciones. Si cualquiera de los dos
cambia una clave, el verificador falla. Correrlo es parte de la definición de hecho de
ambos tramos.

**Cambios de versión:** cualquier renombre/eliminación de clave sube la versión aquí y
en el verificador, **de acuerdo entre los dos**, no por sorpresa.

---

## 1 · Lo que entrego (garantizado al cruzar la frontera)

### En `flow_answers` (las fija el `save_as` del YAML)

| Clave | Ejemplo real | Nota |
|---|---|---|
| `trx_cantidad` | `"1"` | 1–3; "Más de 3" nunca llega aquí (sale por `.1.1.pqr`) |
| `producto_trx_no_reconocida` | `"producto_1"` | **índice**, no identificador — resolver contra `trx_products_result` |
| `trx_fecha` | `"06/08/2026"` | ya validada: el gate `.8` repregunta las ilegibles (H-01) |
| `trx_movimiento_seleccionado` | `"movimiento_1"` | índice sobre `trx_movimientos_result` |
| `trx_confirmacion_movimiento` | `"si_reportar"` | **la frontera sólo se cruza con este valor**; "no es necesario" cierra por satisfacción y no te llega |

### En `captured_data`

| Clave | Qué lleva | Quién la escribe | Quién la lee en tu tramo |
|---|---|---|---|
| `trx_card_id` | PAN resuelto (`4912680517940060`) | gate `.8` | los bloqueos (`_trx_bloqueo`) |
| `trx_vigencia` | `"vigente"` (si no, no se cruza) | gate `.8` | — |
| `trx_index` | `"1"` | gate `.1` | el bucle multi-transacción (`.20.1 → .3`) |
| `trx_products_result` | respuesta completa de productos; `[idx]` trae **`origin_flag` (`TDC`/`Pasivo`), `last_four`, `card_brand`, `card_id`** y `last_four_origen` | gate `.4` | tu rombo **"¿Compra con TC?"** |
| `trx_movimientos_result` | listado del día consultado | gate `.8` | referencia |
| `trx_detalle_result` | detalle crudo de operations: `id`, `responseOperati`, `eci`, `eCard`, `dateOper`, `hourOperation`, `descProvision`, `placeOperation`… (21 campos) | gate `.10` | tus reglas ECI / reversado |
| `trx_clasificacion` | **precalculada** por `aso_rules` sobre el detalle: `{pendiente_tdc, eci, ecard, reversado, response, resultado}` | gate `.10` | tu gate `.12` y el ruteo de `.19` **ya la consumen** |
| `trx_salesforce_result` | recurrencia con `targetUserId` (`{personal_type}-{personal_id}`) | gate `.1` | radicación Salesforce |

### Decisión que esto resuelve (pregunta 3 de la estrategia)

Consumes **`trx_clasificacion`** — es lo que tu gate `.12` ya hace. El crudo
(`trx_detalle_result`) viaja al lado por si necesitas un campo más, pero la regla vive
en `aso_rules.py` y **se cambia allí**, no reinterpretando el crudo en el flujo. Así no
reimplementas la clasificación ni divergimos en la semántica del ECI.

---

### Los últimos 4 vienen del PAN, no del contrato (18/08)

`last_four` se reescribe en el gate `.4` con los **últimos 4 del `card_id` de
financial-overview**, y `card_id` viaja en el mismo producto. `last_four_origen` dice de
dónde salió: `financial_overview` (lo normal) o `ada_fallback` (si FO no respondió).

**Para tu tramo:** usa `last_four` tal cual llega —ya es el del PAN— y `card_id` para
cualquier llamada. El `last_four_pan_id` de ADA queda solo como llave de cruce interna;
no lo muestres ni lo propagues.

## 2 · Trampas conocidas (verificadas, no teóricas)

1. **`trx_products_map` NO es fuente**: es la copia de presentación y **pierde**
   `origin_flag` y `last_four`. Consumir siempre `trx_products_result[idx]`. El
   verificador lo avisa.
2. **Los índices** (`producto_N`, `movimiento_N`) sólo tienen sentido contra el
   `*_result` de **esta** conversación. En el bucle multi-transacción (`.20.1 → .3`)
   los resultados se renuevan: no guardes referencias viejas.
3. La conversación cruza con `trx_vigencia == "vigente"` siempre; si te llega otra
   cosa, es una regresión mía, no un caso a manejar.

---

## 3 · El hueco que ninguno de los dos puede cerrar solo

**Tu regla de 7 días (cruce MC30) no tiene insumo.** En el detalle hay `dateOper` (fecha
de la **operación**) — no hay `postingDate`/fecha de **cruce**. Contar los 7 días desde
`dateOper` sería inventarse la semántica. Está preguntado a Data (pregunta 12 de la
estrategia); hasta que responda, `pendiente_tdc` se queda como está
(`TDC && responseOperati=='pendiente'`, sin fechas) **y eso hay que decirlo en la
demo**, no esconderlo.

---

## 4 · Zonas compartidas — reglas para no pisarnos

| Zona | Regla |
|---|---|
| `_prefetch_trx_data_if_needed` (chat_service) | una sola función con los gates de ambos. **Bloques por dueño con comentario de cabecera**; cada PR toca sólo bloques propios. Si Fabián acepta, refactor a dispatch `{step: handler}` con módulos por dueño (propuesto, pregunta 2) |
| helpers `_trx_*` compartidos (`_trx_clasificacion`, `_trx_bloqueo`, `_trx_origin_flag`…) y `aso_rules.py` | cambio = aviso previo en el canal + correr `verificar_contrato.py` antes del push |
| `satisfaction_check` / `shared_steps.yml` | **de nadie**: lo usan todos los flujos del bot. Cambios sólo con acuerdo de los tres |
| la arista de vuelta `.20.1 → .2.4.0.1.3` (bucle) | nace en tu tramo y aterriza en el mío: cualquier cambio de destino o de estado que arrastre (`trx_index`, limpieza de `*_result`) se acuerda antes |
| índice `trx-no-reconocida-cases` | lo escriben hitos de ambos tramos; el esquema del documento es parte de este contrato (v1 = el de `ESTADO_Y_CONFIG.md`) |

---

## 5 · Cómo se verifica (los dos)

```bash
cd co_pqrs_back_trx_noreconocida/docs/pruebas
curl -sk -u admin:admin -X DELETE https://localhost:9200/trx-no-reconocida-cases
python3 verificar_contrato.py      # CONTRATO OK = 25 comprobaciones
```

Antes de cada push que toque el flujo trx. El caso 112 del documento corporativo de
pruebas referencia esta verificación.
