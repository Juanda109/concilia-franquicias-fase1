# OpenSearch Conversation Maintenance

Servicio en Python para:

- revisar conversaciones `Active` y cerrarlas cuando llevan 5 minutos o mas sin interaccion,
- exportar conversaciones `Closed` junto con sus mensajes,
- guardar un JSON particionado por fecha en `conversations/id/YYYY/MM/DD/id_timestamp.json`,
- marcar o eliminar las conversaciones exportadas segun configuracion,
- exponer un endpoint interno `POST /end/{conversation_id}` para historizar de inmediato cuando el back principal cierre una conversacion.

## Como funciona

El servicio ahora tiene dos formas de disparo que conviven sobre la misma logica:

1. `cron`: hace el barrido periodico, igual que antes.
2. `api`: recibe `POST /end/{conversation_id}` y procesa solo esa conversacion.

En ambos casos se usa el mismo flujo interno y un claim en OpenSearch para evitar duplicados entre procesos concurrentes.

### Flujo de exportacion

1. Busca o recibe una conversacion cerrada.
2. Intenta tomar un claim escribiendo `LOCKED_AT_FIELD` y `LOCKED_BY_FIELD`.
3. Si otra ejecucion ya la tomo y el lock sigue vigente, la salta.
4. Calcula una ruta deterministica para el JSON y la persiste en el documento.
5. Trae los mensajes desde el indice configurado.
6. Genera el JSON con la conversacion completa y los mensajes.
7. Lo guarda bajo `OUTPUT_DIR`.
8. Segun configuracion:
9. marca la conversacion con `EXPORTED_AT_FIELD` y `EXPORTED_PATH_FIELD`, o
10. elimina la conversacion de OpenSearch.
11. Si corresponde, elimina tambien los mensajes exportados.

### Flujo cron

El flujo del job por cron es este:

1. Busca conversaciones `Closed` que aun no tengan la marca de exportacion.
2. Para cada una intenta tomar el claim antes de exportar.
3. Si logra el claim, la historiza con la misma logica descrita arriba.
6. Luego revisa las conversaciones `Active`.
7. Si la ultima interaccion fue hace menos de 5 minutos, no hace nada.
8. Si fue hace 5 minutos o mas, cambia el estado a `Closed`.

Ese orden hace que una conversacion que acaba de pasar de `Active` a `Closed` se exporte en la siguiente ejecucion, tal como pediste.

## Archivo `.env`

El proyecto ahora usa un archivo `.env` real.

- `main.py` carga `.env` automaticamente.
- el contenedor tambien lo carga si el archivo existe dentro de `/app`.
- en Docker, lo mas seguro es pasar ese archivo con `--env-file .env` en tiempo de ejecucion.
- el codigo acepta `CONVERSATIONS_INDEX` y `MESSAGES_INDEX` por compatibilidad, pero ahora prioriza `OPENSEARCH_CONVERSATIONS_INDEX` y `OPENSEARCH_MESSAGES_INDEX`.

## Creacion de indices en OpenSearch

Si vas a levantar el flujo de mantenimiento desde cero, estos `curl` crean los indices base usados por la configuracion actual del `.env`.

Nota:
si OpenSearch corre dentro de otro host o desde contenedor no expone `localhost`, cambia la URL por la direccion real del cluster, por ejemplo `https://host.containers.internal:9200`.

Indice de conversaciones (`conversations-reference`):

```bash
curl -k -u admin:admin \
  -H "Content-Type: application/json" \
  -X PUT "https://localhost:9200/conversations-reference" \
  -d '{
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 1
    },
    "mappings": {
      "dynamic": true,
      "properties": {
        "id": { "type": "keyword" },
        "status": { "type": "keyword" },
        "last_msg_date": { "type": "date" },
        "last_interaction_at": { "type": "date" },
        "updated_at": { "type": "date" },
        "last_message_at": { "type": "date" },
        "closed_at": { "type": "date" },
        "maintenance_exported_at": { "type": "date" },
        "maintenance_export_path": { "type": "keyword" },
        "maintenance_locked_at": { "type": "date" },
        "maintenance_locked_by": { "type": "keyword" }
      }
    }
  }'
```

Indice de mensajes (`conversations-messages`):

```bash
curl -k -u admin:admin \
  -H "Content-Type: application/json" \
  -X PUT "https://localhost:9200/conversations-messages" \
  -d '{
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 1
    },
    "mappings": {
      "dynamic": true,
      "properties": {
        "conversation_id": { "type": "keyword" },
        "created_at": { "type": "date" },
        "timestamp": { "type": "date" },
        "sent_at": { "type": "date" }
      }
    }
  }'
```

Indice de control por cliente (`client-control-table`):

```bash
curl -k -u admin:admin \
  -H "Content-Type: application/json" \
  -X PUT "https://localhost:9200/client-control-table" \
  -d '{
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 1
    },
    "mappings": {
      "dynamic": "strict",
      "properties": {
        "client_id": { "type": "keyword" },
        "total_interactions": { "type": "long" },
        "workflows": { "type": "object", "enabled": true },
        "daily": { "type": "object", "enabled": true },
        "updated_at": { "type": "date" }
      }
    }
  }'
```

Si tu modelo real tiene mas campos, puedes mantener `dynamic: true` en los indices operativos y ampliar `properties` segun necesites.

## Variables de entorno

La configuracion se hace por variables de entorno para poder adaptar el script al mapping real de tu OpenSearch:

| Variable | Requerida | Default | Descripcion |
| --- | --- | --- | --- |
| `OPENSEARCH_HOSTS` | Si | - | Uno o varios hosts separados por coma. Ejemplo: `https://user:pass@host:9200` |
| `OPENSEARCH_USERNAME` | No | - | Usuario, si no viene embebido en el host |
| `OPENSEARCH_PASSWORD` | No | - | Password, si no viene embebido en el host |
| `OPENSEARCH_VERIFY_CERTS` | No | `true` | Verifica certificados SSL |
| `OPENSEARCH_TIMEOUT_SECONDS` | No | `30` | Timeout del cliente |
| `OPENSEARCH_CONVERSATIONS_INDEX` | No | `conversations` | Indice de conversaciones |
| `OPENSEARCH_MESSAGES_INDEX` | No | `messages` | Indice de mensajes |
| `OUTPUT_DIR` | No | `./output` | Carpeta raiz de exportacion |
| `BATCH_SIZE` | No | `250` | Tamano de lote para scroll |
| `SCROLL_KEEPALIVE` | No | `2m` | Tiempo de vida del scroll |
| `INACTIVE_MINUTES` | No | `5` | Minutos sin interaccion para cerrar |
| `DEFAULT_TIMEZONE` | No | `UTC` | Zona para timestamps sin timezone |
| `CONVERSATION_STATUS_FIELD` | No | `status` | Campo de estado en la conversacion |
| `ACTIVE_STATUS_VALUE` | No | `Active` | Valor del estado activo |
| `CLOSED_STATUS_VALUE` | No | `Closed` | Valor del estado cerrado |
| `CONVERSATION_ID_FIELD` | No | `_id` del documento | Campo de negocio de la conversacion; si no se define usa el `_id` |
| `MESSAGE_CONVERSATION_ID_FIELD` | No | `conversation_id` | Campo que relaciona mensaje con conversacion |
| `LAST_INTERACTION_FIELDS` | No | `last_msg_date,last_interaction_at,updated_at,last_message_at` | Campos candidatos para calcular inactividad |
| `MESSAGE_TIMESTAMP_FIELDS` | No | `created_at,timestamp,sent_at` | Campos candidatos para ordenar mensajes |
| `CLOSED_AT_FIELD` | No | `closed_at` | Campo donde se guarda la fecha de cierre |
| `EXPORTED_AT_FIELD` | No | `maintenance_exported_at` | Campo marca para no volver a exportar |
| `EXPORTED_PATH_FIELD` | No | `maintenance_export_path` | Campo con la ruta relativa del JSON generado |
| `LOCKED_AT_FIELD` | No | `maintenance_locked_at` | Campo con la fecha del claim en progreso |
| `LOCKED_BY_FIELD` | No | `maintenance_locked_by` | Campo con el identificador del proceso que tomo el claim |
| `LOCK_TIMEOUT_SECONDS` | No | `300` | Tiempo maximo en segundos que se considera vigente un claim |
| `ARCHIVE_LOOKUP_RETRIES` | No | `3` | Reintentos para el endpoint cuando aun no aparece la conversacion cerrada |
| `ARCHIVE_LOOKUP_RETRY_SECONDS` | No | `1` | Espera entre reintentos del endpoint |
| `MAINTENANCE_API_TOKEN` | No | - | Token opcional esperado en el header `X-Maintenance-Token` |
| `DELETE_EXPORTED_CONVERSATIONS` | No | `true` | Si esta en `true`, elimina la conversacion del indice despues de exportarla |
| `DELETE_EXPORTED_MESSAGES` | No | `true` | Si esta en `true`, elimina los mensajes asociados despues de exportarlos |

Nota importante:
si ejecutas esto dentro de `podman` o `docker`, no uses `localhost` en `OPENSEARCH_HOSTS` a menos que OpenSearch viva dentro del mismo contenedor. Si OpenSearch corre en tu maquina, usa `https://host.containers.internal:9200` o la IP/DNS real del cluster.

Con la configuracion actual del `.env`, las conversaciones `Closed` se exportan y luego se eliminan de OpenSearch junto con sus mensajes. Si quieres solo archivarlas sin borrarlas, cambia `DELETE_EXPORTED_CONVERSATIONS=false`.
Si antes corriste una version que solo marcaba `maintenance_exported_at`, el modo actual de borrado vuelve a tomar esas conversaciones `Closed` para exportarlas de nuevo si hace falta y eliminarlas.

## Estructura del JSON

Cada archivo queda con esta forma:

```json
{
  "metadata": {
    "conversation_id": "abc123",
    "conversation_document_id": "abc123",
    "message_count": 10,
    "closed_at": "2026-05-04T14:10:00+00:00",
    "exported_at": "2026-05-04T14:12:00+00:00",
    "export_relative_path": "conversations/abc123/2026/05/04/abc123_20260504T141000Z.json"
  },
  "conversation": {
    "_id": "abc123",
    "_index": "conversations",
    "_source": {}
  },
  "messages": [
    {
      "_id": "msg-1",
      "_index": "messages",
      "_source": {}
    }
  ]
}
```

## Ejecucion local

```powershell
uv sync
uv run python main.py
```

Modo API:

```powershell
uv sync
uv run python api.py
```

Endpoint interno:

```http
POST /end/{conversation_id}
X-Maintenance-Token: <token-opcional>
```

Respuestas esperadas:

- `200` con `status=archived` cuando historiza en esa llamada
- `200` con `status=already_exported` cuando ya existia una exportacion valida
- `202` con `status=already_processing` cuando otro proceso ya esta trabajando esa conversacion
- `404` si no la encontro despues de los reintentos configurados
- `409` si existe mas de una conversacion para el mismo identificador o si aun no esta cerrada

## Docker con cron o API

El repo incluye un `Dockerfile` y un `docker-entrypoint.sh`. El contenedor:

- crea el entorno con `uv`,
- arranca en modo `cron` o `api` segun `SERVICE_MODE`,
- en modo `cron` crea un job usando `CRON_SCHEDULE`,
- en modo `api` levanta `uvicorn` con `API_HOST` y `API_PORT` sobre `8001` por defecto,
- deja los logs visibles por stdout/stderr del contenedor.

Ejemplo:

```bash
docker build -t co-pqrs-back-maintenance .

docker run --rm \
  --env-file .env \
  -e SERVICE_MODE=api \
  -p 8001:8001 \
  -v "$(pwd)/output:/app/output" \
  co-pqrs-back-maintenance
```

## Podman Compose

Tambien puedes usar `podman-compose` con el archivo [compose.yaml](<C:/Users/O020172/Documents/proyectos/pqrs/code/agentepqr/co_pqrs_back_maintenance/compose.yaml:1>).

Construir:

```bash
podman-compose build
```

Levantar en segundo plano:

```bash
podman-compose up -d
```

Ese `compose.yaml` crea dos servicios usando la misma imagen:

- `conversation-maintenance-api`
- `conversation-maintenance-cron`

De esa forma el back principal puede hablar con la API interna mientras el cron queda como red de seguridad.
Si usas el `compose` de este repo, la API queda publicada en `http://localhost:8001`.

Ver logs:

```bash
podman-compose logs -f
```

Detener y remover:

```bash
podman-compose down
```

## Ajustes que seguramente vas a querer revisar

- `LAST_INTERACTION_FIELDS`: en tu caso debe priorizar `last_msg_date`, que es el campo usado para pasar de `Active` a `Closed`.
- `MESSAGE_CONVERSATION_ID_FIELD`: debe ser la llave real que une mensajes con conversaciones.
- `CONVERSATION_ID_FIELD`: si tu identificador de negocio no es el `_id` del documento.
- `DEFAULT_TIMEZONE`: si tus fechas llegan sin timezone y debes asumir, por ejemplo, `America/Bogota`.
- `LOCK_TIMEOUT_SECONDS`: debe ser mayor al peor tiempo esperado de historizacion para evitar reclamos prematuros.

## Volcado durable a MinIO (S3-compatible)

Cuando `MINIO_ENABLED=true`, el archivado escribe a MinIO en lugar del disco
efimero. MinIO habla el protocolo S3, por eso se usa el cliente boto3 `s3`
apuntando a `MINIO_ENDPOINT_URL` con path-style addressing. No hay AWS S3 real.

Se escriben tres clases de objeto en el bucket `MINIO_BUCKET`:

- `conversations/<id>/YYYY/MM/DD/<id>_<ts>.json` — JSON crudo (conversacion + mensajes).
- `summaries/dt=YYYY-MM-DD/<id>.json` — NDJSON aplanado, una linea por conversacion
  (user_id, workflow, final_step, satisfaction, message_count, total_tokens, total_duration_ms...).
- `control-table/dt=YYYY-MM-DD/control-table_<ts>.json` — NDJSON snapshot del indice
  `client-control-table` con 3 tipos de registro: `client`, `workflow_month`, `daily_sessions`.
  El blob `monthly.*.workflows.*.data` (back-data comercial / PII) se EXCLUYE siempre.

Las subidas son idempotentes (se verifica `head_object` antes de escribir el crudo
y los resumenes por conversacion).

### Variables de entorno MinIO

| Variable | Descripcion |
| --- | --- |
| `MINIO_ENABLED` | `true` para volcar a MinIO; `false` mantiene el disco. |
| `MINIO_ENDPOINT_URL` | Endpoint interno, ej. `http://minio.pqr-genai-dev.svc.cluster.local:9000`. |
| `MINIO_BUCKET` | Bucket destino, ej. `pqr-conversations-history`. |
| `MINIO_REGION` | Region (MinIO la ignora); por defecto `us-east-1`. |
| `MINIO_ACCESS_KEY` | Access key (se inyecta via secret `minio-creds`). |
| `MINIO_SECRET_KEY` | Secret key (se inyecta via secret `minio-creds`). |
| `MINIO_ADDRESSING_STYLE` | `path` (requerido por MinIO). |
| `OPENSEARCH_CONTROL_INDEX` | Indice de control por cliente, por defecto `client-control-table`. |

En OpenShift el barrido periodico lo ejecuta el CronJob
`co-pqrs-back-maintenance-sweep` (cada 5 min, `python main.py`), ademas de la API
`/end/{id}` bajo demanda.

### Pruebas

```bash
cd co_pqrs_back_maintenance
python3 -m pytest tests/ -q
```

### Smoke test en dev

1. Generar/cerrar una conversacion (o esperar al cierre por inactividad de 5 min).
2. Ejecutar el barrido (CronJob `co-pqrs-back-maintenance-sweep` o `python main.py`
   dentro del pod con el `.env` montado y `MINIO_ENABLED=true`).
3. Verificar los objetos en MinIO:

```bash
aws s3 ls s3://pqr-conversations-history/conversations/ --recursive \
  --endpoint-url http://minio.pqr-genai-dev.svc.cluster.local:9000

aws s3 ls s3://pqr-conversations-history/summaries/ --recursive \
  --endpoint-url http://minio.pqr-genai-dev.svc.cluster.local:9000

aws s3 ls s3://pqr-conversations-history/control-table/ --recursive \
  --endpoint-url http://minio.pqr-genai-dev.svc.cluster.local:9000
```

> Nota de seguridad: en dev se reutiliza la credencial root de `minio-creds`. Antes
> de QA/prod conviene crear un usuario MinIO con politica limitada al bucket y
> segregar credenciales (hoy la misma contrasena se reutiliza en OpenSearch/MinIO).
