# co_pqrs_back_data

API para consultar informacion de clientes usando PostgreSQL o un CSV mock
como fuente, y un JSON local como respuesta mock de una API externa.

## Ejecutar localmente

```bash
uv sync
uv run uvicorn --app-dir src infrastructure.entrypoint.fastapi_app:app --reload
```

## Fuente de datos

Para consultar PostgreSQL:

```env
CUSTOMER_IDENTITY_SOURCE=postgres
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DATABASE=pqr_db
POSTGRES_USER=pqr_user
POSTGRES_PASSWORD=pqr_password
POSTGRES_CUSTOMER_IDENTITY_TABLE=ada_info_detail
POSTGRES_TABLE_EMB=BGDTEMB
POSTGRES_TABLE_DEM=BGDTDEM
POSTGRES_TABLE_JOIN=BGDT_SALIDA_JOIN
```

Para volver al CSV mock:

```env
CUSTOMER_IDENTITY_SOURCE=mock
DATA_CSV=unifi
```

## Endpoints

- `GET /health`
- `GET /consultar?customer_id=56780000`
