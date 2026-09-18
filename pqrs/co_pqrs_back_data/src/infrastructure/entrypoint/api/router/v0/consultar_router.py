"""Customer query routes."""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from application.customer.consultar_service import (
    get_customer_display_name,
    process_centrales_no_autorizo_request,
    process_consultar_customer_request,
    process_notificacion_centrales_request,
    process_notificacion_producto_request,
)
from infrastructure.core.logger import get_correlation_id, log_execution
from infrastructure.observability.error_audit import schedule_error_report
from infrastructure.entrypoint.api.dependencies import (
    get_app_logger,
    get_commercial_info_client,
    get_customer_identity_repository,
    get_opensearch_client,
)
from infrastructure.persistence.commercial_info_client import CommercialInfoClient
from infrastructure.persistence.customer_identity_repository import CustomerIdentityRepository
from infrastructure.persistence.opensearch_client import OpenSearchClient

router = APIRouter(tags=["consultar"])


@router.get(
    "/customer_name",
    status_code=status.HTTP_200_OK,
    summary="Nombre de pila del cliente desde ada_info_detail (Postgres)",
)
@log_execution
async def customer_name(
    customer_id: str = Query(
        ...,
        min_length=1,
        description="Customer identifier to resolve the given names from Postgres.",
    ),
    logger: logging.Logger = Depends(get_app_logger),
    identity_repository: CustomerIdentityRepository = Depends(
        get_customer_identity_repository
    ),
) -> dict[str, object]:
    """Return the customer given names (fast, read-only, best-effort)."""

    logger.info("Received customer_name request customer_id=%s", customer_id)
    try:
        given_name = await asyncio.to_thread(
            get_customer_display_name,
            customer_id=customer_id,
            identity_repository=identity_repository,
        )
    except Exception as error:
        logger.exception(
            "customer_name lookup failed customer_id=%s", customer_id
        )
        schedule_error_report(
            error=error,
            source="customer_name",
            extra_context={
                "customer_id": customer_id,
                "operation": "customer_name",
            },
        )
        given_name = ""

    return {
        "customer_id": customer_id,
        "given_name": given_name,
        "found": bool(given_name),
    }


@router.post(
    "/consultar",
    status_code=status.HTTP_200_OK,
    summary="Consultar customer data",
)
@log_execution
async def consultar(
    background_tasks: BackgroundTasks,
    customer_id: str = Query(
        ...,
        min_length=1,
        description="Customer identifier to query in the CSV data source.",
    ),
    workflow: str = Query(
        ...,
        min_length=1,
        description="Workflow identifier where the generated data will be stored.",
    ),
    run_id: str | None = Query(
        None,
        description="Correlation/run id from the agent to tag the control-table result.",
    ),
    logger: logging.Logger = Depends(get_app_logger),
    identity_repository: CustomerIdentityRepository = Depends(
        get_customer_identity_repository
    ),
    embargo_repository: CustomerIdentityRepository = Depends(
        get_customer_identity_repository
    ),
    commercial_info_client: CommercialInfoClient = Depends(get_commercial_info_client),
    opensearch_client: OpenSearchClient = Depends(get_opensearch_client),
) -> dict[str, str]:
    """Accept the request and process the customer data asynchronously."""

    logger.info(
        "Received consultar request customer_id=%s workflow=%s",
        customer_id,
        workflow,
    )
    background_tasks.add_task(
        process_consultar_customer_request,
        customer_id=customer_id,
        workflow=workflow,
        identity_repository=identity_repository,
        commercial_info_client=commercial_info_client,
        opensearch_client=opensearch_client,
        correlation_id=get_correlation_id(),
        run_id=run_id,
        embargo_repository=embargo_repository,
    )
    return {"status": "processing"}


@router.post(
    "/notificacion_centrales",
    status_code=status.HTTP_200_OK,
    summary="Procesar notificacion de centrales",
)
@log_execution
async def notificacion_centrales(
    background_tasks: BackgroundTasks,
    customer_id: str = Query(
        ...,
        min_length=1,
        description="Customer identifier to query in the data source.",
    ),
    workflow: str = Query(
        ...,
        min_length=1,
        description="Workflow identifier where the generated data will be stored.",
    ),
    run_id: str | None = Query(
        None,
        description="Correlation/run id from the agent to tag the control-table result.",
    ),
    logger: logging.Logger = Depends(get_app_logger),
    identity_repository: CustomerIdentityRepository = Depends(
        get_customer_identity_repository
    ),
    commercial_info_client: CommercialInfoClient = Depends(get_commercial_info_client),
    opensearch_client: OpenSearchClient = Depends(get_opensearch_client),
) -> dict[str, str]:
    """Accept the request and process central-risk findings asynchronously."""

    logger.info(
        "Received notificacion_centrales request customer_id=%s workflow=%s",
        customer_id,
        workflow,
    )
    background_tasks.add_task(
        process_notificacion_centrales_request,
        customer_id=customer_id,
        workflow=workflow,
        identity_repository=identity_repository,
        commercial_info_client=commercial_info_client,
        opensearch_client=opensearch_client,
        correlation_id=get_correlation_id(),
        run_id=run_id,
        embargo_repository=identity_repository,
    )
    return {"status": "processing"}


@router.post(
    "/notificacion_centrales_producto",
    status_code=status.HTTP_200_OK,
    summary="Analizar notificacion del producto elegido (fase 2)",
)
@log_execution
async def notificacion_centrales_producto(
    background_tasks: BackgroundTasks,
    customer_id: str = Query(
        ...,
        min_length=1,
        description="Customer identifier to query in the data source.",
    ),
    workflow: str = Query(
        ...,
        min_length=1,
        description="Workflow identifier where the generated data will be stored.",
    ),
    key_id: str = Query(
        ...,
        min_length=1,
        description="key_id del producto elegido por el cliente (fase 2).",
    ),
    run_id: str | None = Query(
        None,
        description="Correlation/run id from the agent to tag the control-table result.",
    ),
    logger: logging.Logger = Depends(get_app_logger),
    identity_repository: CustomerIdentityRepository = Depends(
        get_customer_identity_repository
    ),
    commercial_info_client: CommercialInfoClient = Depends(get_commercial_info_client),
    opensearch_client: OpenSearchClient = Depends(get_opensearch_client),
) -> dict[str, str]:
    """Accept the request and analyze the selected product (phase 2) asynchronously."""

    logger.info(
        "Received notificacion_centrales_producto request customer_id=%s workflow=%s key_id=%s",
        customer_id,
        workflow,
        key_id,
    )
    background_tasks.add_task(
        process_notificacion_producto_request,
        customer_id=customer_id,
        workflow=workflow,
        key_id=key_id,
        identity_repository=identity_repository,
        commercial_info_client=commercial_info_client,
        opensearch_client=opensearch_client,
        correlation_id=get_correlation_id(),
        run_id=run_id,
    )
    return {"status": "processing"}


@router.post(
    "/centrales_no_autorizo",
    status_code=status.HTTP_200_OK,
    summary="Procesar autorizacion de consulta en centrales",
)
@log_execution
async def centrales_no_autorizo(
    background_tasks: BackgroundTasks,
    customer_id: str = Query(
        ...,
        min_length=1,
        description="Customer identifier to query in the CSV data source.",
    ),
    workflow: str = Query(
        ...,
        min_length=1,
        description="Workflow identifier where the generated data will be stored.",
    ),
    run_id: str | None = Query(
        None,
        description="Correlation/run id from the agent to tag the control-table result.",
    ),
    logger: logging.Logger = Depends(get_app_logger),
    identity_repository: CustomerIdentityRepository = Depends(
        get_customer_identity_repository
    ),
    opensearch_client: OpenSearchClient = Depends(get_opensearch_client),
) -> dict[str, str]:
    """Accept the request and process central-risk authorization asynchronously."""

    logger.info(
        "Received centrales_no_autorizo request customer_id=%s workflow=%s",
        customer_id,
        workflow,
    )
    background_tasks.add_task(
        process_centrales_no_autorizo_request,
        customer_id=customer_id,
        workflow=workflow,
        identity_repository=identity_repository,
        opensearch_client=opensearch_client,
        correlation_id=get_correlation_id(),
        run_id=run_id,
    )
    return {"status": "processing"}
