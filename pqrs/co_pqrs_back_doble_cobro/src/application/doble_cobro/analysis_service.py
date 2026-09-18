"""Application service para Doble Cobro.

Orquesta las tres decisiones del flujo:

1. Qué productos puede reportar el cliente (ASO financial-overview).
2. Si la fecha reportada es reclamable hoy (días hábiles + vigencia).
3. Qué grupos de cobros duplicados existen ese día (ASO operations).

El servicio NO persiste nada: el registro del caso vive en OpenSearch y lo
escribe el agente, igual que en transacción no reconocida.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from dateutil.relativedelta import relativedelta

from application.doble_cobro.movements import parse_operations
from domain.doble_cobro.business_days import business_days_between
from domain.doble_cobro.duplicate_finder import (
    filter_by_amount,
    find_duplicate_groups,
)
from domain.doble_cobro.models import (
    DobleCobroResult,
    DuplicateSearchRequest,
    ValidityRequest,
)
from infrastructure.core.config import load_doble_cobro_settings
from infrastructure.core.logger import get_logger
from infrastructure.persistence.doble_cobro_aso_client import DobleCobroAsoClient

logger = get_logger(__name__)

_ACTIVE_STATUSES = frozenset({"OPERATIVE", "ACTIVE", "ACTIVATED"})
_SUPPORTED_PRODUCT_TYPES = frozenset({"CARD", "ACCOUNT"})

# Familia elegida por el cliente -> subtipos ASO que la satisfacen.
#
# Las tarjetas DEBITO acompañan a las cuentas en ambas familias: el cobro
# duplicado pudo hacerse con la cuenta o con su tarjeta, y el cliente elige
# dónde lo vio. Aparecen bajo ahorro y bajo corriente porque el ASO no dice a
# qué cuenta pertenece cada tarjeta (`relatedContracts` viene vacío), así que
# no se puede acotar la lista sin inventarse el vínculo.
#
# Es además lo que activa la vigencia por franquicia: solo se evalúa cuando el
# producto elegido es una tarjeta, porque una cuenta no tiene marca.
_FAMILY_SUB_PRODUCTS: dict[str, frozenset[str]] = {
    "SAVING": frozenset({"SAVING", "SAVINGS", "SAVING_ACCOUNT", "DEBIT_CARD"}),
    "CHECKING": frozenset({"CHECKING", "CURRENT", "CHECKING_ACCOUNT", "DEBIT_CARD"}),
    "CREDIT_CARD": frozenset({"CREDIT_CARD"}),
}

_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y")


def parse_date(value: str) -> date | None:
    """Acepta DD/MM/AAAA y AAAA-MM-DD, que son los formatos que llegan del chat."""

    text = str(value or "").strip()
    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None


class DobleCobroAnalysisService:
    """Servicio de aplicación de Doble Cobro."""

    def __init__(
        self,
        aso_client: DobleCobroAsoClient | None = None,
    ) -> None:
        self._settings = load_doble_cobro_settings()
        self._aso_client = aso_client or DobleCobroAsoClient()

    # ------------------------------------------------------------------
    # 1. Productos
    # ------------------------------------------------------------------

    async def consultar_productos(
        self,
        *,
        customer_id: str,
        family: str = "",
    ) -> DobleCobroResult:
        """Productos activos del cliente, opcionalmente acotados a una familia."""

        customer_id = str(customer_id or "").strip()
        logger.info(
            "DOBLE_COBRO PRODUCTS REQUEST customer_id=%s family=%s",
            customer_id,
            family,
        )

        if not customer_id:
            return DobleCobroResult(
                status="error",
                step="consultar_productos",
                detail="customer_id vacío.",
                data={"products": []},
            )

        financial_overview = await self._aso_client.financial_overview(
            customer_id=customer_id
        )

        if financial_overview is None:
            logger.error(
                "DOBLE_COBRO PRODUCTS ASO UNAVAILABLE customer_id=%s", customer_id
            )
            return DobleCobroResult(
                status="unavailable",
                step="consultar_productos",
                detail="No fue posible consultar financial-overview.",
                data={"products": []},
            )

        products = self._normalize_products(financial_overview, family=family)

        logger.info(
            "DOBLE_COBRO PRODUCTS NORMALIZED customer_id=%s family=%s products=%s",
            customer_id,
            family,
            len(products),
        )

        if not products:
            return DobleCobroResult(
                status="not_found",
                step="consultar_productos",
                detail="No se encontraron productos activos para el cliente.",
                data={"products": []},
            )

        return DobleCobroResult(
            status="ok",
            step="consultar_productos",
            detail="Productos obtenidos correctamente.",
            data={"products": products},
        )

    # ------------------------------------------------------------------
    # 2. Vigencia de la fecha reportada
    # ------------------------------------------------------------------

    def validar_vigencia(self, request: ValidityRequest) -> DobleCobroResult:
        """Decide si la fecha reportada puede reclamarse hoy.

        Las tres reglas se evalúan en orden y la primera que falla manda:

        1. Conciliación con el comercio: 7 días hábiles, igual para cuentas y
           tarjetas. Antes de ese plazo el cobro todavía puede desaparecer solo.
        2. Plazo general de reporte: 6 meses.
        3. Vigencia de la franquicia: VISA 180 días, MASTER 120, y el plazo
           más largo para una marca no reconocida. Solo aplica cuando el
           producto es una tarjeta, porque una cuenta no tiene marca. Mismo
           criterio que transacción no reconocida: manda la marca, sin
           distinguir ámbito nacional/interoperable/internacional (no hay
           ningún campo del ASO que lo indique).
        """

        transaction_date = parse_date(request.transaction_date)
        if transaction_date is None:
            return DobleCobroResult(
                status="error",
                step="validar_vigencia",
                detail="Fecha no reconocida.",
                data={"outcome": "invalid_date"},
            )

        today = date.today()
        is_card = str(request.product_type or "").strip().upper() == "CARD"
        settlement_days = self._settings.settlement_days

        elapsed = business_days_between(transaction_date, today)
        data: dict[str, Any] = {
            "transaction_date": transaction_date.isoformat(),
            "settlement_days": settlement_days,
            "elapsed_business_days": elapsed,
        }

        if elapsed < settlement_days:
            return DobleCobroResult(
                status="ok",
                step="validar_vigencia",
                detail="La transacción sigue dentro de la ventana de conciliación.",
                data={**data, "outcome": "settlement_pending"},
            )

        oldest_allowed = today - relativedelta(months=self._settings.max_report_months)
        if transaction_date < oldest_allowed:
            return DobleCobroResult(
                status="ok",
                step="validar_vigencia",
                detail="La fecha supera el plazo general para reportar.",
                data={
                    **data,
                    "outcome": "report_window_expired",
                    "max_report_months": self._settings.max_report_months,
                },
            )

        franchise_days = self._franchise_days(request.card_brand) if is_card else 0
        if franchise_days and (today - transaction_date).days > franchise_days:
            return DobleCobroResult(
                status="ok",
                step="validar_vigencia",
                detail="La fecha supera la vigencia de la franquicia.",
                data={
                    **data,
                    "outcome": "franchise_expired",
                    "franchise_days": franchise_days,
                },
            )

        return DobleCobroResult(
            status="ok",
            step="validar_vigencia",
            detail="La fecha es reclamable.",
            data={**data, "outcome": "ok"},
        )

    def _franchise_days(self, card_brand: str) -> int:
        brand = str(card_brand or "").strip().upper()
        if brand == "VISA":
            return self._settings.visa_validity_days
        if brand in {"MASTER", "MASTERCARD"}:
            return self._settings.master_validity_days
        # Marca no reconocida (AMEX, Diners, o un dato incompleto): recibe el
        # plazo MAS LARGO, igual que en transacción no reconocida. Es una
        # decisión de negocio consciente: se prefiere admitir la reclamación y
        # que la revise el equipo, antes que rechazarla por un dato que el ASO
        # no supo clasificar.
        return self._settings.visa_validity_days

    # ------------------------------------------------------------------
    # 3. Grupos de cobros duplicados
    # ------------------------------------------------------------------

    async def buscar_grupos_duplicados(
        self,
        request: DuplicateSearchRequest,
    ) -> DobleCobroResult:
        """Movimientos del día dentro del rango del monto indicado.

        Devuelve TODOS los del rango (±``amount_tolerance``) para que el
        cliente elija cuáles forman el cobro duplicado. La agrupación se
        La agrupación se sigue calculando para dejar constancia en el log de
        cuántos duplicados detectó el servicio, pero no viaja en la respuesta:
        quien decide qué es duplicado es el cliente, y el agente valida su
        elección antes de registrarla.
        """

        transaction_date = parse_date(request.transaction_date)
        if transaction_date is None:
            return DobleCobroResult(
                status="error",
                step="buscar_grupos_duplicados",
                detail="Fecha no reconocida.",
                data={"groups": []},
            )

        payload = await self._aso_client.operations(
            operation_date=transaction_date.strftime("%Y%m%d"),
            card_id=request.card_id,
            account_id=request.account_id,
        )

        if payload is None:
            return DobleCobroResult(
                status="unavailable",
                step="buscar_grupos_duplicados",
                detail="No fue posible consultar los movimientos.",
                data={"groups": []},
            )

        movements = parse_operations(payload)
        candidates = filter_by_amount(
            movements,
            target_amount=request.amount,
            tolerance=self._settings.amount_tolerance,
        )
        groups = find_duplicate_groups(candidates)

        logger.info(
            "DOBLE_COBRO GROUPS customer_id=%s movements=%s candidates=%s groups=%s",
            request.customer_id,
            len(movements),
            len(candidates),
            len(groups),
        )

        data = {
            # TODOS los movimientos del rango, sin recortar: el cliente elige
            # cuáles forman el cobro duplicado y el agente valida su elección.
            "transactions": [
                self._serialize_movement(movement) for movement in candidates
            ],
            "movements_found": len(movements),
            "candidates_found": len(candidates),
        }

        if not candidates:
            return DobleCobroResult(
                status="not_found",
                step="buscar_grupos_duplicados",
                detail="No se encontraron movimientos con ese monto.",
                data=data,
            )

        return DobleCobroResult(
            status="ok",
            step="buscar_grupos_duplicados",
            detail="Movimientos del rango obtenidos.",
            data=data,
        )

    @staticmethod
    def _serialize_movement(movement: dict[str, Any]) -> dict[str, Any]:
        """Movimiento serializable: se descarta el ``datetime``.

        La fecha y la hora ya viajan como texto en ``date`` y ``time``.
        """

        return {
            key: value for key, value in movement.items() if key != "timestamp"
        }

    # ------------------------------------------------------------------
    # Normalización de productos
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_string(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _status(cls, contract: dict[str, Any]) -> str:
        status = contract.get("status") or {}
        value = cls._safe_string(status.get("id")).upper()
        if value:
            return value

        detail_status = (contract.get("detail") or {}).get("status") or {}
        return cls._safe_string(detail_status.get("id")).upper()

    @classmethod
    def _pan(cls, contract: dict[str, Any]) -> str:
        """PAN real: ``formats[].number`` con ``numberType`` PAN.

        En el ASO real ``contracts[].id`` es un token que ``operations`` rechaza;
        el simulador local sí usa el PAN como id, de ahí el respaldo.
        """

        for item in contract.get("formats") or []:
            if not isinstance(item, dict):
                continue
            number = cls._safe_string(item.get("number"))
            number_type = cls._safe_string(
                (item.get("numberType") or {}).get("id")
            ).upper()
            if number and number_type in {"", "PAN"}:
                return number

        if cls._safe_string((contract.get("numberType") or {}).get("id")).upper() == "PAN":
            return cls._safe_string(contract.get("id"))

        return ""

    @classmethod
    def _last_four(cls, contract: dict[str, Any]) -> str:
        for candidate in (
            cls._pan(contract),
            cls._safe_string(contract.get("number")),
            cls._safe_string(contract.get("id")),
        ):
            if candidate:
                return candidate[-4:]
        return ""

    @classmethod
    def _product_name(cls, contract: dict[str, Any]) -> str:
        product = contract.get("product") or {}
        return cls._safe_string(product.get("name")) or "Producto financiero"

    @classmethod
    def _currency(cls, contract: dict[str, Any]) -> str:
        for currency in contract.get("currencies") or []:
            if isinstance(currency, dict):
                value = cls._safe_string(currency.get("currency"))
                if value:
                    return value
        return ""

    @classmethod
    def _brand(cls, contract: dict[str, Any]) -> str:
        """Franquicia por BIN; el nombre del producto queda de respaldo.

        El primer dígito del PAN es la fuente fiable (4 = VISA, 5 y 2 = MASTER);
        un nombre como "TARJETA AQUA" no delata la marca.
        """

        digits = "".join(ch for ch in cls._pan(contract) if ch.isdigit())
        if len(digits) >= 8:
            if digits[0] == "4":
                return "VISA"
            if digits[0] in {"5", "2"}:
                return "MASTER"

        name = cls._product_name(contract).upper()
        if "VISA" in name:
            return "VISA"
        if "MASTER" in name:
            return "MASTER"
        return ""

    @classmethod
    def _matches_family(cls, contract: dict[str, Any], family: str) -> bool:
        """Filtra por la familia que el cliente eligió en el primer paso."""

        expected = _FAMILY_SUB_PRODUCTS.get(str(family or "").strip().upper())
        if expected is None:
            return True

        sub_product = cls._safe_string(
            (contract.get("subProductType") or {}).get("id")
        ).upper()
        return sub_product in expected

    @classmethod
    def _normalize_products(
        cls,
        payload: dict[str, Any],
        *,
        family: str = "",
    ) -> list[dict[str, Any]]:
        contracts = (payload.get("data") or {}).get("contracts") or []
        if not isinstance(contracts, list):
            return []

        products: list[dict[str, Any]] = []

        for contract in contracts:
            if not isinstance(contract, dict):
                continue

            product_type = cls._safe_string(contract.get("productType")).upper()
            if product_type not in _SUPPORTED_PRODUCT_TYPES:
                continue

            if cls._status(contract) not in _ACTIVE_STATUSES:
                continue

            if not cls._matches_family(contract, family):
                continue

            contract_id = cls._safe_string(contract.get("id"))
            if not contract_id:
                continue

            pan = cls._pan(contract) if product_type == "CARD" else ""
            last_four = cls._last_four(contract)

            products.append(
                {
                    "product_id": pan or contract_id,
                    "key_id": pan or contract_id,
                    "contract_id": contract_id,
                    "card_id": pan,
                    "last_four": last_four,
                    "last_four_pan_id": last_four if product_type == "CARD" else "",
                    "commercial_product_desc": cls._product_name(contract),
                    "product_desc": cls._product_name(contract),
                    "account_status_type_desc": cls._status(contract),
                    "product_type": product_type,
                    "sub_product_type": cls._safe_string(
                        (contract.get("subProductType") or {}).get("id")
                    ).upper(),
                    "card_brand": cls._brand(contract) if product_type == "CARD" else "",
                    "currency": cls._currency(contract),
                }
            )

        return products
