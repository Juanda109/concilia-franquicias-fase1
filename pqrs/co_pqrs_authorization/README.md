# co_pqrs_authorization

Ciclo de vida de las autorizaciones OOB (push + estado + timeout + resultado),
extraido del flujo de negocio como capacidad transversal (pliego de Luis, 03/09).

- **No dispara el push**: recibe el `challenge` ya creado por el flujo que inicio
  la ceremonia (TXNR hoy; Doble Cobro manana) y desde ahi es dueno del ciclo.
- **Worker durable**: jobs persistidos en OpenSearch (`authorizations`), claim
  con concurrencia optimista (`if_seq_no`), deadline de 180 s cumplido por el
  backend aunque el usuario no vuelva. Sobrevive reinicios y multiples replicas.
- **Estados**: negocio (`PENDING/ACCEPTED/REJECTED/EXPIRED`) separado del
  tecnico (`SUCCESS/BUSINESS_RESULT/TECHNICAL_ERROR`). Un fallo del ASO jamas
  se convierte en rechazo.
- **Cero negocio de workflows**: `workflow`/`step`/`metadata` son opacos.

## Correr en local

    uv sync
    uv run uvicorn --app-dir src infrastructure.entrypoint.fastapi_app:app --port 8005

Con el simulador ASO en :8050 y OpenSearch local. `ASO_SOURCE=simulator|real`
por entorno (ver `.env.example`); nada hardcodeado.

## Contrato

    POST /v1/authorizations   {conversation_id, workflow, step, challenge, idempotency_key?, metadata?}
    GET  /v1/authorizations/{authorization_id}
    GET  /v1/authorizations?conversation_id=...

La creacion es idempotente: el id deriva de la idempotency_key
(por defecto `conversation:step:challenge`) con create-if-absent.
