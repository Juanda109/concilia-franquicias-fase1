# co_pqrs_back_load_seizures_data

Modulo batch en Python para cargar archivos diarios de embargos en PostgreSQL.

## Alcance

Procesa los siguientes archivos del dia anterior (formato AAMMDD):

- DESCARGA_EMB.FAAMMDD.TXT -> bgdtemb
- DESCARGA_DEM.FAAMMDD.TXT -> bgdtdem

La ejecucion es de una sola corrida por invocacion.

## Flujo de proceso

1. Carga configuracion desde variables de entorno y archivo .env.
2. Construye los nombres esperados para el dia anterior.
3. Verifica disponibilidad de archivos en RUTA_PROCESO.
4. Por cada archivo:
   - Ejecuta TRUNCATE TABLE ... RESTART IDENTITY en la tabla destino.
   - Carga datos con COPY FROM STDIN (CSV, HEADER true).
   - Si hay error de codificacion, reintenta con codificaciones fallback.
   - Elimina bytes nulos (\x00) antes del COPY.
5. Registra resultado por archivo y resumen final del job.

## Variables de entorno

### Requeridas

- DB_HOST
- DB_NAME
- DB_USER
- DB_PASS

### Opcionales

- DB_PORT (default: 5432)
- RUTA_PROCESO (default: /mnt/embargos)
- CSV_DELIMITER (default: ;)
- CSV_QUOTE_CHAR (default: \x01)
- CSV_ESCAPE_CHAR (default: \x01)
- FILE_ENCODING (default: cp1252)
- FILE_ENCODING_FALLBACKS (default: latin-1,utf-8)

Notas:

- Si faltan variables requeridas, la ejecucion falla al iniciar.
- Si DB_PORT no es numerico, la ejecucion falla al cargar configuracion.

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

Build:

```bash
docker build -t co-pqrs-back-load-seizures-data .
```

Run:

```bash
docker run --rm \
  --env-file .env \
  -v /ruta/real/embargos:/mnt/embargos:ro \
  co-pqrs-back-load-seizures-data
```

## Comportamiento operativo

- No expone API HTTP.
- Si un archivo no existe, se marca como omitido y el proceso continua.
- Si un archivo falla al cargar, se realiza rollback de ese archivo.
- Se usa SQL parametrizado para nombres de tabla mediante psycopg2.sql.Identifier.
