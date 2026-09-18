# Excel / RPA (Tantia) — OBSOLETO

> **Este documento quedó obsoleto el 2026-08-21.**
>
> El Excel de 21 columnas con una fila por caso **fue reemplazado** por un CSV de
> 20 columnas con una fila por transacción. El módulo ya no genera ficheros
> `.xlsx` y la dependencia `openpyxl` se eliminó.
>
> **Ver: [`CSV_TANTIA.md`](./CSV_TANTIA.md)**

## Por qué se dejó esta nota en vez de borrar el fichero
El nombre `EXCEL_TANTIA.md` aparece referenciado en documentos y conversaciones
previas. Dejar la redirección evita que alguien lo busque, no lo encuentre y
asuma que la especificación se perdió.

## Resumen del cambio
| | Antes (Excel) | Ahora (CSV) |
|---|---|---|
| Formato | `.xlsx`, hoja `tantia` | CSV separado por `;` |
| Nombre | `tantia_trx_no_reconocida_AAAAMMDD.xlsx` | `DDMMAAAATxrNoReconocida.csv` |
| Columnas | 21 (layout AS400, con erratas del original) | 20 |
| Granularidad | una fila por **caso** | una fila por **transacción** |
| Carpeta | `trx_no_reconocida_pqrs` | `ficheros_rpa` |
| Horario | 23:45 todos los días | 16:00 solo días hábiles |
| Fichero vacío | no se generaba | **sí**, con solo encabezado |
