# co_pqrs_back_error_handler

API basada en la estructura de `co_pqrs_back_agent` para capturar fallos del agente, consultar la conversacion en OpenSearch por `conversation_id` y exportar un JSON local con la conversacion, el error exacto y metrica util para analitica.

## Objetivo

- Recibir un incidente tecnico del agente con el `conversation_id`.
- Consultar OpenSearch usando los indices de conversaciones y mensajes ya existentes.
- Volcar un reporte JSON local con el error exacto, la conversacion recuperada y el contexto recibido.
- Agregar analitica util para agrupar y priorizar fallos.

## Estructura

```text
co_pqrs_back_error_handler/
|-- .env.example
|-- README.md
|-- pyproject.toml
|-- src/
|   |-- application/
|   |   `-- error_report/
|   |       `-- error_report_service.py
|   |-- domain/
|   |   |-- conversation/
|   |   |   `-- models.py
|   |   `-- error_report/
|   |       `-- models.py
|   `-- infrastructure/
|       |-- core/
|       |   |-- config.py
|       |   `-- logger.py
|       |-- entrypoint/
|       |   |-- fastapi_app.py
|       |   `-- api/
|       |       |-- dependencies.py
|       |       |-- errors/
|       |       `-- router/
|       |           |-- healthcheck/
|       |           `-- v0/
|       |               `-- error_report_router.py
|       |-- filesystem/
|       |   `-- error_report_writer.py
|       `-- persistence/
|           |-- conversation_store.py
|           `-- opensearch_client.py
`-- tests/
    `-- test_application/
        `-- test_error_report/
            `-- test_error_report_service.py
```

## Endpoint principal

- `POST /v0/error-reports`
- `GET /health`

Ejemplo de request:

```json
{
  "conversation_id": "03966512_20260421",
  "error_message": "TimeoutError: model response exceeded 30 seconds",
  "error_type": "TimeoutError",
  "error_source": "co_pqrs_back_agent",
  "trace_id": "pqr-err-20260422-0001",
  "tags": ["llm", "timeout", "production"],
  "agent_context": {
    "step": "2.1",
    "agent_name": "workflow-agent"
  },
  "extra_context": {
    "channel": "webchat",
    "customer_segment": "retail"
  }
}
```

Respuesta esperada:

```json
{
  "report_id": "03966512_20260421_20260422T143100123456Z",
  "conversation_id": "03966512_20260421",
  "conversation_found": true,
  "exported_file_path": "C:\\path\\to\\data\\error_reports\\2026\\04\\22\\error_report_03966512_20260421_20260422T143100Z.json",
  "generated_at": "2026-04-22T14:31:00.123456Z",
  "analytics": {
    "conversation_found": true,
    "conversation_reference_found": true,
    "message_documents_found": true,
    "message_document_count": 8,
    "parsed_message_count": 8,
    "invalid_message_count": 0,
    "conversation_status": "Active",
    "general_workflow": "Hazlo tu mismo",
    "workflow": "Solicitud",
    "current_step": "2.1",
    "message_count_by_role": {
      "user": 4,
      "assistant": 4
    },
    "total_input_tokens": 321,
    "total_output_tokens": 287,
    "total_tokens": 608,
    "failure_stage": "assistant_response"
  }
}
```

## Contenido del JSON exportado

Cada archivo exportado incluye:

- `metadata`: `report_id`, fecha de generacion, version de esquema y nombre del servicio.
- `failure`: `conversation_id`, mensaje de error exacto, tipo de error, `trace_id`, tags y contexto opcional del agente.
- `conversation_snapshot`: referencia de conversacion, mensajes recuperados y advertencias de parseo si OpenSearch devuelve datos incompletos.
- `analytics`: workflow, paso actual, cantidad de mensajes por rol, tokens, tiempos, huella normalizada del error y retardo entre ultimo mensaje y reporte del fallo.

## Variables de entorno

- `OPENSEARCH_ENDPOINT`
- `OPENSEARCH_USER`
- `OPENSEARCH_PASSWORD`
- `OPENSEARCH_VERIFY_SSL`
- `OPENSEARCH_CONVERSATIONS_INDEX`
- `OPENSEARCH_MESSAGES_INDEX`
- `OPENSEARCH_TIMEOUT`
- `ERROR_REPORT_OUTPUT_DIR`
- `ERROR_REPORT_FILE_PREFIX`
- `ERROR_HANDLER_LOG_LEVEL`

Puedes usar `.env.example` como base.

## Ejecucion local

Instalar dependencias:

```powershell
uv sync
```

Levantar la API:

```powershell
uv run uvicorn --app-dir src infrastructure.entrypoint.fastapi_app:app --reload --host 127.0.0.1 --port 8002
```

## Salida local

Por defecto los archivos se escriben en:

```text
data/error_reports/<yyyy>/<mm>/<dd>/
```

Esto facilita particionar la evidencia y luego procesarla para analitica o carga batch.
