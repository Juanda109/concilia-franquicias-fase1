"""Fire-and-forget HTTP client for the co_pqrs_back_data service."""

import time

import httpx

from infrastructure.core.logger import get_correlation_id, get_logger
from infrastructure.observability.trace_audit import schedule_trace_event

logger = get_logger(__name__)


def _correlation_headers() -> dict[str, str]:
    """Propagate the current conversation id so back_data logs correlate."""

    correlation_id = get_correlation_id()
    if correlation_id and correlation_id != "-":
        return {"X-Correlation-Id": correlation_id}
    return {}


async def fetch_customer_given_name(
    *,
    base_url: str,
    customer_id: str,
    timeout: float = 2.0,
) -> str:
    """Return the customer given names from co_pqrs_back_data (Postgres source).

    Best-effort and low-latency: uses a short timeout and swallows all errors,
    returning "" so the greeting never blocks on this call.
    """

    url = f"{base_url.rstrip('/')}/customer_name"
    params = {"customer_id": customer_id}
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                url, params=params, headers=_correlation_headers()
            )
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        response.raise_for_status()
        given_name = str(response.json().get("given_name", "") or "").strip()
        logger.info(
            "Back-data customer_name resolved customer_id=%s status=%s elapsed_ms=%s has_name=%s",
            customer_id,
            response.status_code,
            elapsed_ms,
            bool(given_name),
        )
        schedule_trace_event(
            event_type="back_data",
            operation="customer_name",
            outcome="ok",
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            target=url,
            customer_id=customer_id,
            response_summary={"has_name": bool(given_name)},
            tags=["back_data", "customer_name"],
        )
        return given_name
    except Exception as error:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.warning(
            "Back-data customer_name lookup failed customer_id=%s url=%s elapsed_ms=%s (greeting sin nombre)",
            customer_id,
            url,
            elapsed_ms,
        )
        schedule_trace_event(
            event_type="back_data",
            operation="customer_name",
            outcome="error",
            elapsed_ms=elapsed_ms,
            target=url,
            customer_id=customer_id,
            error_type=type(error).__name__,
            error_message=str(error),
            tags=["back_data", "customer_name"],
        )
        return ""


async def _trigger_back_data(
    *,
    operation: str,
    path: str,
    base_url: str,
    customer_id: str,
    workflow: str,
    run_id: str | None = None,
    extra_params: dict[str, str] | None = None,
) -> None:
    """POST a fire-and-forget pre-fetch to back_data and trace the outcome.

    All errors are swallowed after logging; a trace event (ok/error) is emitted
    so the agent -> back_data call is visible end-to-end in MinIO.
    """

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    params = {"customer_id": customer_id, "workflow": workflow}
    if run_id:
        params["run_id"] = run_id
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    logger.info(
        "Triggering back-data %s customer_id=%s url=%s", operation, customer_id, url
    )
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url, params=params, headers=_correlation_headers()
            )
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "Back-data %s accepted customer_id=%s status=%s elapsed_ms=%s",
            operation,
            customer_id,
            response.status_code,
            elapsed_ms,
        )
        schedule_trace_event(
            event_type="back_data",
            operation=operation,
            outcome="ok",
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            target=url,
            customer_id=customer_id,
            request_summary={"workflow": workflow},
            tags=["back_data", operation],
        )
    except Exception as error:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.exception(
            "Back-data %s notification failed customer_id=%s url=%s elapsed_ms=%s",
            operation,
            customer_id,
            url,
            elapsed_ms,
        )
        schedule_trace_event(
            event_type="back_data",
            operation=operation,
            outcome="error",
            elapsed_ms=elapsed_ms,
            target=url,
            customer_id=customer_id,
            request_summary={"workflow": workflow},
            error_type=type(error).__name__,
            error_message=str(error),
            tags=["back_data", operation],
        )


async def trigger_consultar(
    *, base_url: str, customer_id: str, workflow: str, run_id: str | None = None
) -> None:
    """
    Notify the back-data service to pre-load commercial and identity data
    for the given customer into the client-control table.

    This call is fire-and-forget: all errors are swallowed after logging.
    """

    await _trigger_back_data(
        operation="consultar",
        path="consultar",
        base_url=base_url,
        customer_id=customer_id,
        workflow=workflow,
        run_id=run_id,
    )


async def trigger_centrales_no_autorizo(
    *, base_url: str, customer_id: str, workflow: str, run_id: str | None = None
) -> None:
    """
    Notify the back-data service to record an unauthorized-query event
    for the given customer in the client-control table.

    This call is fire-and-forget: all errors are swallowed after logging.
    """

    await _trigger_back_data(
        operation="centrales_no_autorizo",
        path="centrales_no_autorizo",
        base_url=base_url,
        customer_id=customer_id,
        workflow=workflow,
        run_id=run_id,
    )


async def trigger_notificacion_centrales(
    *, base_url: str, customer_id: str, workflow: str, run_id: str | None = None
) -> None:
    """
    Notify the back-data service to resolve the notification-centrales case
    for the given customer in the client-control table.

    This call is fire-and-forget: all errors are swallowed after logging.
    """

    await _trigger_back_data(
        operation="notificacion_centrales",
        path="notificacion_centrales",
        base_url=base_url,
        customer_id=customer_id,
        workflow=workflow,
        run_id=run_id,
    )


async def trigger_notificacion_centrales_producto(
    *,
    base_url: str,
    customer_id: str,
    workflow: str,
    key_id: str,
    run_id: str | None = None,
) -> None:
    """
    FASE 2 del flujo 3: pedir a back_data el análisis de notificación del
    producto elegido (por su ``key_id``): adelanto de nómina / extracto / correo.

    This call is fire-and-forget: all errors are swallowed after logging.
    """

    await _trigger_back_data(
        operation="notificacion_centrales_producto",
        path="notificacion_centrales_producto",
        base_url=base_url,
        customer_id=customer_id,
        workflow=workflow,
        run_id=run_id,
        extra_params={"key_id": key_id},
    )
