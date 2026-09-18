"""Fire-and-forget / fail-open HTTP client for co_pqrs_back_trx_noreconocida.

The trx path is still a MOCK skeleton, so this client is defined but NOT yet wired
into the conversation flow (the flow currently answers "estamos trabajando en este
proceso"). It mirrors the back_data_client conventions: short timeouts, correlation
header propagation and fail-open behaviour (never raise to the caller).
"""

import os

import httpx

from infrastructure.core.config import load_env_constants
from infrastructure.core.logger import get_correlation_id, get_logger

logger = get_logger(__name__)


def _local_contingency_enabled() -> bool:
    """Enable local-only contingency behavior when explicitly configured."""

    try:
        raw = load_env_constants().get("LOCAL_CONTINGENCY_MODE")
    except Exception:
        raw = None
    if raw is None:
        raw = os.getenv("LOCAL_CONTINGENCY_MODE")
    return str(raw or "").strip().casefold() in {"1", "true", "yes", "on"}


def _correlation_headers() -> dict[str, str]:
    """Propagate the current conversation id so trx logs correlate."""

    correlation_id = get_correlation_id()
    if correlation_id and correlation_id != "-":
        return {"X-Correlation-Id": correlation_id}
    return {}


async def _post_mock(
    *,
    base_url: str,
    path: str,
    customer_id: str,
    evento: str | None,
    descripcion: str | None,
    product_id: str | None,
    timeout: float,
) -> dict | None:
    """POST a trx payload and return the JSON body, or None on any failure."""

    url = f"{base_url.rstrip('/')}/v0/{path.lstrip('/')}"
    payload: dict[str, object] = {"customer_id": customer_id}
    if evento is not None:
        payload["evento"] = evento
    if descripcion is not None:
        payload["descripcion"] = descripcion
    if product_id is not None:
        payload["product_id"] = product_id
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url, json=payload, headers=_correlation_headers()
            )
        response.raise_for_status()
        logger.info("trx %s ok customer_id=%s status=%s", path, customer_id, response.status_code)
        return response.json()
    except Exception:
        logger.warning(
            "trx %s failed customer_id=%s url=%s (fail-open)", path, customer_id, url
        )
        return None


async def validar_recurrencia(
    *,
    base_url: str,
    customer_id: str,
    timeout: float = 10.0,
) -> dict | None:
    """Call trx recurrence API (Salesforce/ASO mock backed)."""

    url = f"{base_url.rstrip('/')}/v1/trx/validar-recurrencia"
    params = {"customer_id": customer_id}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                url,
                params=params,
                headers=_correlation_headers(),
            )
        response.raise_for_status()
        logger.info(
            "trx validar_recurrencia ok customer_id=%s status=%s",
            customer_id,
            response.status_code,
        )
        return response.json()
    except Exception:
        logger.warning(
            (
                "trx validar_recurrencia failed customer_id=%s "
                "url=%s (fail-open)"
            ),
            customer_id,
            url,
        )
        return None


async def consultar_trx(
    *,
    base_url: str,
    customer_id: str,
    descripcion: str | None = None,
    product_id: str | None = None,
    fecha: str | None = None,
    card_franchise: str | None = None,
    timeout: float = 10.0,
) -> dict | None:
    """Vigencia por franquicia + movimientos por producto y fecha (GET /v1/trx/movimientos)."""

    url = f"{base_url.rstrip('/')}/v1/trx/movimientos"
    params = {
        "customer_id": customer_id,
        "contract_id": product_id or "",
        "fecha": fecha or "",
        "card_franchise": (card_franchise or "VISA"),
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params, headers=_correlation_headers())
        response.raise_for_status()
        logger.info("trx movimientos ok customer_id=%s status=%s", customer_id, response.status_code)
        return response.json()
    except Exception:
        logger.warning("trx movimientos failed customer_id=%s url=%s (fail-open)", customer_id, url)
        return None


async def consultar_productos_activos(
    *,
    base_url: str,
    customer_id: str,
    timeout: float = 10.0,
) -> dict | None:
    """Productos vigentes activos (GET /v1/trx/productos-activos)."""

    url = f"{base_url.rstrip('/')}/v1/trx/productos-activos"
    params = {"customer_id": customer_id}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params, headers=_correlation_headers())
        response.raise_for_status()
        logger.info("trx productos-activos ok customer_id=%s status=%s", customer_id, response.status_code)
        return response.json()
    except Exception:
        logger.warning("trx productos-activos failed customer_id=%s url=%s (fail-open)", customer_id, url)
        return None


async def run_aso(
    *,
    base_url: str,
    customer_id: str,
    timeout: float = 10.0,
) -> dict | None:
    """MOCK: invocar los ASOS del caso (por definir)."""

    return await _post_mock(
        base_url=base_url,
        path="aso",
        customer_id=customer_id,
        evento=None,
        descripcion=None,
        product_id=None,
        timeout=timeout,
    )


async def analizar(
    *,
    base_url: str,
    customer_id: str,
    evento: str | None = None,
    timeout: float = 10.0,
) -> dict | None:
    """MOCK: analizar el origen del evento."""

    return await _post_mock(
        base_url=base_url,
        path="analisis",
        customer_id=customer_id,
        evento=evento,
        descripcion=None,
        product_id=None,
        timeout=timeout,
    )


# --- Fase 2: endpoints ASO del back_trx (card-id / movimientos-aso / detalle / bloqueo) ---
import time as _time  # noqa: E402
from infrastructure.observability.trace_audit import schedule_trace_event  # noqa: E402


async def _get_json(
    url: str, params: dict, timeout: float, *, operation: str = "trx_get", customer_id: str | None = None
) -> dict | None:
    start = _time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params, headers=_correlation_headers())
        response.raise_for_status()
        data = response.json()
        schedule_trace_event(
            event_type="http",
            operation=operation,
            outcome="ok",
            status_code=response.status_code,
            elapsed_ms=round((_time.perf_counter() - start) * 1000, 2),
            target=url,
            customer_id=customer_id,
            request_summary={"params": {k: v for k, v in params.items() if k != "last_four"}},
            response_summary={
                "status": str((data or {}).get("status")),
                "keys": list((data or {}).keys())[:10],
            },
            tags=["trx", "agent", operation],
        )
        return data
    except Exception as exc:
        logger.warning("trx GET failed url=%s (fail-open)", url)
        schedule_trace_event(
            event_type="http",
            operation=operation,
            outcome="error",
            elapsed_ms=round((_time.perf_counter() - start) * 1000, 2),
            target=url,
            customer_id=customer_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
            tags=["trx", "agent", operation],
        )
        return None


async def obtener_card_id(
    *,
    base_url: str,
    customer_id: str,
    contract_id: str = "",
    last_four: str = "",
    timeout: float = 15.0,
) -> dict | None:
    """financial-overview -> card_id (PAN).

    SIEMPRE se envia el contract_id cuando el llamador lo trae. Aqui vivia el
    ultimo resto de LOCAL_CONTINGENCY_MODE: con la bandera sin definir (todos
    los entornos), la rama else DESCARTABA el contract_id que ambos llamadores
    pasan, el servicio recibia contrato vacio y el financial-overview salia SIN
    el filtro contracts.id -- exactamente lo que Fabian vio en los logs de DEV
    el 21/08, pese a que el filtro estaba implementado en el servicio desde el
    20/08. Es el mismo patron de "media contingencia" ya retirado del servicio.
    """

    params = {"customer_id": customer_id}
    if str(contract_id).strip():
        params["contract_id"] = str(contract_id).strip()
    if str(last_four).strip():
        params["last_four"] = str(last_four).strip()

    return await _get_json(
        f"{base_url.rstrip('/')}/v1/trx/card-id",
        params,
        timeout,
        operation="trx.card_id",
        customer_id=customer_id,
    )


async def movimientos_aso(
    *,
    base_url: str,
    card_id: str,
    fecha: str,
    from_amount: float | None = None,
    to_amount: float | None = None,
    timeout: float = 20.0,
) -> dict | None:
    """transactions ASO por tarjeta/fecha/rango -> lista de movimientos parseada."""
    params: dict[str, object] = {"card_id": card_id, "fecha": fecha}
    if from_amount is not None:
        params["from_amount"] = from_amount
    if to_amount is not None:
        params["to_amount"] = to_amount
    return await _get_json(
        f"{base_url.rstrip('/')}/v1/trx/movimientos-aso", params, timeout, operation="trx.movimientos"
    )


async def movimientos_pagina(
    *,
    base_url: str,
    card_id: str,
    fecha: str,
    page: int = 1,
    page_size: int = 5,
    from_amount: float | None = None,
    to_amount: float | None = None,
    timeout: float = 20.0,
) -> dict | None:
    """Una pagina de movimientos del dia (GET /v1/trx/movimientos-pagina).

    El servicio hace un fetch unico cacheado al ASO y rebana la pagina (sabor A
    del contrato): la navegacion entre paginas no vuelve a golpear al ASO. La
    respuesta trae page/total_pages/has_prev/has_next y los movimientos con id.
    """
    params: dict[str, object] = {
        "card_id": card_id, "fecha": fecha, "page": page, "page_size": page_size,
    }
    if from_amount is not None:
        params["from_amount"] = from_amount
    if to_amount is not None:
        params["to_amount"] = to_amount
    return await _get_json(
        f"{base_url.rstrip('/')}/v1/trx/movimientos-pagina", params, timeout,
        operation="trx.movimientos_pagina",
    )


async def fetch_trx_customer_address(
    *,
    base_url: str,
    customer_id: str,
    timeout: float = 10.0,
) -> str:
    """Direccion del cliente directo de Postgres (GET /v1/trx/customer-address).

    TXNR es quien consulta Postgres (ada_info_detail); el agente solo pide el
    resultado, sin pasar por co_pqrs_back_data. Fail-open: cualquier fallo o
    ausencia de dato devuelve "".
    """

    data = await _get_json(
        f"{base_url.rstrip('/')}/v1/trx/customer-address",
        {"customer_id": customer_id},
        timeout,
        operation="trx.customer_address",
        customer_id=customer_id,
    )
    return str((data or {}).get("customer_address") or "").strip()


async def fetch_trx_account_identity(
    *,
    base_url: str,
    customer_id: str,
    last_four: str,
    timeout: float = 2.0,
) -> dict[str, str]:
    """Obtiene account_id y personal_id directamente desde TXNR."""

    data = await _get_json(
        f"{base_url.rstrip('/')}/v1/trx/identity-by-card",
        {
            "customer_id": customer_id,
            "last_four": last_four,
            "origin_flag": "TDC",
        },
        timeout,
        operation="trx.identity_by_card",
        customer_id=customer_id,
    )
    return {
        "account_id": str((data or {}).get("account_id") or "").strip(),
        "personal_id": str((data or {}).get("personal_id") or "").strip(),
    }


async def detalle_trx(
    *, base_url: str, card_id: str, fecha: str, tx_id: str, origin_flag: str = "", timeout: float = 20.0
) -> dict | None:
    """operations ASO -> detalle + clasificacion de investigacion."""
    return await _get_json(
        f"{base_url.rstrip('/')}/v1/trx/detalle",
        {"card_id": card_id, "fecha": fecha, "tx_id": tx_id, "origin_flag": origin_flag},
        timeout,
        operation="trx.detalle",
    )


async def bloqueo_trx(
    *,
    base_url: str,
    card_id: str,
    tipo: str,
    autorizacion: dict | None = None,
    timeout: float = 20.0,
) -> dict | None:
    """Bloqueo de tarjeta: tipo = temporal | permanente.

    `autorizacion` lleva los datos del reto (challenge, authentication_state,
    device_id, profile_id, account_last_four). Es OBLIGATORIA en el bloqueo permanente:
    sin ella el back_trx rechaza la peticion sin llamar al ASO, porque ese POST
    cancela la tarjeta y pide reexpedicion.

    En el bloqueo temporal no se envia: ese camino solo hace el PATCH de apagado.
    """
    url = f"{base_url.rstrip('/')}/v1/trx/bloqueo"
    params = {"card_id": card_id, "tipo": tipo}
    for clave in ("challenge", "authentication_state", "device_id", "profile_id", "account_last_four"):
        valor = str((autorizacion or {}).get(clave) or "").strip()
        if valor:
            params[clave] = valor
    start = _time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url, params=params, headers=_correlation_headers()
            )
        response.raise_for_status()
        data = response.json()
        schedule_trace_event(
            event_type="http",
            operation="trx.bloqueo",
            outcome="ok",
            status_code=response.status_code,
            elapsed_ms=round((_time.perf_counter() - start) * 1000, 2),
            target=url,
            request_summary={"tipo": tipo},
            response_summary={"ok": bool((data or {}).get("ok")), "status": str((data or {}).get("status"))},
            tags=["trx", "agent", "trx.bloqueo"],
        )
        return data
    except Exception as exc:
        logger.warning("trx bloqueo failed url=%s (fail-open)", url)
        schedule_trace_event(
            event_type="http",
            operation="trx.bloqueo",
            outcome="error",
            elapsed_ms=round((_time.perf_counter() - start) * 1000, 2),
            target=url,
            request_summary={"tipo": tipo},
            error_type=type(exc).__name__,
            error_message=str(exc),
            tags=["trx", "agent", "trx.bloqueo"],
        )
        return None


async def subida_nivel_trx(
    *,
    base_url: str,
    card_id: str,
    personal_id: str,
    last_four: str = "",
    account_last_four: str = "",
    timeout: float = 15.0,
) -> dict | None:
    """Ejecuta el flujo de subida de nivel para autorizar el bloqueo.

    El endpoint /v1/trx/subida-nivel ejecuta internamente:
      1. Obtención/uso del contexto de autorización.
      2. Validación del usuario/dispositivo.
      3. Invocación de /cards/v2/operations.
      4. Generación del challenge.
    """

    url = f"{base_url.rstrip('/')}/v1/trx/subida-nivel"

    params = {
        "card_id": card_id,
        "personal_id": personal_id,
    }

    if last_four:
        params["last_four"] = last_four

    if account_last_four:
        params["account_last_four"] = account_last_four

    logger.info(
        "TXNR SUBIDA NIVEL START "
        "card_id=%s personal_id=%s last_four=%s account_last_four=%s",
        card_id,
        personal_id,
        last_four,
        account_last_four,
    )

    logger.info(
        "TXNR SUBIDA NIVEL REQUEST "
        "url=%s params=%s",
        url,
        {
            "card_id": card_id,
            "personal_id": personal_id,
            "last_four": last_four,
            "account_last_four": account_last_four,
        },
    )

    start = _time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:

            logger.info(
                "TXNR SUBIDA NIVEL HTTP POST START url=%s",
                url,
            )

            response = await client.post(
                url,
                params=params,
                headers=_correlation_headers(),
            )

        elapsed_ms = round(
            (_time.perf_counter() - start) * 1000,
            2,
        )

        logger.info(
            "TXNR SUBIDA NIVEL HTTP RESPONSE "
            "status_code=%s elapsed_ms=%s",
            response.status_code,
            elapsed_ms,
        )

        # Intentamos leer el JSON antes de validar funcionalmente
        try:
            data = response.json()
        except Exception:
            data = {}

        logger.info(
            "TXNR SUBIDA NIVEL RESPONSE DATA "
            "status=%s etapa=%s enviado=%s "
            "challenge=%s authentication_state=%s "
            "device_id=%s profile_id=%s",
            data.get("status"),
            data.get("etapa"),
            data.get("enviado"),
            bool(data.get("challenge")),
            data.get("authentication_state"),
            data.get("device_id"),
            data.get("profile_id"),
        )

        # HTTP distinto de 2xx
        if response.is_error:
            logger.error(
                "TXNR SUBIDA NIVEL HTTP ERROR "
                "status_code=%s response=%s",
                response.status_code,
                data,
            )

            response.raise_for_status()

        # ---------------------------------------------------------
        # VALIDACIÓN FUNCIONAL
        # ---------------------------------------------------------
        functional_status = str(
            data.get("status") or ""
        ).strip().lower()

        if functional_status != "ok":
            logger.error(
                "TXNR SUBIDA NIVEL FUNCTIONAL ERROR "
                "http_status=%s status=%s etapa=%s "
                "enviado=%s challenge=%s response=%s",
                response.status_code,
                data.get("status"),
                data.get("etapa"),
                data.get("enviado"),
                bool(data.get("challenge")),
                data,
            )

            schedule_trace_event(
                event_type="http",
                operation="trx.subida_nivel",
                outcome="functional_error",
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
                target=url,
                request_summary={
                    "card_id": card_id,
                    "last_four": last_four,
                    "account_last_four": account_last_four,
                },
                response_summary={
                    "status": data.get("status"),
                    "etapa": data.get("etapa"),
                    "enviado": data.get("enviado"),
                    "tiene_challenge": bool(
                        data.get("challenge")
                    ),
                },
                tags=["trx", "subida_nivel"],
            )

            return data

        # ---------------------------------------------------------
        # ÉXITO
        # ---------------------------------------------------------

        logger.info(
            "TXNR SUBIDA NIVEL SUCCESS "
            "card_id=%s last_four=%s account_last_four=%s "
            "challenge=%s authentication_state=%s",
            card_id,
            last_four,
            account_last_four,
            bool(data.get("challenge")),
            data.get("authentication_state"),
        )

        schedule_trace_event(
            event_type="http",
            operation="trx.subida_nivel",
            outcome="ok",
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            target=url,
            request_summary={
                "card_id": card_id,
                "last_four": last_four,
                "account_last_four": account_last_four,
            },
            response_summary={
                "status": data.get("status"),
                "etapa": data.get("etapa"),
                "enviado": data.get("enviado"),
                "tiene_challenge": bool(
                    data.get("challenge")
                ),
                "authentication_state": data.get(
                    "authentication_state"
                ),
                "device_id": data.get("device_id"),
                "profile_id": data.get("profile_id"),
            },
            tags=["trx", "subida_nivel"],
        )

        return data

    except httpx.HTTPStatusError as exc:

        elapsed_ms = round(
            (_time.perf_counter() - start) * 1000,
            2,
        )

        logger.error(
            "TXNR SUBIDA NIVEL HTTP EXCEPTION "
            "status_code=%s url=%s elapsed_ms=%s error=%s",
            exc.response.status_code if exc.response else None,
            url,
            elapsed_ms,
            exc,
        )

        schedule_trace_event(
            event_type="http",
            operation="trx.subida_nivel",
            outcome="http_error",
            status_code=(
                exc.response.status_code
                if exc.response
                else None
            ),
            elapsed_ms=elapsed_ms,
            target=url,
            error_type=type(exc).__name__,
            error_message=str(exc),
            tags=["trx", "subida_nivel"],
        )

        return None

    except Exception as exc:

        elapsed_ms = round(
            (_time.perf_counter() - start) * 1000,
            2,
        )

        logger.exception(
            "TXNR SUBIDA NIVEL EXCEPTION "
            "url=%s elapsed_ms=%s error=%s",
            url,
            elapsed_ms,
            exc,
        )

        schedule_trace_event(
            event_type="http",
            operation="trx.subida_nivel",
            outcome="error",
            elapsed_ms=elapsed_ms,
            target=url,
            error_type=type(exc).__name__,
            error_message=str(exc),
            tags=["trx", "subida_nivel"],
        )

        return None


async def subida_nivel_estado_trx(
    *,
    base_url: str,
    challenge: str,
    timeout: float = 15.0,
) -> dict | None:
    """
    Consulta el estado del reto de autorización y normaliza la respuesta
    del ASO a un contrato único para TXNR.

    Contrato normalizado de salida:

        {
            "aceptado": True | False,
            "status": "accepted" | "pending" | "rejected" | "expired" | "unknown",
            "challenge": "<challenge>"
        }

    El ASO puede responder con diferentes estructuras/valores y esta función
    se encarga de homologarlos.

    Ejemplos de respuestas ASO soportadas:

        {
            "data": {
                "status": {
                    "id": "accepted"
                }
            }
        }

        {
            "data": {
                "status": {
                    "id": "pending"
                }
            }
        }

        {
            "data": {
                "status": {
                    "id": "rejected"
                }
            }
        }

        {
            "aceptado": true
        }

        {
            "accepted": true
        }
    """

    if not base_url:
        logger.warning(
            "TXNR ASO ESTADO RETO sin base_url "
            "challenge=%s",
            challenge,
        )
        return None

    if not challenge:
        logger.warning(
            "TXNR ASO ESTADO RETO sin challenge",
        )
        return None

    # La consulta va por el servicio TXNR (maneja el tsec), no directo al ASO:
    # /security/v0/order-chanel/... es la ruta interna del servicio. UNA sola
    # consulta por pulsacion de "Continuar" -- sin sondeo ni espera.
    url = (
        f"{base_url.rstrip('/')}"
        f"/v1/trx/subida-nivel/estado"
        f"?challenge={challenge}"
    )

    start = _time.perf_counter()

    logger.info(
        "TXNR ASO ESTADO RETO REQUEST "
        "url=%s challenge=%s",
        url,
        challenge,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                url,
                headers=_correlation_headers(),
            )

        elapsed_ms = round(
            (_time.perf_counter() - start) * 1000,
            2,
        )

        response.raise_for_status()

        raw = response.json()

        logger.info(
            "TXNR ASO ESTADO RETO RAW RESPONSE "
            "challenge=%s status_code=%s response=%s",
            challenge,
            response.status_code,
            raw,
        )

        # ============================================================
        # 1. EXTRAER POSIBLES VALORES DEL ASO
        # ============================================================

        data = raw.get("data") or {}

        # Puede venir:
        #
        # data.status.id
        # data.status
        # status.id
        # status
        #
        status_obj = data.get("status")

        if isinstance(status_obj, dict):
            status_raw = status_obj.get("id")
        else:
            status_raw = status_obj

        if status_raw is None:
            # El sobre del servicio TXNR trae el estado del RETO en "estado";
            # su "status" de nivel superior es el resultado del request ("ok")
            # y NO debe confundirse con el estado del reto.
            status_raw = raw.get("estado")

        if status_raw is None:
            top_status = raw.get("status")

            if isinstance(top_status, dict):
                status_raw = top_status.get("id")
            else:
                status_raw = top_status

        # ============================================================
        # 2. HOMOLOGAR BOOLEANOS DE AUTORIZACIÓN
        # ============================================================

        accepted_raw = (
            raw.get("aceptado")
            if "aceptado" in raw
            else raw.get("accepted")
        )

        if accepted_raw is None:
            accepted_raw = data.get("aceptado")

        if accepted_raw is None:
            accepted_raw = data.get("accepted")

        aceptado = False

        if isinstance(accepted_raw, bool):
            aceptado = accepted_raw

        elif isinstance(accepted_raw, str):
            aceptado = accepted_raw.strip().lower() in {
                "true",
                "1",
                "yes",
                "si",
                "sí",
                "accepted",
                "approved",
                "autorizado",
                "aprobado",
            }

        elif isinstance(accepted_raw, (int, float)):
            aceptado = accepted_raw == 1

        # ============================================================
        # 3. NORMALIZAR STATUS
        # ============================================================

        status_normalizado = "unknown"

        if status_raw is not None:
            status_text = str(status_raw).strip().lower()

            # --------------------------------------------------------
            # ACEPTADO
            # --------------------------------------------------------
            if status_text in {
                "accepted",
                "accept",
                "approved",
                "approve",
                "authorized",
                "authorised",
                "autorizado",
                "autorizada",
                "aprobado",
                "aprobada",
            }:
                # OJO: "ok"/"success"/"completed" NO estan aqui a proposito:
                # son estados de sobre (la peticion funciono), no del reto.
                # Tratarlos como accepted autorizaba bloqueos con el reto
                # aun pending (bug cazado en el E2E de escenarios, 28/08).
                status_normalizado = "accepted"

            # --------------------------------------------------------
            # PENDIENTE
            # --------------------------------------------------------
            elif status_text in {
                "pending",
                "pendiente",
                "processing",
                "in_progress",
                "in-progress",
                "waiting",
                "wait",
                "created",
                "initiated",
            }:
                status_normalizado = "pending"

            # --------------------------------------------------------
            # RECHAZADO
            # --------------------------------------------------------
            elif status_text in {
                "rejected",
                "reject",
                "denied",
                "deny",
                "declined",
                "cancelled",
                "canceled",
                "refused",
                "unauthorized",
                "not_authorized",
                "not-authorized",
                "rechazado",
                "rechazada",
                "denegado",
                "denegada",
                "cancelado",
                "cancelada",
            }:
                status_normalizado = "rejected"

            # --------------------------------------------------------
            # VENCIDO
            # --------------------------------------------------------
            elif status_text in {
                "expired",
                "expire",
                "timeout",
                "timed_out",
                "timed-out",
                "vencido",
                "vencida",
            }:
                status_normalizado = "expired"

        # ============================================================
        if status_normalizado == "unknown" and bool(raw.get("pendiente")):
            # Forma del sobre del servicio: {"status":"ok","aceptado":false,
            # "pendiente":true} sin campo "estado" -- respaldo explicito.
            status_normalizado = "pending"

        # 4. EL BOOLEANO "ACEPTADO" TIENE PRIORIDAD
        # ============================================================

        if aceptado:
            status_normalizado = "accepted"

        # Si el status dice accepted/approved también consideramos
        # explícitamente aceptado aunque el ASO no mande el booleano.
        if status_normalizado == "accepted":
            aceptado = True

        # ============================================================
        # 5. ARMAR CONTRATO NORMALIZADO
        # ============================================================

        result = {
            "aceptado": aceptado,
            "status": status_normalizado,
            "challenge": challenge,
        }

        logger.info(
            "TXNR ASO ESTADO RETO NORMALIZED "
            "challenge=%s "
            "status_raw=%s "
            "status=%s "
            "aceptado=%s "
            "elapsed_ms=%s",
            challenge,
            status_raw,
            status_normalizado,
            aceptado,
            elapsed_ms,
        )

        # ============================================================
        # 6. TRACE
        # ============================================================

        schedule_trace_event(
            event_type="http",
            operation="trx.subida_nivel_estado",
            outcome=status_normalizado,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            target=url,
            request_summary={
                "challenge": challenge,
            },
            response_summary={
                "status": status_normalizado,
                "aceptado": aceptado,
                "challenge": challenge,
                "status_raw": status_raw,
            },
            tags=[
                "trx",
                "subida_nivel",
                "auth_status",
            ],
        )

        return result

    except httpx.HTTPStatusError as exc:
        elapsed_ms = round(
            (_time.perf_counter() - start) * 1000,
            2,
        )

        logger.warning(
            "TXNR ASO ESTADO RETO HTTP ERROR "
            "challenge=%s status_code=%s error=%s",
            challenge,
            exc.response.status_code,
            exc,
        )

        schedule_trace_event(
            event_type="http",
            operation="trx.subida_nivel_estado",
            outcome="error",
            status_code=exc.response.status_code,
            elapsed_ms=elapsed_ms,
            target=url,
            request_summary={
                "challenge": challenge,
            },
            error_type=type(exc).__name__,
            error_message=str(exc),
            tags=[
                "trx",
                "subida_nivel",
                "auth_status",
            ],
        )

        return None

    except Exception as exc:  # noqa: BLE001
        elapsed_ms = round(
            (_time.perf_counter() - start) * 1000,
            2,
        )

        logger.warning(
            "TXNR ASO ESTADO RETO ERROR "
            "challenge=%s error=%s",
            challenge,
            exc,
        )

        schedule_trace_event(
            event_type="http",
            operation="trx.subida_nivel_estado",
            outcome="error",
            elapsed_ms=elapsed_ms,
            target=url,
            request_summary={
                "challenge": challenge,
            },
            error_type=type(exc).__name__,
            error_message=str(exc),
            tags=[
                "trx",
                "subida_nivel",
                "auth_status",
            ],
        )

        return None