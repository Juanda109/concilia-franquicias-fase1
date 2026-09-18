# co_pqrs_back_trx_tantia_export

CronJob de **días hábiles a las 16:00 (America/Bogota)** que consolida las
transacciones con **devolución automática** del flujo *Transacción no reconocida*
(paso `2.4.0.1.20`) desde el índice durable de OpenSearch
`trx-no-reconocida-cases` y genera el **CSV para el RPA de Tantia**.

> **Cambio 2026-08-21:** este módulo generaba un Excel de 21 columnas con una fila
> por caso. Ahora genera un **CSV con una fila por TRANSACCIÓN**.
> El Excel quedó eliminado, no conviven.

## Qué hace
1. Verifica que hoy sea **día hábil** (lunes a viernes y que no esté en `FESTIVOS`).
   Si no lo es, termina sin escribir nada.
2. Lee el índice durable `trx-no-reconocida-cases` (docs por cliente, sin TTL).
3. Filtra los casos con `outcome == "devolucion"` y `completed_report` en
   `milestones` cuyo `updated_at` cae en el día (hora Bogotá).
4. Por cada caso, recorre `trx_case_state_snapshot.tantia_items` y emite **una
   fila por transacción**. Si el cliente reportó 3 transacciones y las 3 llegaron
   al abono, salen 3 filas.
5. Escribe o hace **append** al CSV del día, deduplicando por transacción
   (`client_id + statementId + movementId`).

El fichero se genera **todos los días hábiles aunque no haya transacciones**: en
ese caso queda solo con el encabezado. Su ausencia sería ambigua para Tantia
(¿no hubo abonos, o falló el proceso?).

## Formato de salida
| | |
|---|---|
| Formato | CSV separado por `;`, con encabezado |
| Nombre | `DDMMAAAANotificaciones.csv` (ej. `21082026Notificaciones.csv`) |
| Subcarpeta | `ficheros_rpa` |
| Ruta desarrollo | `\\82.250.88.90\tx\RECEPCION_HOST\XC\STG\automatizacion_pqrs` |
| Ruta producción | `\\co.igrupobbva\tx\RECEPCION_HOST\XC\STG\automatizacion_pqrs` |
| Codificación | `utf-8-sig` (BOM, para que Windows respete los acentos) |
| Corte | 16:00 |
| Ejecución | Únicamente días hábiles |

## Columnas (orden exacto)
| # | Columna | Origen |
|---|---|---|
| 1 | `fecha_recepcion` | Timestamp del flujo, formato `DD/MM/AAAA` |
| 2 | `numero_producto` | **TDC** → tarjeta de 16 dígitos (`trx_card_id`, del Financial)<br>**PASIVO** → `contract_id` |
| 3 | `numero_extracto` | ASO · `statementDetail.statementId` |
| 4 | `numero_operacion` | ASO · `statementDetail.movementId` |
| 5 | `fecha_compra` | ASO · `dateOper` → `DD/MM/AAAA` |
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
| 21 | `tipo_de_notificacion` | `trx_no_reconocida` o `doble_cobro` |

Los campos vacíos los completa el RPA/Tantia.

`tipo_de_notificacion` se agregó **al final** para que las 20 columnas anteriores
conserven su posición: el fichero dejó de ser exclusivo de transacción no
reconocida y esta columna dice de qué flujo viene cada fila. Las fichas escritas
antes de que existiera el campo se emiten como `trx_no_reconocida`, que era el
único flujo que alimentaba el índice.

Se añaden al final dos columnas técnicas, `_dedup_key` y `_conversation_id`, que
permiten el append incremental sin repetir transacciones. **No forman parte del
layout entregado** y el RPA las ignora.

## Requisito en el agente
El agente acumula cada transacción que llega al abono en
`trx_case_state.tantia_items`. Esto es indispensable: antes el payload se
**sobrescribía** en cada vuelta del bucle y `reset_per_tx` borraba el detalle, así
que el registro durable conservaba solo la última transacción y era imposible
emitir una fila por cada una.

Si un caso no tiene `tantia_items` (registros anteriores al cambio), se usa
`tantia` como respaldo para no perderlo, generando una sola fila.

## Variables de entorno (las inyecta el CronJob)
| Variable | Default | Notas |
|---|---|---|
| `RUTA_PROCESO` | `/mnt/ada_data` | Raíz del recurso de red montado |
| `TANTIA_FOLDER_NAME` | `ficheros_rpa` | Subcarpeta |
| `CSV_DELIMITER` | `;` | |
| `CSV_ENCODING` | `utf-8-sig` | |
| `FESTIVOS` | *(vacío)* | Festivos colombianos `YYYY-MM-DD` por coma |
| `TRX_CASES_INDEX` | `trx-no-reconocida-cases` | |
| `SCAN_LOOKBACK_DAYS` | `0` | Días hacia atrás además de hoy |
| `CAMPO_CODIGO_AUTORIZACION` | `responseOperati,process.responseOperati,codigo_autorizacion` | Candidatos por coma, admite rutas con punto |
| `CAMPO_INTERES` | `interest,interes,valor_intereses` | Ídem |
| `LOG_LEVEL` | `INFO` | |

Los campos del ASO son **configurables** a propósito: si el contrato cambia un
nombre, se ajusta en el ConfigMap sin tocar código ni reconstruir la imagen.

## Días hábiles y festivos
El cron (`0 16 * * 1-5`) solo sabe de días de la semana. Los **festivos
colombianos** se excluyen en código con la variable `FESTIVOS`. Si esa lista está
vacía, un festivo se trataría como día hábil y se generaría el fichero.

## Pruebas
```bash
uv run --extra dev pytest -q
```
