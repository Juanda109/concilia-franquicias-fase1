# co_pqrs_back_doble_cobro

Servicio backend del camino **duplicidad en el cobro / doble cobro**. Resuelve
las decisiones de negocio del flujo: días hábiles de conciliación, vigencia de
la fecha reportada y detección de cobros duplicados.

El árbol conversacional vive en el agente
(`co_pqrs_back_agent/src/domain/workflow/doble_cobro/doble_cobro.yml`); aquí no
hay textos de cara al cliente.

Especificación completa del flujo, reglas y contrato:
[`docs/ESPECIFICACION_FLUJO.md`](docs/ESPECIFICACION_FLUJO.md).

## Puerto

`8006` (agent=8000, maintenance=8001, error_handler=8002, data=8003, trx=8004,
aso_simulator=8050, **doble_cobro=8006**).

## Levantar en local

Necesita el simulador ASO en `:8050` para responder con datos.

```bash
uv sync
cp .env.example .env
uv run uvicorn --app-dir src infrastructure.entrypoint.fastapi_app:app --reload --host 127.0.0.1 --port 8006
```

O todo el stack de una vez desde la raíz del repo:

```bash
uv run python scripts/run_local.py
```

## Endpoints

| Método | Ruta | Para qué |
|---|---|---|
| `GET` | `/health` | Estado del servicio |
| `GET` | `/v0/doble-cobro/productos-activos` | Productos del cliente, filtrables por familia |
| `POST` | `/v0/doble-cobro/validar-vigencia` | Días hábiles + plazo de 6 meses + franquicia |
| `POST` | `/v0/doble-cobro/grupos-duplicados` | Grupos de cobros duplicados del día |

Documentación interactiva en `http://127.0.0.1:8006/docs`.

### Ejemplo

```bash
curl -s "http://127.0.0.1:8006/v0/doble-cobro/productos-activos?customer_id=13083558&family=SAVING"
```

```bash
curl -s -X POST http://127.0.0.1:8006/v0/doble-cobro/grupos-duplicados \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"13083558","transaction_date":"20/08/2026","amount":145000,"account_id":"00130766000200022384"}'
```

## Estructura

```
src/domain/doble_cobro/
    business_days.py      Festivos colombianos y conteo de dias habiles
    duplicate_finder.py   Agrupacion de cobros duplicados
    models.py             Contratos de entrada/salida
src/application/doble_cobro/
    movements.py          /cards/v2/operations -> movimiento normalizado
    analysis_service.py   Orquestacion de las cuatro decisiones del flujo
src/infrastructure/persistence/
    doble_cobro_aso_client.py  Cliente ASO (financial-overview + operations)
```

El servicio es **sin estado**: resuelve reglas y no persiste nada.

## Dónde se guardan los casos

En **OpenSearch**, no aquí. El agente escribe la ficha en el índice durable
`trx-no-reconocida-cases` con `tipo_de_notificacion: "doble_cobro"` y el id
`doble_cobro_<client_id>`, con la misma estructura que transacción no reconocida
para que el CronJob de exportación a Tantia lea ambos flujos.

Detalles en [`docs/ESPECIFICACION_FLUJO.md`](docs/ESPECIFICACION_FLUJO.md).

## Tests

```bash
uv run pytest -q
```

## Seguridad

Servicio interno sin autenticación (igual que los demás `co_pqrs_back_*`
internos). Deuda técnica a resolver si algún día se expone fuera de la malla
interna.
