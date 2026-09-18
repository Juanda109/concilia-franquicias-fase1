# co_pqrs_back_load_ada_data

Modulo batch en Python para cargar datos ADA en PostgreSQL desde parquet particionado.

## Alcance

Procesa la carpeta del dia anterior (formato AAAAMMDD):

- pqrs_ada_data_AAAAMMDD -> carga completa en tabla ada_info_detail

La ejecucion es de una sola corrida por invocacion.

## Flujo de proceso

1. Carga configuracion desde variables de entorno y archivo .env.
2. Construye la carpeta esperada del dia anterior.
3. Si la carpeta no existe, registra warning y termina sin error.
4. Busca todas las partes parquet dentro de la carpeta (incluyendo subdirectorios).
5. Ejecuta TRUNCATE TABLE ... RESTART IDENTITY sobre ada_info_detail.
6. Carga todas las partes con COPY FROM STDIN por lotes (streaming) para evitar alto uso de memoria.
7. Registra resultados por parte y resumen final del job.

## Variables de entorno

### Requeridas

- DB_HOST
- DB_NAME
- DB_USER
- DB_PASS

### Opcionales

- DB_PORT (default: 5432)
- RUTA_PROCESO (default: /mnt/ada_data)
- ADA_FOLDER_PREFIX (default: pqrs_ada_data_)
- TARGET_TABLE (default: ada_info_detail)
- PARQUET_BATCH_SIZE (default: 50000)
- CSV_DELIMITER (default: ,)
- CSV_QUOTE_CHAR (default: ")
- CSV_ESCAPE_CHAR (default: ")
- COPY_NULL_TOKEN (default: __CO_PQRS_NULL__)

Notas:

- El job asume que las columnas del parquet coinciden en nombre y tipo con la tabla destino.
- Si hay varias partes parquet, se cargan todas en la misma tabla.
- Si existe mismatch de schema entre partes, el job falla y hace rollback.

## Ejecucion local

1. Configurar variables en un archivo .env.
2. Instalar dependencias:

```bash
pip install -r requirements.txt
```

3. Ejecutar:

```bash
python main.py
```

## Ejecucion con contenedor

Ruta de red requerida para montar como entrada de datos:

- \\82.250.88.90\tx\RECEPCION_HOST\XC\STG\automatizacion_pqrs

Build:

```bash
docker build -t co-pqrs-back-load-ada-data .
```

Run:

```bash
docker run --rm \
	--env-file .env \
	-v //82.250.88.90/tx/RECEPCION_HOST/XC/STG/automatizacion_pqrs:/mnt/ada_data:ro \
	co-pqrs-back-load-ada-data
```

## Comportamiento operativo

- No expone API HTTP.
- Si no existe la carpeta esperada del dia anterior, termina con warning sin error.
- Usa una sola transaccion para truncar y cargar todas las partes parquet.
- Si una parte falla durante carga, se realiza rollback completo.
