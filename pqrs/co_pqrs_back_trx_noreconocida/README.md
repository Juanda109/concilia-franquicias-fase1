# co_pqrs_back_trx_noreconocida

Servicio backend del camino **transacción no reconocida**. Su rol final será orquestar
las herramientas y fuentes de datos del proceso (ASOS, "jalar datos" del cliente/movimientos,
análisis del posible origen del evento: cambiazo, hurto/pérdida, ingeniería social, compra
presencial/internet).

Estado actual:

- `POST /v0/productos_activos` consulta productos activos del cliente en Postgres (`ada_info_detail`).
- `POST /v0/consultar_trx` devuelve el producto seleccionado y un estado explícito de la fuente de transacciones.
- `POST /v0/aso` y `POST /v0/analisis` siguen como placeholders.

## Puerto

`8004` (agent=8000, maintenance=8001, error_handler=8002, data=8003, **trx=8004**).

## Levantar en local

```bash
uv run uvicorn --app-dir src infrastructure.entrypoint.fastapi_app:app --reload --host 127.0.0.1 --port 8004
```

## Endpoints

- `GET  /health` → `{"status": "ok"}`
- `POST /v0/productos_activos` → consultar productos activos del cliente en Postgres
- `POST /v0/consultar_trx` → validar el producto seleccionado y devolver el sobre de transacciones
- `POST /v0/aso` → placeholder de ASOS (mock; definir cuáles)
- `POST /v0/analisis` → análisis del caso (mock)

## Variables de entorno para Postgres

- `DB_HOST`
- `DB_PORT` (default `5432`)
- `DB_NAME`
- `DB_USER`
- `DB_PASS`
- `TRX_POSTGRES_TABLE` (default `ada_info_detail`)
- `POSTGRES_CONNECT_TIMEOUT` (default `5`)

## Seguridad

Servicio interno sin autenticación (igual que los demás `co_pqrs_back_*` internos). Deuda técnica
a resolver si algún día se expone fuera de la malla interna.
