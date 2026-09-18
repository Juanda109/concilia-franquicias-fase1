
from fastapi import APIRouter, Query, status
import asyncio
import os
from application.trx.analysis_service import TrxAnalysisService
from application.trx import aso_rules
from domain.trx.models import TrxCase
from infrastructure.core.config import load_trx_flow_settings
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.observability.ceremonia_subida_nivel import (
    CeremoniaDeSubidaDeNivel,
)
from infrastructure.persistence.aso_client import TrxAsoClient, huella_tsec

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/trx", tags=["trx"])
_analysis_service = TrxAnalysisService()


@router.get(
    "/debug/env",
    status_code=status.HTTP_200_OK,
    summary="Debug: show DIAS env and trx flow settings",
)
async def debug_env():
    """Return env values and the resolved TrxFlowSettings for runtime verification."""
    try:
        from infrastructure.core.config import load_trx_aso_settings, load_trx_source_settings
        flow = load_trx_flow_settings()
        aso = load_trx_aso_settings()
        src = load_trx_source_settings()
        return {
            "ENV_FILE": os.getenv("ENV_FILE") or None,
            "DIAS_HABILES_DEVOLUCION": os.getenv("DIAS_HABILES_DEVOLUCION") or None,
            "DIAS_HABILES_TARJETA": os.getenv("DIAS_HABILES_TARJETA") or None,
            "aso": {
                "source": aso.source,
                "base_url": aso.base_url,
            },
            "sources": {
                "products_source": src.products_source,
                "salesforce_source": src.salesforce_source,
                "salesforce_mock_file": src.salesforce_mock_file,
            },
            "env_raw": {
                "ASO_SOURCE": os.getenv("ASO_SOURCE"),
                "ASO_SIMULATOR_URL": os.getenv("ASO_SIMULATOR_URL"),
                "TRX_PRODUCTS_SOURCE": os.getenv("TRX_PRODUCTS_SOURCE"),
                "TRX_ALLOW_MOCKS": os.getenv("TRX_ALLOW_MOCKS"),
                "LOCAL_CONTINGENCY_MODE": os.getenv("LOCAL_CONTINGENCY_MODE"),
            },
            "flow": {
                "dias_habiles_devolucion": flow.dias_habiles_devolucion,
                "vigencia_visa_dias": flow.vigencia_visa_dias,
                "vigencia_master_dias": flow.vigencia_master_dias,
            },
        }
    except Exception as e:
        logger.exception("debug/env failed")
        return {"error": str(e)}


def _local_contingency_enabled() -> bool:
    raw = (os.getenv("LOCAL_CONTINGENCY_MODE") or "").strip().casefold()
    return raw in {"1", "true", "yes", "on"}


@router.get(
    "/validar-recurrencia",
    status_code=status.HTTP_200_OK,
    summary="Validar si el cliente tiene interacciones en los últimos 6 meses (Paso 3)",
)
@log_execution
async def validar_recurrencia(
    customer_id: str = Query(
        ...,
        min_length=1,
        description="Identificador del cliente para consultar recurrencia en Salesforce",
        examples=["03966512"],
    )
):
    logger.info(f"Consultando recurrencia para customer_id: {customer_id}")
    result = _analysis_service.consultar_recurrencia_salesforce(
        TrxCase(customer_id=customer_id)
    )
    return {
        "status": "success",
        "customer_id": customer_id,
        "targetUserId": result.data.get("targetUserId", ""),
        "has_recurrence": result.status == "REDIRECT_PQR",
        "id_message": result.id_message,
        "detail": result.detail,
        "data": result.data,
    }


def _envelope(result) -> dict:
    """Serialize a TrxResult into the JSON envelope used by the agent client."""

    return {
        "status": result.status,
        "id_message": result.id_message,
        "step": result.step,
        "detail": result.detail,
        "data": result.data,
    }


@router.get(
    "/productos-activos",
    status_code=status.HTTP_200_OK,
    summary="Productos vigentes activos del cliente (Paso 2.4.0.2)",
)
@log_execution
async def productos_activos(
    customer_id: str = Query(..., min_length=1, examples=["03966512"]),
):
    logger.info("Consultando productos activos customer_id=%s", customer_id)
    result = _analysis_service.consultar_productos_activos(TrxCase(customer_id=customer_id))
    return _envelope(result)


@router.get(
    "/customer-address",
    status_code=status.HTTP_200_OK,
    summary="Direccion del cliente directo de Postgres (fail-open)",
)
@log_execution
async def customer_address(
    customer_id: str = Query(..., min_length=1, examples=["03966512"]),
):
    direccion = await asyncio.to_thread(
        _analysis_service.resolve_customer_address_from_postgres,
        customer_id,
    )
    return {
        "customer_id": customer_id,
        "customer_address": direccion,
        "found": bool(direccion),
    }


@router.get(
    "/identity-by-card",
    status_code=status.HTTP_200_OK,
    summary="Identidad TXNR por tarjeta desde Postgres",
)
@log_execution
async def identity_by_card(
    customer_id: str = Query(..., min_length=1, examples=["03966512"]),
    last_four: str = Query(..., min_length=4, max_length=4),
    origin_flag: str = Query("TDC"),
):
    identity = await asyncio.to_thread(
        _analysis_service.get_trx_identity_by_card,
        customer_id=customer_id,
        last_four=last_four,
        origin_flag=origin_flag,
    )
    return {
        "customer_id": customer_id,
        "last_four": last_four,
        "origin_flag": origin_flag,
        "account_id": str(identity.get("account_id") or "").strip(),
        "personal_id": str(identity.get("personal_id") or "").strip(),
        "found": bool(identity.get("account_id")),
    }


@router.get(
    "/movimientos",
    status_code=status.HTTP_200_OK,
    summary="Vigencia por franquicia + movimientos por producto y fecha (Paso 2.4.0.3)",
)
@log_execution
async def movimientos(
    customer_id: str = Query(..., min_length=1, examples=["03966512"]),
    contract_id: str = Query("", description="Producto donde se consultan los movimientos"),
    fecha: str = Query("", description="Fecha de la transacción (DD/MM/AAAA)"),
    card_franchise: str = Query("VISA", description="VISA / MASTER (vigencia 180/120)"),
):
    logger.info(
        "Consultando movimientos customer_id=%s contract_id=%s fecha=%s franquicia=%s",
        customer_id,
        contract_id,
        fecha,
        card_franchise,
    )
    case = TrxCase(
        customer_id=customer_id,
        product_id=contract_id or None,
        data={
            "contract_id": contract_id,
            "fecha": fecha,
            "card_franchise": card_franchise,
        },
    )
    result = _analysis_service.consultar_movimientos_aso(case)
    return _envelope(result)


@router.get(
    "/evaluar-valor",
    status_code=status.HTTP_200_OK,
    summary="Valida el rango de valor por transacción ($35.000–$500.000) (Paso 2.4.0.1.4)",
)
@log_execution
async def evaluar_valor(
    monto: float = Query(..., description="Valor de la transacción a validar"),
):
    logger.info("Evaluando valor de transacción monto=%s", monto)
    result = _analysis_service.evaluar_transaccion_individual(monto)
    return _envelope(result)


# =============================================================================
# Endpoints ASO (Fase 2) — usan TrxAsoClient (toggle simulator/real) + aso_rules.
# =============================================================================
from datetime import datetime  # noqa: E402


def _parse_ddmmyyyy(fecha: str) -> datetime | None:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime((fecha or "").strip(), fmt)
        except ValueError:
            continue
    return None


@router.get("/card-id", status_code=status.HTTP_200_OK, summary="Card id (PAN) desde financial-overview (2.4.0.1.8)")
@log_execution
async def card_id(
    customer_id: str = Query(..., min_length=1),
    contract_id: str = Query("", description="Contract id resuelto desde productos activos"),
    last_four: str = Query("", description="Legacy: ultimos 4 (opcional)"),
):
    flow = load_trx_flow_settings()
    client = TrxAsoClient()
    tsec = client.get_tsec()
    fo = client.financial_overview(
        customer_id=customer_id,
        contract_id=contract_id,
        tsec=tsec,
    )
    card = None
    if fo:
        # La peticion ya va filtrada por contrato (ver aso_client), pero el
        # contrato se LOCALIZA en la respuesta por los campos configurables
        # (FO_CONTRACT_MATCH_FIELD=number, FO_CARD_NUMBER_PATH=id), no por el
        # contract_id de ADA: son espacios de identificadores distintos -- ADA
        # entrega un LIC y el JSON devuelve el PAN. Buscar por el contract_id
        # de ADA dentro de la respuesta devolvia contracts=[] y dejaba al
        # cliente sin movimientos.
        card = aso_rules.extraer_card_id(
            fo,
            match_value=last_four,
            match_field=flow.fo_contract_match_field,
            card_number_path=flow.fo_card_number_path,
        )
    if fo is None:
        # El ASO no contesto (o el tsec fallo): NO es "la tarjeta no existe".
        # El agente trata "error" como fallo de servicio y deriva a .4.error,
        # en vez de dejar al cliente avanzar con datos sin verificar.
        return {
            "status": "error",
            "card_id": None,
            "customer_id": customer_id,
            "contract_id": contract_id,
        }
    return {
        "status": "ok" if card else "not_found",
        "card_id": card,
        "customer_id": customer_id,
        "contract_id": contract_id,
    }


def _consultar_movimientos_dia(
    card_id: str,
    fecha: str,
    from_amount: float | None,
    to_amount: float | None,
) -> dict:
    """Fetch unico al ASO + parse + filtro de rango, compartido por los dos
    endpoints de movimientos (``-aso`` sin paginar y ``-pagina``).

    Devuelve un dict con ``ok`` (False = el ASO no contesto, fail-closed), la
    lista ya filtrada (cada movimiento con ``id`` no vacio), ``fuera_de_rango``,
    ``total_del_dia`` y los montos efectivos. No pagina: eso queda para
    ``aso_rules.paginar_movimientos``.
    """

    flow = load_trx_flow_settings()
    parsed = _parse_ddmmyyyy(fecha)
    day_iso = parsed.strftime("%Y-%m-%d") if parsed else ""
    monto_min = from_amount if from_amount is not None else flow.monto_min
    monto_max = to_amount if to_amount is not None else flow.monto_max

    client = TrxAsoClient()
    tsec = client.get_tsec()
    ops = client.operations(card_id, operation_date=day_iso, tsec=tsec)

    if ops is None:
        # El ASO no contesto: distinto de "el dia no tiene compras". El agente
        # trata "error" como fallo_aso y deriva a .8.error en vez de afirmar
        # "no encontramos compras registradas".
        return {
            "ok": False,
            "movimientos": [],
            "fuera_de_rango": 0,
            "total_del_dia": 0,
            "monto_min": monto_min,
            "monto_max": monto_max,
        }

    todos = aso_rules.parse_movimientos_operations(ops)
    logger.info(
        "movimientos parseados card=****%s fecha=%s total=%s descripciones=%s",
        str(card_id)[-4:],
        fecha,
        len(todos),
        [str(m.get("descripcion") or "")[:40] for m in todos[:5]],
    )
    movimientos, fuera_de_rango = aso_rules.filtrar_por_rango(
        todos, monto_min=monto_min, monto_max=monto_max
    )
    # id estable para la seleccion por id (contrato Fase 0): el id del ASO es la
    # fuente; si un movimiento llega sin id (fixtures antiguos / payload parcial)
    # se le asigna uno sintetico y estable por posicion en la lista filtrada,
    # para que la seleccion nunca quede sin clave y sea consistente entre paginas.
    for pos, mov in enumerate(movimientos):
        if not str(mov.get("id") or "").strip():
            mov["id"] = f"mov_{pos}"
    return {
        "ok": True,
        "movimientos": movimientos,
        "fuera_de_rango": fuera_de_rango,
        "total_del_dia": len(todos),
        "monto_min": monto_min,
        "monto_max": monto_max,
    }


@router.get("/movimientos-aso", status_code=status.HTTP_200_OK, summary="Movimientos ASO por tarjeta/fecha/rango (2.4.0.1.8)")
@log_execution
async def movimientos_aso(
    card_id: str = Query(..., min_length=1),
    fecha: str = Query(..., description="DD/MM/AAAA"),
    from_amount: float | None = Query(None),
    to_amount: float | None = Query(None),
):
    """Lista los movimientos del dia con su detalle (paso 2.4.0.1.8 -> 2.4.0.1.9).

    Consume ``/cards/v2/operations`` (via ``_consultar_movimientos_dia``). El
    filtro de rango de importe se aplica en el servicio: ``operations`` no acepta
    filtros de monto. Endpoint sin paginar: mantiene el contrato historico. Para
    paginacion usar ``/movimientos-pagina``.
    """

    r = _consultar_movimientos_dia(card_id, fecha, from_amount, to_amount)
    if not r["ok"]:
        return {
            "status": "error",
            "movimientos": [],
            "card_id": card_id,
            "fecha": fecha,
            "fuera_de_rango": 0,
            "monto_min": r["monto_min"],
            "monto_max": r["monto_max"],
        }
    movimientos = r["movimientos"]
    return {
        "status": "ok" if movimientos else "not_found",
        "movimientos": movimientos,
        "card_id": card_id,
        "fecha": fecha,
        "fuera_de_rango": r["fuera_de_rango"],
        "total_del_dia": r["total_del_dia"],
        "monto_min": r["monto_min"],
        "monto_max": r["monto_max"],
    }


@router.get("/movimientos-pagina", status_code=status.HTTP_200_OK, summary="Movimientos del dia paginados (2.4.0.1.9)")
@log_execution
async def movimientos_pagina(
    card_id: str = Query(..., min_length=1),
    fecha: str = Query(..., description="DD/MM/AAAA"),
    from_amount: float | None = Query(None),
    to_amount: float | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=100),
):
    """Movimientos del dia troceados en paginas (contrato Fase 0).

    Sabor A: un unico fetch al ASO (cacheado por card+fecha), filtro de rango y
    slice en el servicio. La navegacion entre paginas no vuelve a llamar al ASO.
    El agente pasa ``page`` y pinta lo que llega, con "Anterior"/"Ver mas" segun
    ``has_prev``/``has_next``; la seleccion es por ``id``.
    """

    r = _consultar_movimientos_dia(card_id, fecha, from_amount, to_amount)
    if not r["ok"]:
        # Fail-closed, igual que movimientos-aso: no afirmar "no hay compras".
        return {
            "status": "error",
            "card_id": card_id,
            "fecha": fecha,
            "page": page,
            "page_size": page_size,
            "total": 0,
            "total_pages": 1,
            "has_prev": False,
            "has_next": False,
            "fuera_de_rango": 0,
            "monto_min": r["monto_min"],
            "monto_max": r["monto_max"],
            "movimientos": [],
        }

    pag = aso_rules.paginar_movimientos(
        r["movimientos"], page=page, page_size=page_size
    )
    return {
        "status": "ok" if pag["total"] else "not_found",
        "card_id": card_id,
        "fecha": fecha,
        "page": pag["page"],
        "page_size": pag["page_size"],
        "total": pag["total"],
        "total_pages": pag["total_pages"],
        "has_prev": pag["has_prev"],
        "has_next": pag["has_next"],
        "fuera_de_rango": r["fuera_de_rango"],
        "total_del_dia": r["total_del_dia"],
        "monto_min": r["monto_min"],
        "monto_max": r["monto_max"],
        "movimientos": pag["movimientos"],
    }


@router.get("/detalle", status_code=status.HTTP_200_OK, summary="Detalle de la operacion + clasificacion (2.4.0.1.10/1.19)")
@log_execution
async def detalle(
    card_id: str = Query(..., min_length=1),
    fecha: str = Query(..., description="DD/MM/AAAA"),
    tx_id: str = Query(..., min_length=1),
    origin_flag: str = Query("", description="TDC / Pasivo (para pendiente y clasificacion)"),
):
    flow = load_trx_flow_settings()
    parsed = _parse_ddmmyyyy(fecha)
    yyyymmdd = parsed.strftime("%Y%m%d") if parsed else ""
    client = TrxAsoClient()
    tsec = client.get_tsec()
    ops = client.operations(card_id, operation_date=yyyymmdd, tsec=tsec)
    det = aso_rules.extraer_detalle(ops, tx_id=tx_id, tx_op_id_field=flow.tx_op_id_field) if ops else None
    if not det:
        return {"status": "not_found", "detalle": None, "clasificacion": None}
    clasif = aso_rules.clasificar_investigacion(
        det,
        origin_flag=origin_flag,
        eci_path=flow.eci_path,
        ecard_path=flow.ecard_path,
        response_oper_path=flow.response_oper_path,
        eci_chargeback_set=flow.eci_chargeback_set,
    )
    return {"status": "ok", "detalle": det, "clasificacion": clasif}


@router.post(
    "/subida-nivel",
    status_code=status.HTTP_200_OK,
    summary="Envia la notificacion push para autorizar el bloqueo (2.4.0.1.16.1/17.1)",
)
@log_execution
async def subida_nivel(
    card_id: str = Query(..., min_length=1),
    personal_id: str = Query(
        ...,
        min_length=1,
        description="personal_id de Postgres",
    ),
    account_last_four: str = Query(
        "",
        description=(
            "Ultimos 4 del account_id que el agente ya obtuvo de Postgres en "
            "/identity-by-card. Obligatorio: trx no vuelve a consultar"
        ),
    ),
):
    """Pasos 1-3 de la subida de nivel.

    1. Obtiene el dispositivo activo del cliente.
    2. Usa el `account_last_four` que envia el agente (una sola consulta a
       Postgres por subida de nivel: la de /identity-by-card).
    3. Inicia el reto de autenticación.
    4. Envía la notificación push.

    Devuelve challenge y authentication_state para que
    los pasos posteriores puedan consultar la autorización.

    Este endpoint NO ejecuta el bloqueo.
    """

    # ---------------------------------------------------------
    # Cliente ASO
    # ---------------------------------------------------------
    client = TrxAsoClient()

    normalized_card_id = str(card_id or "").strip()
    normalized_personal_id = str(personal_id or "").strip()

    # Registro de la ceremonia. Anota CADA etapa, incluidas las que no llaman al
    # ASO -y que antes no dejaban rastro-, y al final un resumen con la secuencia.
    ceremonia = CeremoniaDeSubidaDeNivel(
        card_id=normalized_card_id, personal_id=normalized_personal_id
    )

    if not normalized_card_id:
        ceremonia.etapa("card_id", "error", detalle="card_id es obligatorio")
        ceremonia.cerrar("error", "card_id es obligatorio")
        return {
            "status": "error",
            "etapa": "card_id",
            "detalle": "card_id es obligatorio",
        }

    if not normalized_personal_id:
        ceremonia.etapa("personal_id", "error", detalle="personal_id es obligatorio")
        ceremonia.cerrar("error", "personal_id es obligatorio")
        return {
            "status": "error",
            "etapa": "personal_id",
            "detalle": "personal_id es obligatorio",
        }

    # Últimos 4 de la TARJETA.
    last_four = normalized_card_id[-4:]

    # Profile ID utilizado por el ASO: CC + cedula rellenada con ceros a 15
    # digitos (contrato del ASO real, 28/08: cedula 3017449 -> CC000000003017449).
    # Sin el relleno, user-status no encuentra dispositivos y la subida de
    # nivel muere en etapa "dispositivo"; el simulador no lo detecta porque
    # acepta cualquier profileId.
    profile_id = f"CC{normalized_personal_id.zfill(15)}"

    # ---------------------------------------------------------
    # account_last_four: UNA sola consulta a Postgres
    # ---------------------------------------------------------
    # El agente ya resolvio el account_id en /identity-by-card (por customer_id)
    # y manda sus ultimos 4. trx NO vuelve a consultar ada_info_detail: esa
    # segunda consulta pasaba la cedula como customer_id, no encontraba la fila
    # cuando customer_id != personal_id (clientes reales) y la subida de nivel
    # moria en etapa "account_id" (QA 13083558 y dev 98782372, 14/09).
    # Se valida ANTES del TSEC: sin cuenta no hay reto posible.
    # Llamado directo (tests) deja el Query() sin resolver: de ahi el isinstance.
    account_last_four = (
        account_last_four.strip() if isinstance(account_last_four, str) else ""
    )
    if not (len(account_last_four) == 4 and account_last_four.isdigit()):
        detalle = "el agente no envio account_last_four (4 digitos)"
        ceremonia.etapa("account_id", "error", detalle=detalle)
        ceremonia.cerrar("error", detalle)
        return {
            "status": "error",
            "etapa": "account_id",
            "profile_id": profile_id,
            "card_id": normalized_card_id,
            "last_four": last_four,
            "detalle": detalle,
        }

    # URLs a las que sale cada paso, resueltas igual que en TrxAsoClient: el TSEC
    # por la base de consultas y el reto (user-status y operations) por la base
    # del challenge. Solo para la traza de la ceremonia.
    url_tsec = (
        client.settings.ticket_url
        or f"{client._base()}/TechArchitecture/co/grantingTicket/V02"
    )
    url_user_status = f"{client._challenge_base()}{client.settings.user_status_path}"
    url_operations = f"{client._challenge_base()}{client.settings.operations_path}"

    # ---------------------------------------------------------
    # Paso 0: TSEC
    # ---------------------------------------------------------
    # Las llamadas al ASO son httpx SINCRONAS (timeout de hasta 30 s): se
    # corren en un hilo para no congelar el event loop, que atiende a TODAS
    # las conversaciones del servicio.
    tsec = await asyncio.to_thread(client.get_tsec)
    # Huella del TSEC (nunca el valor) + id de cadena, igual que en las trazas
    # por llamada al ASO: muestra que token uso cada etapa de la ceremonia.
    traza_tsec = {**huella_tsec(tsec), "aso_chain_id": client._chain_id}

    if not tsec:
        ceremonia.etapa(
            "tsec", "error", method="POST", url=url_tsec, peticion=traza_tsec,
            detalle="no se obtuvo TSEC",
        )
        ceremonia.cerrar("error", "no se obtuvo TSEC")
        return {
            "status": "error",
            "etapa": "tsec",
            "detalle": "no se obtuvo TSEC",
        }

    ceremonia.etapa("tsec", "ok", method="POST", url=url_tsec, peticion=traza_tsec)

    # ---------------------------------------------------------
    # Paso 1: dispositivo activo
    # ---------------------------------------------------------
    dispositivo = await asyncio.to_thread(
        client.user_status,
        profile_id,
        tsec=tsec,
    )

    if not dispositivo.get("activo"):
        ceremonia.etapa(
            "user_status",
            "error",
            method="GET",
            url=url_user_status,
            params={"profileId": profile_id}, peticion=traza_tsec,
        )
        ceremonia.cerrar("error", "fallo en user_status")
        return {
            "status": "sin_dispositivo",
            "etapa": "user_status",
            "profile_id": profile_id,
            "total_dispositivos": dispositivo.get(
                "total_dispositivos",
                0,
            ),
            "detalle": (
                "el cliente no tiene un dispositivo "
                "con softToken ACTIVE"
            ),
        }

    device_id = dispositivo.get("device_id")

    if not device_id:
        ceremonia.etapa(
            "user_status",
            "error",
            method="GET",
            url=url_user_status,
            params={"profileId": profile_id}, peticion=traza_tsec,
        )
        ceremonia.cerrar("error", "fallo en user_status")
        return {
            "status": "error",
            "etapa": "user_status",
            "profile_id": profile_id,
            "detalle": (
                "el ASO devolvio dispositivo activo "
                "pero no devolvio device_id"
            ),
        }

    ceremonia.etapa(
        "user_status",
        "ok",
        method="GET",
        url=url_user_status,
        params={"profileId": profile_id}, peticion=traza_tsec,
    )

    # ---------------------------------------------------------
    # Paso 2: iniciar reto
    # ---------------------------------------------------------
    #
    # POST /cards/v2/operations
    #
    # Esperamos el 403 con authenticationtype.
    # ---------------------------------------------------------

    reto = await asyncio.to_thread(
        client.challenge_iniciar,
        normalized_card_id,
        tsec=tsec,
    )

    ceremonia.etapa(
        "challenge_iniciar",
        "ok" if reto.get("ok") else "error",
        method="POST",
        url=url_operations,
        peticion=traza_tsec,
        status_code=reto.get("status_code"),
        authentication_type=reto.get("authentication_type"),
    )

    if not reto.get("ok"):
        ceremonia.cerrar("error", "fallo en challenge_iniciar")
        return {
            "status": "error",
            "etapa": "challenge_iniciar",
            "status_code": reto.get("status_code"),
            "authentication_type": reto.get(
                "authentication_type"
            ),
            "esperado": reto.get("esperado"),
            "card_id": normalized_card_id,
            "profile_id": profile_id,
            "detalle": (
                "el ASO no devolvio el tipo "
                "de autenticacion esperado"
            ),
        }

    # ---------------------------------------------------------
    # Paso 3: enviar push
    # ---------------------------------------------------------
    #
    # POST /cards/v2/operations
    #
    # En este punto enviamos:
    #
    #   device_id
    #   profile_id
    #   last_four
    #   account_last_four
    #
    # El usuario NO los proporciona como parametros.
    # Todos fueron obtenidos internamente.
    # ---------------------------------------------------------

    push = await asyncio.to_thread(
        client.challenge_enviar_push,
        normalized_card_id,
        device_id=device_id,
        profile_id=profile_id,
        account_last_four=account_last_four,
        tsec=tsec,
    )

    if not push.get("ok"):
        ceremonia.etapa(
            "challenge_enviar_push",
            "error",
            method="POST",
            url=url_operations,
            status_code=push.get("status_code"), peticion=traza_tsec,
        )
        ceremonia.cerrar("error", "fallo en challenge_enviar_push")
        return {
            "status": "error",
            "etapa": "challenge_enviar_push",
            "status_code": push.get("status_code"),
            "card_id": normalized_card_id,
            "profile_id": profile_id,
            "detalle": (
                "el ASO no devolvio authenticationChallenge"
            ),
        }

    # ---------------------------------------------------------
    # Resultado
    # ---------------------------------------------------------

    # La ceremonia llego hasta el push. NO esta autorizada todavia: eso lo dice
    # /subida-nivel/estado. Se distingue en la traza para no leer "ok" como
    # "el cliente ya aprobo", que es un malentendido caro.
    ceremonia.etapa(
        "challenge_enviar_push",
        "ok",
        method="POST",
        url=url_operations,
        status_code=push.get("status_code"), peticion=traza_tsec,
        tiene_challenge=bool(push.get("challenge")),
        tiene_authentication_state=bool(push.get("authentication_state")),
    )
    ceremonia.cerrar("ok", "push enviado; pendiente de que el cliente autorice")

    return {
        "status": "ok",
        "enviado": True,
        "device_id": device_id,
        "profile_id": profile_id,
        "challenge": push["challenge"],
        "authentication_state": push["authentication_state"],
        "card_id": normalized_card_id,
    }


@router.get(
    "/subida-nivel/estado",
    status_code=status.HTTP_200_OK,
    summary="Consulta el estado actual de la autorización"
)
@log_execution
def subida_nivel_estado(
    challenge: str = Query(..., min_length=1),
    intentos: int = Query(1, ge=1, le=8, description="Obsoleto: se consulta una sola vez"),
    espera: float = Query(1.5, ge=0.2, le=3.0, description="Obsoleto: ya no hay espera"),
):
    """Paso 4: consulta el estado actual del reto UNA sola vez.

    Sin sondeo interno: nada de time.sleep ni reintentos dentro de la peticion.
    La ventana de 3 minutos se reparte entre pulsaciones de "Continuar" del
    cliente (el agente reconsulta en cada una y controla el plazo con su propio
    deadline); esperar aqui dentro bloqueaba el proceso para TODAS las
    conversaciones. `intentos` y `espera` se aceptan por compatibilidad con
    clientes viejos y se ignoran.

    Handler sincrono a proposito: FastAPI lo lleva al threadpool y la llamada
    bloqueante al ASO no congela el event loop.
    """

    client = TrxAsoClient()
    tsec = client.get_tsec()

    # Un fallo tecnico (sin TSEC o ASO caido) NO es "pendiente": antes el cliente
    # pulsaba "Continuar" hasta agotar los 3 minutos y se cerraba como si no
    # hubiera autorizado. "estado": "error" hace que el agente lo trate como error.
    if not tsec:
        return {
            "status": "error",
            "aceptado": False,
            "estado": "error",
            "pendiente": False,
            "sondeos": 0,
            "detalle": "no se obtuvo TSEC",
        }

    ultimo = client.order_channel_status(challenge, tsec=tsec)
    if ultimo.get("estado") == "error":
        return {
            "status": "error",
            "aceptado": False,
            "estado": "error",
            "pendiente": False,
            "sondeos": 1,
            "detalle": "el ASO no respondio el estado del reto",
        }
    if ultimo.get("aceptado"):
        return {
            "status": "ok",
            "aceptado": True,
            "estado": ultimo.get("estado"),
            "sondeos": 1,
        }

    return {
        "status": "ok",
        "aceptado": bool(ultimo.get("aceptado")),
        "estado": ultimo.get("estado", ""),
        "pendiente": bool(ultimo.get("pendiente")),
        "sondeos": 1,
    }


@router.post("/bloqueo", status_code=status.HTTP_200_OK,
             summary="Ejecuta el bloqueo tras la autorizacion (2.4.0.1.16.2/17.2)")
@log_execution
async def bloqueo(
    card_id: str = Query(..., min_length=1),
    tipo: str = Query(..., description="temporal | permanente"),
    challenge: str = Query("", description="Requerido para permanente"),
    authentication_state: str = Query("", description="Requerido para permanente"),
    device_id: str = Query("", description="Requerido para permanente"),
    profile_id: str = Query("", description="Requerido para permanente"),
    account_last_four: str = Query("", description="Ultimos 4 de la cuenta asociada")
):
    """Ejecuta el bloqueo, ya con la autorizacion del cliente.

    - **temporal**: PATCH de apagado (`ON_OFF`, `isActive=false`). NO se llama al
      tercer POST del reto: ese ejecuta la CANCELACION con reexpedicion, y
      apagaria para siempre la tarjeta de quien solo queria apagarla.
    - **permanente**: tercer POST del reto (200 = ejecutado, 400 = no autorizado).
    """

    client = TrxAsoClient()
    tsec = client.get_tsec()
    tipo_n = (tipo or "").strip().casefold()

    if tipo_n == "temporal":
        ok = client.block_temporary(card_id, is_active=False, tsec=tsec)
        return {"status": "ok" if ok else "error", "ok": ok,
                "card_id": card_id, "tipo": tipo_n, "via": "patch_on_off"}

    if tipo_n == "permanente":
        faltantes = [
            nombre for nombre, valor in (
                ("challenge", challenge),
                ("authentication_state", authentication_state),
                ("device_id", device_id),
                ("profile_id", profile_id),
            ) if not str(valor).strip()
        ]
        if faltantes:
            # Sin la autorizacion NO se ejecuta: es la salvaguarda que evita
            # cancelar una tarjeta sin que el cliente lo haya aprobado.
            return {"status": "error", "ok": False, "tipo": tipo_n,
                    "detalle": f"falta la autorizacion: {', '.join(faltantes)}"}
        resultado = client.challenge_confirmar(
            card_id,
            device_id=device_id,
            profile_id=profile_id,
            account_last_four=account_last_four,
            challenge=challenge,
            authentication_state=authentication_state,
            tsec=tsec,
        )
        return {
            "status": "ok" if resultado["ok"] else "error",
            "ok": resultado["ok"],
            "card_id": card_id,
            "tipo": tipo_n,
            "via": "challenge_confirmar",
            "status_code": resultado.get("status_code"),
            "rechazado_por_cliente": resultado.get("rechazado"),
        }

    return {"status": "error", "ok": False, "detail": "tipo debe ser temporal|permanente"}
