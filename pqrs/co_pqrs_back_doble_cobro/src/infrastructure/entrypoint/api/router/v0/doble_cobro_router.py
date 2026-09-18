"""v0 routes for Doble Cobro."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from application.doble_cobro.analysis_service import DobleCobroAnalysisService
from domain.doble_cobro.models import (
    DobleCobroResult,
    DuplicateSearchRequest,
    ValidityRequest,
)
from infrastructure.core.logger import get_logger, log_execution

logger = get_logger(__name__)

router = APIRouter(prefix="/v0/doble-cobro", tags=["doble_cobro"])

_analysis_service = DobleCobroAnalysisService()


@router.get(
    "/productos-activos",
    response_model=DobleCobroResult,
    status_code=status.HTTP_200_OK,
    summary="Productos activos del cliente (paso 3.4.0.1)",
)
@log_execution
async def productos_activos(
    customer_id: str = Query(..., min_length=1),
    family: str = Query("", description="SAVING, CHECKING o CREDIT_CARD."),
) -> DobleCobroResult:
    result = await _analysis_service.consultar_productos(
        customer_id=customer_id,
        family=family,
    )

    logger.info(
        "DOBLE_COBRO PRODUCTS HTTP RESPONSE customer_id=%s status=%s products=%s",
        customer_id,
        result.status,
        len(result.data.get("products", [])),
    )
    return result


@router.post(
    "/validar-vigencia",
    response_model=DobleCobroResult,
    status_code=status.HTTP_200_OK,
    summary="Días hábiles de conciliación + vigencia de la fecha (paso 3.4.0.3)",
)
@log_execution
async def validar_vigencia(request: ValidityRequest) -> DobleCobroResult:
    return _analysis_service.validar_vigencia(request)


@router.post(
    "/grupos-duplicados",
    response_model=DobleCobroResult,
    status_code=status.HTTP_200_OK,
    summary="Grupos de cobros duplicados del día (paso 3.4.0.6)",
)
@log_execution
async def grupos_duplicados(request: DuplicateSearchRequest) -> DobleCobroResult:
    return await _analysis_service.buscar_grupos_duplicados(request)
