# CSV para el RPA de Tantia — Estructura del archivo

> **Estado: 2026-08-24.** Este documento **reemplaza** a `EXCEL_TANTIA.md`.
> El Excel de 21 columnas con una fila por caso quedó eliminado; hoy se genera un
> **CSV de 20 columnas con una fila por TRANSACCIÓN**.

Módulo: `co_pqrs_back_trx_tantia_export`

---

## 1. Formato acordado

| | |
|---|---|
| Formato | CSV separado por `;`, con encabezado |
| Nombre | `DDMMAAAATxrNoReconocida.csv` (ej. `21082026TxrNoReconocida.csv`) |
| Subcarpeta | `ficheros_rpa` |
| Ruta desarrollo | `\\82.250.88.90\tx\RECEPCION_HOST\XC\STG\automatizacion_pqrs` |
| Ruta producción | `\\co.igrupobbva\tx\RECEPCION_HOST\XC\STG\automatizacion_pqrs` |
| Codificación | `utf-8-sig` (BOM, para que Windows respete los acentos) |
| Corte | 16:00 (America/Bogota) |
| Ejecución | Únicamente días hábiles |

**Granularidad: una fila por transacción.** Si el cliente reportó 3 transacciones
y las 3 llegaron al abono automático, se escriben 3 filas.

**El fichero se entrega SIEMPRE, tenga datos o no.** Es un fichero de **corte**:
Tantia espera uno por cada día hábil, y uno con solo encabezado significa "en esta
ventana no hubo abonos". Su ausencia sería ambigua (¿no hubo, o falló el proceso?).

Si el fichero del día **ya existe** porque una corrida anterior sí tuvo datos, se
**conserva intacto**: nunca se truncan filas ya entregadas.

> **Excepción deliberada:** si falla la conexión con OpenSearch, el job **falla** y
> NO entrega fichero. Un CSV vacío diría "no hubo abonos" cuando en realidad no se
> pudo consultar.

---

## 2. Las 20 columnas y su origen

| # | Columna | Origen |
|---|---|---|
| 1 | `fecha_recepcion` | Momento del flujo, formato `DD/MM/AAAA` |
| 2 | `numero_producto` | **TDC** → tarjeta de 16 dígitos (`trx_card_id`, del Financial)<br>**PASIVO** → `contract_id` |
| 3 | `numero_extracto` | ASO · `statementDetail.statementId` |
| 4 | `numero_operacion` | ASO · `statementDetail.movementId` |
| 5 | `fecha_compra` | ASO · `dateOper`, convertido a `DD/MM/AAAA` |
| 6 | `nombre_titular` | Postgres · `customer_name` |
| 7 | `documento_cliente` | Postgres · `personal_id` **sin los 5 ceros de la izquierda** |
| 8 | `tipo_producto` | Postgres · `product_desc` |
| 9 | `valor_compra` | ASO · `amountOperation.amount` |
| 10 | `valor_intereses` | ASO · `interest` |
| 11 | `valor_total_abonado` | `valor_compra + valor_intereses` |
| 12 | `referencia_altamira` | Postgres · `customer_id` (código Altamira) |
| 13 | `codigo_autorizacion` | ASO · `responseOperati` |
| 14 | `id_reclamo` | `customer_id` + `_` + fecha de recepción |
| 15 | `id_referencia` | *vacío* |
| 16 | `correo_notificacion` | Postgres · `customer_mail` |
| 17 | `estado_abono` | *vacío* |
| 18 | `Habilitador` | *vacío* |
| 19 | `estado_notificacion` | *vacío* |
| 20 | `Observaciones` | *vacío* |

Los campos vacíos los completa el RPA/Tantia.

### Columnas técnicas
Al final se añaden `_dedup_key` y `_conversation_id`, que permiten el *append*
incremental sin repetir transacciones. **No forman parte del layout entregado** y
el RPA las ignora. La clave de deduplicación es
`client_id | statementId | movementId`.

---

## 3. Cómo llega el dato al CSV

```
1. El cliente llega al abono automático (paso 2.4.0.1.20)
        ↓  (en ese instante)
2. El agente acumula la transacción en trx_case_state.tantia_items
   y registra el hito en el índice durable trx-no-reconocida-cases
        ↓  (a las 16:00, días hábiles)
3. El CronJob lee el índice, filtra los casos con outcome=devolucion
   actualizados hoy, y convierte cada tantia_items en una fila
        ↓
4. Escribe/append en el CSV del día, en la carpeta de red montada en el pod
```

El append **no es en tiempo real**: el abono va a OpenSearch al instante, pero el
CSV se escribe una sola vez al día.

### Ventana de corte
El fichero de un día hábil cubre **desde el corte del día hábil anterior hasta el
corte de hoy**. Las 16:00 son una **fecha de corte**, no un simple filtro por día.

| Día del job | Ventana que cubre |
|---|---|
| Martes | martes 16:00 ← **lunes 16:00** |
| Lunes | lunes 16:00 ← **viernes 16:00** (incluye viernes tras el corte, sábado y domingo) |
| Después de un festivo | se salta el festivo y arranca en el día hábil anterior |

Las ventanas son **contiguas y no se solapan**: el fin de una es el inicio de la
siguiente. Así cada transacción se entrega **exactamente una vez**, sin huecos ni
duplicados, y lo posterior al corte de hoy sale en el fichero del próximo día
hábil.

Ejemplo verificado (job del lunes 24 a las 16:00):

```
viernes 15:00  → NO entra (ya salió en el fichero del viernes)
viernes 18:00  → entra ✓
sábado         → entra ✓
domingo        → entra ✓
lunes 10:00    → entra ✓
lunes 17:00    → NO entra (sale en el fichero del martes)

Ventana: 2026-08-21T21:00:00Z -> 2026-08-24T21:00:00Z
24082026TxrNoReconocida.csv -> 4 transacciones
```

La deduplicación se hace solo contra el fichero de hoy, como protección ante una
re-ejecución manual del job: la ventana ya garantiza que no hay solape con cortes
anteriores.

### Requisito en el agente
Antes, `update_trx_state(tantia=...)` **sobrescribía** el payload en cada vuelta
del bucle y `reset_per_tx` borraba el detalle, así que el registro durable
conservaba solo la última transacción. La lista `tantia_items` es lo que hace
posible una fila por transacción.

Si un caso no tiene `tantia_items` (registros anteriores al cambio), se usa
`tantia` como respaldo y se genera una sola fila, para no perder el caso.

---

## 4. Variables de entorno

| Variable | Default | Notas |
|---|---|---|
| `RUTA_PROCESO` | `/mnt/ada_data` | Raíz del recurso de red montado |
| `TANTIA_FOLDER_NAME` | `ficheros_rpa` | Subcarpeta |
| `CSV_DELIMITER` | `;` | |
| `CSV_ENCODING` | `utf-8-sig` | |
| `FESTIVOS` | *(vacío)* | Días no laborales **adicionales** `YYYY-MM-DD` por coma. Los festivos nacionales ya se calculan |
| `TRX_CASES_INDEX` | `trx-no-reconocida-cases` | |
| `HORA_CORTE` | `16` | Hora de corte (America/Bogota) |
| `MAX_DIAS_ATRAS` | `10` | Tope al buscar el día hábil anterior (protección ante puentes largos) |
| `CAMPO_CODIGO_AUTORIZACION` | `responseOperati,process.responseOperati,codigo_autorizacion` | Candidatos por coma, admite rutas con punto |
| `CAMPO_INTERES` | `interest,interes,valor_intereses` | Ídem |
| `LOG_LEVEL` | `INFO` | |

Los campos del ASO son **configurables a propósito**: si el contrato cambia un
nombre, se ajusta en el ConfigMap sin tocar código ni reconstruir la imagen.

---

## 5. Días hábiles y festivos

El cron es `0 16 * * 1-5`, que solo distingue días de la semana. Los **festivos
colombianos se calculan en código** con la librería `holidays`, que ya implementa
la Ley Emiliani (traslado al lunes siguiente) y los festivos ligados a la Pascua.

`es_dia_habil` aplica tres filtros, en orden:
1. Fin de semana.
2. **Festivo nacional colombiano** (calculado, cualquier año).
3. Lista manual `FESTIVOS`, para días no laborales que **no** son festivos
   nacionales (un cierre bancario, un día cívico). Complementa el cálculo, no lo
   reemplaza.

En un festivo el job **no genera fichero**, y la ventana del siguiente día hábil
**cubre el festivo completo**, así que no se pierde ningún abono:

```
martes 13/01/2026 (el lunes 12 fue festivo)
Ventana de corte: 2026-01-09T21:00:00Z -> 2026-01-13T21:00:00Z
                  (viernes 16:00)          (martes 16:00)
→ 4 transacciones: viernes tras el corte, sábado, LUNES FESTIVO y martes
```

### Por qué la librería y no un cálculo propio
Se implementó el algoritmo a mano primero y **se omitió uno de los 19 festivos de
2026**: Nuestra Señora del Rosario de Chiquinquirá (9 de julio, trasladado al lunes
13). Un olvido así no se nota hasta que el corte de un día sale mal. La librería
también destapó que un test usaba `2026-08-17` como "lunes normal" cuando es La
Asunción trasladada.

Si la librería no estuviera disponible en la imagen, el código **se degrada** a
excluir solo fines de semana y la lista manual, dejando una advertencia en el log:
es preferible generar un fichero de más que romper el job.

---

## 6. Garantías del modelo de corte

Esta sección resume **qué está garantizado** y por qué, para no tener que
reconstruirlo leyendo el código.

### G1 — Los datos se traen en función del día hábil
La ventana de un fichero es `[corte del día hábil anterior, corte de hoy)`. Tanto
el extremo inicial como la decisión de generar el fichero usan la **misma**
función `es_dia_habil`, que excluye fines de semana, festivos nacionales
colombianos calculados y la lista manual. No hay dos criterios distintos de "día
hábil" en el módulo.

### G2 — Ninguna transacción se pierde
El extremo inicial de una ventana es **exactamente** el extremo final de la
anterior. Como las ventanas son contiguas, todo instante del calendario pertenece
a alguna ventana: lo que ocurre en fin de semana o en festivo entra en la ventana
del siguiente día hábil.

### G3 — Ninguna transacción se entrega dos veces
Por la misma contigüidad: los intervalos son semiabiertos `[gte, lt)`, así que un
`updated_at` cae en una sola ventana. La deduplicación contra el fichero del día es
una **segunda** red, solo para el caso de re-ejecutar el job manualmente.

### G4 — Siempre hay fichero en un día hábil
Con datos o sin ellos. Un CSV con solo encabezado significa "en esta ventana no
hubo abonos".

### G5 — Un fallo nunca se disfraza de "no hubo abonos"
Se distinguen dos situaciones que producen cero filas:

| Situación | Resultado |
|---|---|
| Índice inexistente (nadie ha llegado al abono) | fichero vacío, código 0 |
| **Fallo de conexión** con OpenSearch | **el job falla**, no se entrega fichero |

Sin esa distinción, una caída de OpenSearch le diría a Tantia que no hubo abonos.

### G6 — Un fichero ya entregado no se modifica
Las filas nuevas se escriben **siempre** en el fichero de hoy, nunca en el de un
día anterior. Y si el de hoy ya existe con datos, se hace *append*: nunca se
trunca.

### Cómo verificarlo
Los tests que sostienen cada garantía:

| Garantía | Test |
|---|---|
| G1 | `ColombianHolidayTests` · `WindowSkipsHolidaysTests` |
| G2 | `test_no_data_is_lost_across_a_holiday` |
| G3 | `test_windows_are_contiguous_and_do_not_overlap` · `test_windows_remain_contiguous_around_a_holiday` · `test_rerun_does_not_duplicate_or_truncate` |
| G4 | `test_empty_window_still_delivers_the_file` · `test_missing_index_still_delivers_the_cutoff_file` |
| G5 | `test_connection_error_must_not_deliver_an_empty_file` |
| G6 | `test_existing_file_is_preserved_when_there_is_nothing_new` · `test_append_does_not_repeat_the_header` |

```bash
cd co_pqrs_back_trx_tantia_export && uv run --extra dev pytest -q
# 57 tests
```

### Ejemplo verificado de punta a punta
Job del martes 13/01/2026, con el lunes 12 festivo:

```
Ventana de corte: 2026-01-09T21:00:00Z -> 2026-01-13T21:00:00Z
                  (viernes 16:00)          (martes 16:00)

13012026TxrNoReconocida.csv -> 4 transacciones
   viernes 9 tras el corte · sábado 10 · LUNES 12 FESTIVO · martes 13
```

Y el caso del fin de semana, job del lunes 24/08/2026:

```
viernes 15:00  → NO entra (ya salió en el fichero del viernes)
viernes 18:00  → entra ✓        sábado → entra ✓
domingo        → entra ✓        lunes 10:00 → entra ✓
lunes 17:00    → NO entra (sale en el fichero del martes)
```

---

## 7. Comportamiento ante el índice inexistente

El índice `trx-no-reconocida-cases` lo crea el **agente** en la primera devolución
automática. Mientras eso no ocurra —y en producción el flujo entra cerrado por el
portón— el índice **no existe**.

Ese caso se trata como "no hubo abonos", **no** como error: el job registra un
mensaje informativo, **entrega el fichero de corte vacío** y sale con código 0.
Antes salía con código **1**, es decir el CronJob se marcaba como fallido todos los
días y Tantia no recibía nada.

---

## 8. Puntos abiertos

1. **Encabezado sin acento.** Se escribió `codigo_autorizacion`, no
   `código_autorizacion`, para evitar problemas de codificación en el RPA. A
   confirmar con Tantia.
3. **PVC `smb-pvc-tx`.** El cronjob monta ese volumen, que **no está definido en
   el IaC** (solo referenciado, igual que en los otros tres cronjobs que ya
   existían). Es un recurso provisionado fuera del repositorio: conviene
   verificar que exista antes de aplicar.
