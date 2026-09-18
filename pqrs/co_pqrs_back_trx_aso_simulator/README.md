# co_pqrs_back_trx_aso_simulator

Simulador de los ASOs usados por el flujo **Transacción No Reconocida** (TXNR).
**Solo para dev/E2E** (sin autenticación de red). Imita los endpoints del ASO real
(`https://dev-arqaso.work.co.nextgen.igrupobbva:8050`).

## Endpoints
- `POST /TechArchitecture/co/grantingTicket/V02` → 200 + header `tsec`.
- `GET  /salesforce-issue-tracker/v0/issues?targetUserId=01-<doc>`
- `GET  /financial-overview/v0/financial-overview?customer.id=<id>&contracts.productType=CARDS`
- `GET  /cards/v2/cards/{card_id}/transactions` (filtros: fromOperationDate, toOperationDate, operationAmount.fromAmount/toAmount, moneyFlow.id, operationAmount.id)
- `GET  /cards/v2/operations?operationDate=YYYYMMDD&cardId=<pan>`
- `PATCH /cards/v1/cards/{card_id}/activations` (200; 502 si card en data/block_failures.json)
- `POST /cards/v2/operations` (201; 502 si card en data/block_failures.json)

## Data
`data/salesforce/{doc}.json`, `data/financial_overview/{customer_id}.json`,
`data/transactions/{card_id}.json`, `data/operations/{card_id}.json`,
`data/block_failures.json`. Cada request lee del disco (sin estado mutable →
seguro multiusuario). Ver `docs/trx no reconocida/CLIENTES_SIMULADOR.md`.

## Correr local
```bash
uv run uvicorn infrastructure.entrypoint.fastapi_app:app --app-dir src --port 8050
# tests
uv run --extra dev pytest -q
```
