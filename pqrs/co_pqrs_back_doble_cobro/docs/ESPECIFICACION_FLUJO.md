# Especificación del flujo — doble_cobro

El árbol conversacional vive en
`co_pqrs_back_agent/src/domain/workflow/doble_cobro/doble_cobro.yml`. Este
servicio (`:8006`) resuelve las decisiones de negocio; el agente solo pregunta,
enruta y pinta.

## Reparto de responsabilidades

| Capa | Qué hace |
|---|---|
| `general.yml` (agente) | Ruteo transversal: el LLM identifica la tipología y entra al workflow `doble_cobro`. |
| `doble_cobro.yml` (agente) | Árbol de pasos, textos al cliente y destinos. |
| `workflows/doble_cobro_hook.py` (agente) | **Async**: llama a `:8006` y reescribe `current_step`. |
| `actions/doble_cobro.py` (agente) | **Sync**: solo pinta lo que el hook dejó en `captured_data`. |
| Este servicio | Días hábiles, vigencia y detección de duplicados. No persiste nada. |

El hook se engancha por el **nombre de la acción** declarada en el YAML, y el
mapa paso → acción se **deriva del propio YAML al importar**
(`_load_step_actions`). Renumerar el árbol no puede desincronizar el Python.

## Recorrido

```
3.4.0    familia de producto (ahorro / corriente / tarjeta de crédito)
  └─ tarjeta de crédito ──────────────► 3.4.0.pqr_tarjeta_credito  [formulario PQR]
3.4.0.1  cuentas + tarjetas débito del cliente (GET  /productos-activos)
  └─ sin productos ──────────────────► 3.4.0.1.pqr                 [formulario PQR]
3.4.0.2  fecha del cobro                      (input_type: date)
3.4.0.3  GATE vigencia                        (POST /validar-vigencia)
  ├─ settlement_pending ─────────────► 3.4.0.3.pendiente           [fin]
  ├─ report_window_expired ──────────► 3.4.0.3.pqr                 [formulario PQR]
  ├─ franchise_expired ──────────────► 3.4.0.3.pqr                 [formulario PQR]
  └─ ok ─────────────────────────────► 3.4.0.4
3.4.0.4  monto del cobro                      (input_type: number)
3.4.0.5  GATE recurrencia                     (OpenSearch: ficha del cliente)
  ├─ ya reportada ───────────────────► 3.4.0.5.recurrente          [fin]
  └─ sin reporte ────────────────────► 3.4.0.6
3.4.0.6  selección de grupos duplicados       (POST /grupos-duplicados)
  ├─ sin grupos ─────────────────────► 3.4.0.6.pqr                 [formulario PQR]
  └─ "Reportar seleccionados" ───────► 3.4.0.7
3.4.0.7  GATE registro                        (OpenSearch: escribe la ficha)
  ├─ nada seleccionado ──────────────► 3.4.0.6 (con aviso)
  └─ registrado ─────────────────────► 3.4.0.8
3.4.0.8  CONFIRMA que quedó guardado          (OpenSearch: relee la ficha)
  ├─ legible ────────────────────────► 3.4.0.8.pendiente           [fin]
  └─ no se pudo releer ──────────────► 3.4.0.8.no_procede          [fin]
```

Los gates encadenan en un mismo turno (`3.4.0.7` → `3.4.0.8`): el hook itera
hasta llegar a un paso sin acción, con un tope de `_MAX_GATE_HOPS`.

## Reglas de negocio

### 1. Días hábiles de conciliación

Antes de reclamar hay que dejar que el comercio concilie. Se cuentan **días
hábiles colombianos** (lunes a viernes menos los 18 festivos, con el traslado de
la Ley Emiliani y los festivos derivados de la Pascua — se calculan, no se
mantienen en tabla: `domain/doble_cobro/business_days.py`).

Son **`DC_SETTLEMENT_DAYS` = 7 días hábiles para todos los productos**: cuentas
de ahorro, cuentas corrientes y tarjetas débito por igual.

El número que ve el cliente lo inyecta el hook en el texto del paso
`3.4.0.3.pendiente`, así que no queda quemado en el YAML y cambiar la variable
cambia también el mensaje.

### 2. Vigencia

Se evalúan **en orden** y la primera que falla manda:

1. **Plazo general**: la fecha debe estar dentro de los últimos
   `DC_MAX_REPORT_MONTHS` = 6 meses.
2. **Vigencia de franquicia**: VISA 180 días, MASTER 120, y **180 (el plazo más
   largo) para una marca no reconocida** — AMEX, Diners o un dato incompleto.
   Solo aplica a tarjetas; una cuenta no tiene marca. La franquicia se deduce
   del BIN del PAN (4 = VISA; 5 y 2 = MASTER), no del nombre del producto.

Como 180 días ≈ 6 meses, la regla 2 solo cambia el resultado en la práctica para
MASTER, en la franja entre 120 días y 6 meses.

**No se distingue el ámbito** (nacional / interoperable / internacional). El
tablero de negocio lo pedía, pero ningún campo del ASO lo indica: `countryId`
describe el país donde se emitió el contrato —siempre `CO`— y no dónde ocurrió
la compra, y la operación de `/cards/v2/operations` no trae país ni red
adquirente. Es el mismo criterio que aplica transacción no reconocida, cerrado
por negocio el 14/08: manda la marca, sin ámbito.

### 3. Detección de duplicados

Dos tolerancias distintas, a propósito:

* **Al buscar** se admite `DC_AMOUNT_TOLERANCE` = ±2000 sobre el monto que
  escribió el cliente, porque rara vez lo recuerda al peso.
* **Al agrupar** se exige monto **idéntico**, mismo comercio y **la misma
  fecha**. Cualquier margen en el monto produciría falsos positivos sobre
  compras distintas del mismo comercio.

**La hora no interviene en el criterio.** Dos cargos iguales del mismo comercio
en la misma fecha son duplicados aunque los separen horas, porque el comercio
puede reprocesar el cobro mucho después del intento original. Como la consulta
al ASO ya filtra por `operationDate`, en la práctica se agrupa dentro del día
consultado; aun así la fecha entra en la llave del grupo para que la función sea
correcta por sí sola.

El comercio se compara normalizado (sin tildes, mayúsculas, sin puntuación): el
ASO devuelve el mismo comercio con espaciado y acentos inconsistentes.

Un movimiento **sin fecha se descarta** — es la única pieza que el criterio no
puede suponer. La hora es opcional: solo se usa para ordenar el grupo y para
mostrarle al cliente cuándo ocurrieron los cargos, así que un `hourOperation`
ausente en el ASO real no impide detectar el duplicado.

## Fuente de movimientos

`GET /cards/v2/operations`, el mismo endpoint que usa
`co_pqrs_back_trx_noreconocida`, filtrando por `operationDate` (AAAAMMDD) en
origen y recorriendo la paginación.

* Producto **tarjeta** → `cardId` = PAN.
* Producto **cuenta** → `accountId` = contrato.

> **Asunción a confirmar con el ASO real**: el simulador acepta `accountId`
> (`key = card_id or account_id` en su `fastapi_app.py`). Si el ASO real solo
> admite `cardId`, hay que resolver antes el PAN de la tarjeta débito asociada a
> la cuenta. Es un cambio de adaptador en `DobleCobroAsoClient.operations`, no
> de diseño. Nótese que `financial-overview` **no** trae hoy esa relación:
> `relatedContracts` viene vacío y `detail.agreementContract` no coincide con
> ningún id de cuenta en ninguno de los 23 fixtures del simulador.

El nombre del comercio viaja en el **5.º bloque de `observations`** en el ASO
real; `descProvision` allí trae un estado ("ACEPTADA"), no un comercio. Cuando
`observations` no trae los cinco bloques se cae a `descProvision` /
`placeOperation`. Es la misma fragilidad documentada en TXNR y afecta
directamente al criterio "mismo comercio".

## Registro del caso

El caso **no se guarda en este servicio**: vive en OpenSearch y lo escribe el
agente, en el mismo índice durable y con la misma estructura que transacción no
reconocida (`trx-no-reconocida-cases`). Así el job de exportación a Tantia lee
los dos flujos sin distinguirlos.

| | |
|---|---|
| Índice | `trx-no-reconocida-cases` |
| Id del documento | `doble_cobro_<client_id>` |
| Discriminador | `tipo_de_notificacion: "doble_cobro"` |
| Hito / desenlace | `completed_report` / `devolucion` (los mismos que TXNR, para que el filtro del job no cambie) |
| Transacciones | `trx_case_state_snapshot.tantia_items[]`, **una por grupo duplicado** |

El prefijo del id es lo que impide que doble cobro y transacción no reconocida
se pisen la ficha del mismo cliente. Transacción no reconocida conserva su id
histórico (el `client_id` a secas) para no invalidar lo ya guardado.

### Cuántas transacciones se reportan

**Una por grupo duplicado**, sin importar cuántos cargos tenga el grupo.

Negocio revisa el caso mirando los movimientos del cliente, así que con un cargo
del grupo le basta para ubicarlo: si el mismo cobro aparece tres veces,
reportarlo tres veces solo repite la misma información.

Se envía el **segundo** cargo del grupo (el primer repetido), porque el más
antiguo es el legítimo y no es el que se reclama.

| El cliente marca | Filas en el CSV |
|---|---|
| 2 cargos iguales | 1 |
| 3 cargos iguales | 1 |
| 2 grupos distintos | 2 |

Cada elemento de `tantia_items` se convierte en **una fila** del CSV de Tantia:
el job recorre la lista y no reagrupa nada.

### El bot no gestiona estados

El flujo **solo deja la información reposada**. No escribe ni interpreta ningún
estado de gestión: negocio toma el registro y lo trabaja por su cuenta, y eso
queda fuera del alcance del agente.

Por eso la recurrencia (`3.4.0.5`) únicamente distingue si **existe o no** un
reporte previo para esa transacción, y el paso `3.4.0.8` se limita a comprobar
que la escritura quedó legible antes de comunicarle al cliente el plazo de
abono. El registro es acumulativo: reportar un cobro nuevo conserva los
anteriores.

### Cuándo se reemplaza un reporte previo

La llave del reemplazo es **producto + fecha de la transacción + monto exacto**.
Reportar dos veces la misma transacción la sustituye en vez de duplicarla, que
es lo que permite corregir un reporte sin que el cliente vea «ya tenemos un
cobro registrado».

El margen de ±`DC_AMOUNT_TOLERANCE` **no interviene aquí**: solo sirve para
buscar qué movimientos se le muestran. Al guardar, el monto se compara al
centavo. Por eso dos cobros duplicados distintos del mismo día conviven, aunque
el cliente los haya encontrado con la misma búsqueda.

> Caso límite conocido: el comercio no entra en la llave. Dos cobros duplicados
> del mismo día, mismo producto y **exactamente el mismo monto** pero de
> comercios distintos se pisarían entre sí.

### Datos del titular pendientes

`customer_name`, `personal_id`, `customer_mail` y `customer_id` (código
Altamira) se escriben **vacíos**. En transacción no reconocida vienen de
PostgreSQL a través de los productos; doble cobro resuelve los suyos contra el
ASO, que no trae datos del titular. Los campos quedan declarados con la misma
forma para que solo haya que rellenarlos al integrar `co_pqrs_back_data`.

## Endpoints

| Método | Ruta | Paso |
|---|---|---|
| `GET` | `/health` | — |
| `GET` | `/v0/doble-cobro/productos-activos?customer_id=&family=` | 3.4.0.1 |
| `POST` | `/v0/doble-cobro/validar-vigencia` | 3.4.0.3 |
| `POST` | `/v0/doble-cobro/grupos-duplicados` | 3.4.0.6 |

`family` acepta `SAVING`, `CHECKING` o `CREDIT_CARD`; vacío no filtra.

## Pendientes

* **Radicación en Salesforce** para el camino `3.4.0.3.pqr` (fecha fuera de
  plazo). El Salesforce que existe en TXNR es de **solo lectura** (consulta de
  recurrencia); crear un caso es integración nueva.
* Confirmar `accountId` contra el ASO real (ver arriba).
* La salida `3.4.0.8.no_procede` solo se alcanza como fail-closed: cuando el
  caso no se pudo escribir o releer. Nunca por una decisión de negocio.
