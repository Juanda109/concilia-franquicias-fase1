"""Simulador de ASOs para TXNR (solo dev/E2E). Sin autenticación de red.

Endpoints que imitan al ASO real (base `https://dev-arqaso...:8050`):
- POST /TechArchitecture/co/grantingTicket/V02  -> TSEC en header `tsec`
- GET  /salesforce-issue-tracker/v0/issues
- GET  /financial-overview/v0/financial-overview
- GET  /cards/v2/cards/{card_id}/transactions
- GET  /cards/v2/operations
- PATCH /cards/v1/cards/{card_id}/activations
- GET  /security/v0/user-status            (subida de nivel: dispositivo)
- GET  /security/v0/order-chanel/{id}      (subida de nivel: estado del push)
- POST /cards/v2/operations
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import os

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse

from application.scenarios.resolver import TrxAsoResolver


def _contract_amount(item: dict[str, Any]) -> float | None:
    for amt in item.get("operationAmounts", []) or []:
        if amt.get("id") == "CONTRACT_AMOUNT":
            try:
                return float(amt.get("amount"))
            except (TypeError, ValueError):
                return None
    return None


def _date_part(value: str) -> str:
    return (value or "")[:10]


def build_app() -> FastAPI:
    app = FastAPI(
        title="trx ASO simulator",
        version="0.1.0",
        description="Simulador de ASOs para Transacción No Reconocida (solo dev).",
    )
    resolver = TrxAsoResolver(data_dir=Path(__file__).resolve().parents[3] / "data")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/TechArchitecture/co/grantingTicket/V02")
    async def granting_ticket(request: Request) -> Response:
        # El TSEC real llega en el header `tsec`. Devolvemos uno ficticio.
        return JSONResponse(
            content={"status": "ok"},
            headers={"tsec": "SIMULATED-TSEC-TOKEN"},
        )

    @app.get("/salesforce-issue-tracker/v0/issues")
    async def salesforce_issues(
        target_user_id: str = Query("", alias="targetUserId"),
    ) -> dict[str, Any]:
        return resolver.salesforce_issues(target_user_id)

    @app.get("/financial-overview/v0/financial-overview")
    async def financial_overview(
        customer_id: str = Query("", alias="customer.id"),
        contract_id: str = Query("", alias="contracts.id"),
        product_type: str = Query("CARDS", alias="contracts.productType"),
    ) -> dict[str, Any]:
        # El servicio manda ahora los tres filtros: customer.id,
        # contracts.productType y contracts.id (peticion de Fabian 20/08).
        #
        # Si el contrato pedido esta en el payload del cliente, se devuelve ese
        # payload (acotado en origen, que es lo que se busca). Si NO esta, se
        # devuelve el del cliente igualmente en vez de una lista vacia: el
        # contract_id que entrega ADA es un LIC y el JSON de financial-overview
        # trae el PAN, asi que hoy NUNCA casan y filtrar en serio dejaria el
        # flujo sin card_id -- que es exactamente lo que rompio tras el merge.
        #
        # PENDIENTE de confirmar con Nicolas: si el ASO real SI acepta el
        # contract_id de Postgres como filtro, este respaldo sobra y el
        # simulador deberia devolver vacio cuando no casa.
        pedido = str(contract_id or "").strip()
        import os
        if pedido and os.getenv("SIM_FO_ESTRICTO", "").lower() in {"1","true"}:
            # MODO ESTRICTO (reproduccion del incidente de PRD 24/08): el ASO
            # real no conoce el contract_id de ADA (LIC) y rechaza el filtro.
            payload = resolver.financial_overview_by_contract(
                contract_id=pedido, customer_id=customer_id)
            if not (payload.get("data") or {}).get("contracts"):
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="invalid contracts.id")
            return payload
        if pedido:
            payload = resolver.financial_overview_by_contract(
                contract_id=pedido,
                customer_id=customer_id,
            )
            if (payload.get("data") or {}).get("contracts"):
                return payload
        return resolver.financial_overview(customer_id)

    @app.get("/cards/v2/cards/{card_id}/transactions")
    async def transactions(
        card_id: str,
        from_operation_date: str = Query("", alias="fromOperationDate"),
        to_operation_date: str = Query("", alias="toOperationDate"),
        from_amount: float | None = Query(None, alias="operationAmount.fromAmount"),
        to_amount: float | None = Query(None, alias="operationAmount.toAmount"),
        money_flow: str = Query("", alias="moneyFlow.id"),
        amount_id: str = Query("", alias="operationAmount.id"),
    ) -> dict[str, Any]:
        payload = resolver.transactions(card_id)
        items = list(payload.get("data", []) or [])

        def keep(item: dict[str, Any]) -> bool:
            if money_flow and (item.get("moneyFlow", {}) or {}).get("id") != money_flow:
                return False
            if from_operation_date or to_operation_date:
                d = _date_part(item.get("operationDate", ""))
                if from_operation_date and d < _date_part(from_operation_date):
                    return False
                if to_operation_date and d > _date_part(to_operation_date):
                    return False
            amt = _contract_amount(item)
            if amt is not None:
                abs_amt = abs(amt)
                if from_amount is not None and abs_amt < float(from_amount):
                    return False
                if to_amount is not None and abs_amt > float(to_amount):
                    return False
            return True

        filtered = [it for it in items if keep(it)]
        result = dict(payload)
        result["data"] = filtered
        return result

    @app.get("/cards/v2/operations")
    async def operations(
        operation_date: str = Query("", alias="operationDate"),
        card_id: str = Query("", alias="cardId"),
        account_id: str = Query("", alias="accountId"),
        page_size: int = Query(100, alias="pageSize"),
        pagination_key: int = Query(1, alias="paginationKey"),
    ) -> dict[str, Any]:
        key = card_id or account_id
        payload = resolver.operations(key)
        # Fidelidad con el ASO real (27/08): operations filtra por operationDate
        # (yyyymmdd) en ORIGEN. Sin este filtro, una fecha sin compras devolvia
        # el fichero entero y el camino "no encontramos compras registradas"
        # era inalcanzable en local.
        fecha = str(operation_date or "").strip().replace("-", "")
        if fecha and len(fecha) == 8 and isinstance(payload, dict):
            iso = f"{fecha[:4]}-{fecha[4:6]}-{fecha[6:]}"
            for bloque in payload.get("data") or []:
                if isinstance(bloque, dict):
                    bloque["operations"] = [
                        op for op in (bloque.get("operations") or [])
                        if str(op.get("dateOper") or op.get("operationDate") or "")[:10] == iso
                    ]
        return payload

    @app.patch("/cards/v1/cards/{card_id}/activations")
    async def activations(card_id: str, request: Request) -> Response:
        if resolver.block_should_fail(card_id):
            return JSONResponse(status_code=502, content={"error": "activation failed"})
        return JSONResponse(status_code=200, content={"status": "ok", "cardId": card_id})

    # ---- SUBIDA DE NIVEL: notificacion push previa al bloqueo ------------
    #
    # Se modela la ceremonia real del ASO:
    #   POST /cards/v2/operations sin authenticationdata  -> 403 + authenticationtype
    #   POST /cards/v2/operations con authenticationdata   -> 401 + challenge/state
    #   POST /cards/v2/operations con authenticationstate  -> 201 (ejecuta)
    #   GET  /security/v0/order-chanel/{challenge}         -> pending -> accepted/rejected
    #
    # El estado vive en memoria del proceso: es un simulador, no una fuente de
    # verdad. `_RETOS` guarda el estado explícito (pending/accepted/rejected) de cada
    # challenge para permitir simular tanto aprobación como rechazo del cliente.
    #
    # Estructura: {"sim-9784-challenge": {"status": "pending", "sondeos": 0}}
    _RETOS: dict[str, dict[str, Any]] = {}

    @app.get("/security/v0/user-status")
    async def user_status(profileId: str = "") -> Response:
        """Dispositivos del cliente. Sin profileId -> sin dispositivos."""

        if not profileId:
            return JSONResponse(status_code=200, content={"data": []})
        # Un cliente marcado como sin dispositivo permite probar ese camino.
        if profileId.endswith("0000"):
            return JSONResponse(
                status_code=200,
                content={"data": [{
                    "device": {"id": "BB-04-INACTIVO", "name": "SOFTWARE_AMAZON",
                               "softToken": {"id": "BB-04-INACTIVO",
                                             "status": {"id": "BLOCKED"}}},
                    "channel": {"id": "ACTIVE", "status": {"id": "ACTIVE"}}}]},
            )
        return JSONResponse(
            status_code=200,
            content={"data": [{
                "device": {"id": "BB-04-CG0400002F3D", "name": "SOFTWARE_AMAZON",
                           "softToken": {"id": "BB-04-CG0400002F3D",
                                         "status": {"id": "ACTIVE"}}},
                "channel": {"id": "ACTIVE", "status": {"id": "ACTIVE"}}}]},
        )

    @app.get("/security/v0/order-chanel/{challenge}")
    async def order_channel(challenge: str) -> Response:
        """Estado de la notificacion: pending hasta que se apruebe explicitamente.
        
        Para simular que el cliente aprobó, ejecutar:
          POST /security/v0/order-chanel/{challenge}/approve
        
        Para simular que el cliente rechazó, ejecutar:
          POST /security/v0/order-chanel/{challenge}/reject
        """

        reto = _RETOS.get(challenge)
        if not reto:
            # Challenge no existe (nunca se inició)
            return JSONResponse(
                status_code=404,
                content={"error": "challenge not found"}
            )
        
        # Incrementar contador de sondeos para debugging
        reto["sondeos"] = reto.get("sondeos", 0) + 1
        status = reto.get("status", "pending")
        
        return JSONResponse(
            status_code=200,
            content={
                "data": {
                    "status": {"id": status},
                    "_debug": {"sondeos": reto["sondeos"]}  # Solo para debugging
                }
            }
        )

    @app.post("/security/v0/order-chanel/{challenge}/approve")
    async def approve_challenge(challenge: str) -> Response:
        """[TEST ONLY] Simular que el cliente aprobó la notificación push.
        
        Cambia el estado del challenge de 'pending' a 'accepted'.
        
        Después de ejecutar este endpoint, los siguientes GETs a
        /security/v0/order-chanel/{challenge} devolverán status='accepted'.
        
        Uso:
          1. Iniciar flujo de bloqueo (genera challenge)
          2. Consultar GET /security/v0/order-chanel/{challenge} → pending
          3. Ejecutar POST /security/v0/order-chanel/{challenge}/approve
          4. Consultar GET /security/v0/order-chanel/{challenge} → accepted
          5. Continuar con confirmación (POST /cards/v2/operations con authenticationstate)
        """

        reto = _RETOS.get(challenge)
        if not reto:
            return JSONResponse(
                status_code=404,
                content={"error": f"challenge '{challenge}' not found"}
            )
        
        if reto.get("status") == "accepted":
            return JSONResponse(
                status_code=200,
                content={"status": "ok", "message": "challenge already accepted"}
            )
        
        if reto.get("status") == "rejected":
            return JSONResponse(
                status_code=409,
                content={"error": "challenge was rejected, cannot approve"}
            )
        
        # Cambiar estado de pending → accepted
        reto["status"] = "accepted"
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "message": f"challenge '{challenge}' approved",
                "data": {
                    "challenge": challenge,
                    "status": "accepted",
                    "sondeos": reto.get("sondeos", 0)
                }
            }
        )

    @app.post("/security/v0/order-chanel/{challenge}/reject")
    async def reject_challenge(challenge: str, request: Request) -> Response:
        """[TEST ONLY] Simular que el cliente rechazó la notificación push.
        
        Cambia el estado del challenge de 'pending' a 'rejected'.
        
        Después de ejecutar este endpoint, los siguientes GETs a
        /security/v0/order-chanel/{challenge} devolverán status='rejected'.
        
        Esto hace que el flujo de bloqueo no continúe (el cliente rechazó).
        
        Uso:
          1. Iniciar flujo de bloqueo (genera challenge)
          2. Consultar GET /security/v0/order-chanel/{challenge} → pending
          3. Ejecutar POST /security/v0/order-chanel/{challenge}/reject
          4. Consultar GET /security/v0/order-chanel/{challenge} → rejected
          5. El flujo de bloqueo se detiene (cliente no autorizó)
        """

        reto = _RETOS.get(challenge)
        if not reto:
            return JSONResponse(
                status_code=404,
                content={"error": f"challenge '{challenge}' not found"}
            )
        
        if reto.get("status") == "rejected":
            return JSONResponse(
                status_code=200,
                content={"status": "ok", "message": "challenge already rejected"}
            )
        
        if reto.get("status") == "accepted":
            return JSONResponse(
                status_code=409,
                content={"error": "challenge was accepted, cannot reject"}
            )
        
        # Cambiar estado de pending → rejected
        reto["status"] = "rejected"
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "message": f"challenge '{challenge}' rejected",
                "data": {
                    "challenge": challenge,
                    "status": "rejected",
                    "sondeos": reto.get("sondeos", 0)
                }
            }
        )

    @app.post("/security/v0/order-chanel/{challenge}/expire")
    async def expire_challenge(challenge: str) -> Response:
        """[TEST ONLY] Simular que el reto caducó en el ASO (ventana agotada).

        Cambia el estado del challenge a 'expired' desde cualquier estado no
        terminal. Los siguientes GETs devolverán status='expired' y el flujo
        debe cerrar sin bloquear (escenario 4 del pliego de pruebas).
        """

        reto = _RETOS.get(challenge)
        if not reto:
            return JSONResponse(
                status_code=404,
                content={"error": f"challenge '{challenge}' not found"}
            )

        if reto.get("status") in ("accepted", "rejected"):
            return JSONResponse(
                status_code=409,
                content={"error": f"challenge is '{reto['status']}', cannot expire"}
            )

        reto["status"] = "expired"

        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "message": f"challenge '{challenge}' expired",
                "data": {
                    "challenge": challenge,
                    "status": "expired",
                    "sondeos": reto.get("sondeos", 0)
                }
            }
        )

    @app.post("/cards/v2/operations")
    async def operations_challenge(request: Request) -> Response:
        """Los tres pasos del reto, distinguidos por las cabeceras recibidas.
        
        Paso 1: Sin cabeceras → 403 + authenticationtype
        Paso 2: Con tipo + datos → 401 + challenge + state (INICIA RETO EN PENDING)
        Paso 3: Con state → 201 + ejecuta (REQUIERE status=accepted)
        """

        body = await request.json()
        card_id = str(((body or {}).get("card", {}) or {}).get("cardId", ""))
        if resolver.block_should_fail(card_id):
            return JSONResponse(status_code=502, content={"error": "reissuance failed"})

        cabeceras = {k.lower(): v for k, v in request.headers.items()}
        tipo = cabeceras.get("authenticationtype", "")
        datos = cabeceras.get("authenticationdata", "")
        estado = cabeceras.get("authenticationstate", "")

        # Paso 3: trae el estado -> valida que fue aceptado -> ejecuta la operacion.
        # El estado de autorización pertenece al header `authenticationstate`;
        # no forma parte de `authenticationdata` (contrato del paso 3).
        if estado:
            challenge = f"sim-{card_id[-4:] or '0000'}-challenge"
            reto = _RETOS.get(challenge, {})
            
            # Validar que el cliente aprobó (status=accepted)
            if reto.get("status") != "accepted":
                return JSONResponse(
                    status_code=403,
                    content={"error": f"challenge not accepted (status={reto.get('status', 'unknown')})"}
                )
            
            return JSONResponse(status_code=201,
                                content={"status": "ok", "cardId": card_id})

        # Paso 2: trae tipo y datos -> envia el push y entrega el reto.
        if tipo and datos:
            challenge = f"sim-{card_id[-4:] or '0000'}-challenge"
            
            # Inicializar reto en estado PENDING (debe aprobarse explicitamente)
            _RETOS[challenge] = {
                "status": "pending",
                "sondeos": 0,
                "card_id": card_id,
            }
            
            return JSONResponse(
                status_code=401,
                content={"messages": [{"code": "authenticationRequired"}]},
                headers={"authenticationChallenge": challenge,
                         "authenticationstate": f"sim-state-{card_id[-4:] or '0000'}"},
            )

        # Paso 1: sin cabeceras -> exige subir de nivel.
        return JSONResponse(
            status_code=403,
            content={"messages": [{"code": "authenticationTypeRequired"}]},
            headers={"authenticationtype": "241"},
        )

    return app


app = build_app()
