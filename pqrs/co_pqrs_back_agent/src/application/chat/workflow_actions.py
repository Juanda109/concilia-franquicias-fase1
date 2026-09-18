"""Workflow action handlers used by guide flows."""

from __future__ import annotations

import calendar
import json
import os
import random
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
import yaml
from dateutil.relativedelta import relativedelta

from domain.conversation.models import Conversation, ConversationStatus
from domain.workflow.general_messages import load_general_messages
from domain.workflow.models import WorkflowStep
from infrastructure.core.config import load_env_constants
from infrastructure.core.logger import get_logger, log_execution

from application.chat.actions.dispatcher import (
    dispatch_workflow_action,
)

logger = get_logger(__name__)

_COMMERCIAL_INFO_BASE_PATH = (
    Path(__file__).resolve().parents[2] / "domain" / "workflow" / "guia_rapida"
)

_CENTRALES_RESPONSES_PATH = (
    Path(__file__).resolve().parents[2]
    / "domain"
    / "workflow"
    / "pqrs"
    / "centrales_de_riesgo"
    / "responses.yml"
)

_ADA_PRODUCT_DESC_METADATA: dict[str, dict[str, str]] = {
    "4310-AHO": {"product_type": "Cuenta de Ahorros", "product_group": "pasivo"},
    "4320-AHO": {"product_type": "Cuenta de Ahorros", "product_group": "pasivo"},
    "4330-CAB": {"product_type": "Cartera Bancaria", "product_group": "activo"},
    "4340-TDC": {"product_type": "Tarjeta de Credito", "product_group": "activo"},
    "4350-CAB": {"product_type": "Cartera Bancaria", "product_group": "activo"},
}

_DEFAULT_ADA_PRODUCT_METADATA: dict[str, str] = {
    "product_type": "Producto financiero",
    "product_group": "activo",
}

_PRODUCT_CODE_METADATA: dict[str, dict[str, str]] = {
    "01": {
        "product_type": "Cuenta Corriente",
        "product_group": "pasivo",
        "status": "activo",
    },
    "02": {
        "product_type": "Cuenta de Ahorros",
        "product_group": "pasivo",
        "status": "activo",
    },
    "40": {
        "product_type": "Tarjeta de Credito",
        "product_group": "activo",
        "status": "activo",
    },
    "45": {
        "product_type": "Credito Rotativo",
        "product_group": "activo",
        "status": "activo",
    },
    "50": {
        "product_type": "Credito",
        "product_group": "activo",
        "status": "activo",
    },
    "95": {
        "product_type": "Adelanto de Nomina",
        "product_group": "activo",
        "status": "activo",
    },
}

_DEFAULT_PRODUCT_METADATA = {
    "product_type": "Producto financiero",
    "product_group": "activo",
    "status": "activo",
}

_CARTERA_VENDIDA_CENTRALES_ID_MSGS = frozenset({3, 19})
_EMBARGO_VIGENTE_ID_MSGS = frozenset({12})
_DESEMBARGO_REGISTRADO_ID_MSGS = frozenset({11})
_SIN_EMBARGO_ID_MSGS = frozenset({1})
_EMBARGO_DESEMBARGOS_MAP_KEY = "centrales_embargo_desembargos_map"
_EMBARGO_REVIEW_MODE_KEY = "centrales_embargo_review_mode"


def _last4(key_id: str) -> str:
    """Return the last 4 characters of key_id, or 'XXXX' when shorter."""

    tail = str(key_id or "").strip()[-4:]
    return tail if tail else "XXXX"


def _last4_contrato(fuente: dict[str, Any]) -> str:
    """Ultimos 4 del CONTRATO, que es lo que el cliente reconoce.

    ``key_id`` es el numero de OBLIGACION con el que se cruza contra las
    centrales de riesgo, no un dato de cara al cliente. Para el contrato
    ``00130009005078159809`` vale ``77001``, asi que mostrabamos ``*7001``
    cuando la tarjeta del cliente termina en ``9809``. Estuvo asi desde el
    primer commit (09/06/2026) y el rediseno del formato del 23/07 no lo
    cambio, solo envolvio el mismo valor.

    Se cae a ``product_id``/``key_id`` a proposito: el origen ``mock`` no trae
    la columna ``contract_id``, y ahi es preferible el numero de obligacion a
    un ``XXXX``.

    ``key_id`` sigue siendo la clave de negocio para cruzar contra centrales y
    para identificar la opcion elegida: esta funcion solo decide que se PINTA.
    """

    contrato = str(fuente.get("contract_id") or "").strip()
    if contrato:
        return contrato[-4:]
    return _last4(str(fuente.get("product_id") or fuente.get("key_id") or ""))


def _fecha_ddmmaaaa(fecha: str) -> str:
    """ISO (AAAA-MM-DD) -> DD/MM/AAAA, el formato que el tablero pide al
    cliente en labels y confirmacion (H-03). Otros formatos, tal cual."""

    partes = fecha.strip().split("-")
    if len(partes) == 3 and all(p.isdigit() for p in partes) and len(partes[0]) == 4:
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    return fecha


def _build_notificacion_delivery_text(*, fecha: str, correo: str) -> str:
    """Render a readable delivery sentence for notification message 16."""

    clean_fecha = str(fecha or "").strip()
    clean_correo = str(correo or "").strip()

    if clean_fecha and clean_correo:
        return (
            f"Este documento te fue enviado el día {clean_fecha} "
            f"al correo electrónico: {clean_correo}."
        )

    if clean_fecha:
        return (
            f"Este documento te fue enviado el día {clean_fecha} "
            "a los canales de contacto registrados para tu producto."
        )

    if clean_correo:
        return (
            "Este documento te fue enviado al correo electrónico registrado: "
            f"{clean_correo}."
        )

    return (
        "Este documento te fue enviado a los canales de contacto registrados "
        "para tu producto."
    )


def _build_consulta_autorizada_detail_text(*, fecha: str) -> str:
    """Render a readable sentence for authorized-query message 14."""

    clean_fecha = str(fecha or "").strip()
    if clean_fecha:
        return (
            "Entiendo tu duda. Revisé tu caso y esa consulta ocurrió porque el "
            f"{clean_fecha} solicitaste o adquiriste un producto con nosotros."
        )

    return (
        "Entiendo tu duda. Revisé tu caso y esa consulta ocurrió porque "
        "solicitaste o adquiriste un producto con nosotros."
    )


def _format_date_ddmmyyyy(raw: str) -> str:
    """Best-effort format of a date string to DD/MM/YYYY (else return as-is)."""

    value = (raw or "").strip()
    if not value:
        return value
    try:
        from datetime import datetime

        return datetime.fromisoformat(value[:19]).strftime("%d/%m/%Y")
    except Exception:  # noqa: BLE001
        pass
    import re as _re

    match = _re.match(r"^(\d{4})-(\d{2})-(\d{2})", value)
    if match:
        return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"
    return value



def _build_consulta_autorizada_variables(
    source: dict[str, Any],
    *,
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build template variables for authorized-query message 14.

    Uses the product with the most recent contract_register_date resolved by
    back_data: fecha (DD/MM/YYYY), tipo (commercial_product_desc) and the last 4
    digits of contract_id.
    """

    fecha = _format_date_ddmmyyyy(str(source.get("fecha") or "").strip())
    tipo = str(
        source.get("tipo") or (base or {}).get("tipo") or "tu producto"
    ).strip()
    contract_id_last4 = str(source.get("contract_id_last4") or "").strip()
    return {
        **(base or {}),
        "fecha": fecha,
        "tipo": tipo,
        "contract_id_last4": contract_id_last4,
        "detalle_consulta_autorizada": _build_consulta_autorizada_detail_text(
            fecha=fecha
        ),
    }


def _build_notificacion_variables(
    source: dict[str, Any],
    *,
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build template variables for notification message 16."""

    fecha = str(source.get("fecha") or "").strip()
    # back_data (fase 2) devuelve "correo"; se tolera "user_email" por compatibilidad.
    correo = str(source.get("correo") or source.get("user_email") or "").strip()

    return {
        **(base or {}),
        "fecha": fecha,
        "correo": correo,
        "detalle_notificacion": _build_notificacion_delivery_text(
            fecha=fecha,
            correo=correo,
        ),
    }


def _normalize_back_data_payload(
    back_data: dict[str, Any],
) -> dict[str, Any]:
    """Support both flat and nested back-data payload shapes."""

    nested_data = back_data.get("data")
    if not isinstance(nested_data, dict):
        nested_data = {}

    flat_payload = {
        str(key): value for key, value in back_data.items() if key != "data"
    }
    return {**flat_payload, **nested_data}


class _SafeDict(dict):
    """dict subclass that leaves unresolved ``{placeholders}`` intact in format_map."""

    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def _resolve_centrales_variables(
    id_msg: int | str,
    *,
    hallazgo: dict[str, Any],
    entry: dict[str, Any],
    key_id: str,
) -> dict[str, str]:
    """Return the template variables required by the given id_msg.

    Add a new branch here whenever a new message key introduces additional
    placeholders beyond the shared ``tipo`` / ``key_id_last`` pair.
    Variables not yet available are omitted — _SafeDict leaves their
    {placeholder} intact in the rendered text.
    """

    key = str(id_msg)

    base: dict[str, str] = {
        "tipo": str(hallazgo.get("tipo") or "producto"),
        # Los mensajes dicen "terminado en {key_id_last}". El marcador
        # conserva el nombre para no tocar los 5 YAML, pero el valor es
        # el del CONTRATO, que es lo que el cliente reconoce.
        "key_id_last": _last4_contrato({**entry, "product_id": key_id}),
    }

    # No placeholders — simple messages or variants
    if key in ("2", "6", "7", "13", "15", "17", "22"):
        return {}

    # Only base (tipo + key_id_last)
    if key in ("1", "18"):
        return base

    # Reporte negativo (mora / sin castigo) con motivo — base + tipo_producto + motivo
    if key in ("4", "5"):
        valor = hallazgo.get("valor") or {}
        if not isinstance(valor, dict):
            valor = {}
        return {
            **base,
            "tipo_producto": str(
                valor.get("tipo_producto") or base.get("tipo") or "producto"
            ),
            "motivo_reporte": str(valor.get("motivo_reporte") or ""),
        }

    # Cartera vendida — comprador from valor dict or plain string
    if key in ("3", "19"):
        valor = hallazgo.get("valor") or {}
        if isinstance(valor, dict):
            comprador = str(valor.get("comprador") or "No disponible")
        else:
            comprador = str(valor or "No disponible")
        return {**base, "comprador": comprador}

    # Sin bloqueo con estado — status from valor
    if key in ("8",):
        return {**base, "status": str(hallazgo.get("valor") or "")}

    # Sin bloqueo con estado — only status (no product reference in template)
    if key in ("9",):
        return {"status": str(hallazgo.get("valor") or "")}

    # Embargo levantado — fecha + status
    if key in ("10",):
        valor = hallazgo.get("valor") or {}
        if isinstance(valor, dict):
            return {
                **base,
                "fecha": str(valor.get("fecha") or ""),
                "status": str(valor.get("status") or ""),
            }
        return base

    # Desembargos — full detail block for every lifted embargo on the contract.
    if key in ("11",):
        valor = hallazgo.get("valor") or []
        if isinstance(valor, dict):
            valor = [valor]
        if isinstance(valor, list) and valor:
            detalles_str = []
            status = ""
            for folio in valor:
                if not isinstance(folio, dict):
                    continue
                entidad = str(folio.get("nombre_entidad") or "No disponible")
                monto = _format_currency(folio.get("valor_pago"))
                oficio = str(folio.get("numero_oficio") or "No disponible")
                fecha_oficio = _format_date_ddmmyyyy(
                    str(folio.get("fecha_oficio") or "")
                ) or "No disponible"
                fecha_desembargo = _format_date_ddmmyyyy(
                    str(
                        folio.get("fecha_desembargo")
                        or folio.get("fecha")
                        or ""
                    )
                ) or "No disponible"
                if not status:
                    status = str(folio.get("status") or "")

                if any(
                    folio.get(field)
                    for field in (
                        "nombre_entidad",
                        "numero_oficio",
                        "valor_pago",
                        "fecha_oficio",
                    )
                ):
                    detalles_str.append(
                        f"**¿Quién lo solicitó?**: {entidad}\n"
                        f"**Monto**: {monto}\n"
                        f"**Referencia**: Oficio {oficio} del {fecha_oficio}\n"
                        f"**Fecha de desembargo**: {fecha_desembargo}"
                    )
                else:
                    # Compatibility with control-table entries persisted before
                    # desembargos started returning the complete folio list.
                    detalles_str.append(
                        f"**Fecha de desembargo**: {fecha_desembargo}"
                    )

            if detalles_str:
                return {
                    **base,
                    "detalles_desembargos": "\n\n".join(detalles_str),
                    "status": status,
                }
        return base

    # Embargo vigente — full detail block
    if key in ("12",):
        valor = hallazgo.get("valor") or []
        if isinstance(valor, dict):
            valor = [valor]
        if isinstance(valor, list) and valor:
            detalles_str = []
            entidades_unicas = []
            
            # Iteramos sobre todos los folios para armar el texto
            for folio in valor:
                entidad = str(folio.get("nombre_entidad") or "No disponible")
                monto = _format_currency(folio.get("valor_pago"))
                oficio = str(folio.get("numero_oficio") or "No disponible")
                fecha = str(folio.get("fecha_oficio") or "No disponible")
                
                # Guardamos entidades únicas para el mensaje de despedida
                if entidad != "No disponible" and entidad not in entidades_unicas:
                    entidades_unicas.append(entidad)
                
                detalles_str.append(
                    f"**¿Quién lo solicita?**: {entidad}\n"
                    f"**Monto**: {monto}\n"
                    f"**Referencia**: Oficio {oficio} del {fecha}"
                )

            # Unimos las entidades con " y/o " en caso de que un cliente tenga embargos de juzgados distintos
            entidades_formateadas = " y/o ".join(entidades_unicas) if entidades_unicas else "las entidades embargantes"

            return {
                **base,
                "detalles_embargos": "\n\n".join(detalles_str),
                "nombre_entidad": entidades_formateadas,
            }
        return base

    # Consulta autorizada — fecha only
    if key in ("14",):
        valor = hallazgo.get("valor") or {}
        if isinstance(valor, dict):
            return _build_consulta_autorizada_variables(valor, base=base)
        return _build_consulta_autorizada_variables({"fecha": valor}, base=base)

    # Notificación extracto — fecha + user_email
    if key in ("16",):
        valor = hallazgo.get("valor") or {}
        if isinstance(valor, dict):
            return _build_notificacion_variables(valor, base=base)
        return _build_notificacion_variables({}, base=base)

    # Cartera castigada / permanencia — incluye placeholders legacy y nuevos.
    if key in ("20", "21"):
        valor = hallazgo.get("valor") or {}
        if isinstance(valor, dict):
            tipo_producto = str(
                valor.get("tipo_producto") or base.get("tipo") or "producto"
            )
            motivo_reporte = str(valor.get("motivo_reporte") or "")
            dias_mora = str(valor.get("dias_mora") or "")
            mora_months_raw = valor.get("mora_months")
            permanencia_desc = ""

            try:
                mora_months = int(mora_months_raw or 0)
            except (ValueError, TypeError):
                mora_months = 0

            if mora_months > 0:
                permanencia_meses = min(mora_months * 2, 48)
                permanencia_desc = (
                    f"{permanencia_meses} meses"
                    if permanencia_meses < 48
                    else "4 años"
                )

            return {
                **base,
                "tipo_producto": tipo_producto,
                "motivo_reporte": motivo_reporte,
                "fecha_inicio_mora": str(valor.get("fecha_inicio_mora") or ""),
                "dias_mora": dias_mora,
                # Placeholders for newer template variants (id_msg 20/21)
                "product_type": tipo_producto,
                "last_four": base.get("key_id_last") or "",
                "motivo": motivo_reporte,
                "permanencia_desc": permanencia_desc,
                "fecha": str(valor.get("fecha_inicio_mora") or ""),
            }
        return base

    # Not yet mapped — return empty (text renders with placeholders intact)
    return {}


def _load_centrales_response(
    key: str,
    variables: dict[str, str] | None = None,
) -> tuple[str, dict[str, str] | None]:
    """Load a message by key from the centrales_de_riesgo responses.yml catalog.

    Supports two entry shapes:
    - ``text: ...``       → returned as-is.
    - ``variants: [...]`` → one variant is chosen at random.

    Variables are applied via ``_SafeDict.format_map`` so any placeholder
    without a matching variable is left intact (e.g. ``{fecha}`` stays
    as ``{fecha}``).  Use :func:`_resolve_centrales_variables` to build
    the variables dict from the raw back-data structures.

    Returns a tuple of (text, option) where option is a dict with ``key`` and
    ``label`` (the label carries the URL) or ``None`` when the entry has no option.
    """

    try:
        raw = yaml.safe_load(_CENTRALES_RESPONSES_PATH.read_text(encoding="utf-8"))
        # YAML parses bare numeric keys as int; normalise all keys to str so
        # callers can always pass a string key (e.g. "2", "13").
        messages: dict[str, Any] = {
            str(k): v for k, v in (raw.get("messages") or {}).items()
        }
        entry = messages.get(key, {})
        if "variants" in entry:
            text = str(random.choice(entry["variants"]).get("text", "") or "")
        else:
            text = str(entry.get("text", "") or "")
        if text:
            text = text.format_map(_SafeDict(variables or {}))
        option: dict[str, str] | None = entry.get("option") or None
        return text, option
    except Exception:
        logger.warning(
            "Failed to load centrales response key=%s path=%s",
            key,
            _CENTRALES_RESPONSES_PATH,
        )
        return "", None


@log_execution
def execute_workflow_action(
    *,
    conversation: Conversation,
    step: WorkflowStep,
) -> None:
    """
    Execute the technical action attached to the current workflow step.

    Args:
        conversation: Runtime conversation being updated.
        step: Current workflow step that may declare an action.
    """

    handled, _result = dispatch_workflow_action(
        conversation=conversation,
        step=step,
    )

    if handled:
        return

    logger.info(
        "Executing workflow action conversation_id=%s workflow=%s action=%s",
        conversation.conversation_id,
        conversation.workflow,
        step.action,
    )
    if not step.action:
        return

    if step.action == "consultar_productos_cliente":
        _load_customer_products(conversation)
        return

    if step.action == "consultar_productos_activos_trx":
        _load_trx_active_products_summary(conversation)
        return

    if step.action == "mostrar_productos_activos_trx":
        _load_trx_product_selector(conversation)
        return

    if step.action == "mostrar_movimientos_trx":
        _load_trx_movement_selector(conversation)
        return

    if step.action == "consultar_trx_producto_seleccionado":
        _load_selected_trx_transactions(conversation)
        return

    if step.action == "confirmar_movimiento_trx":
        _load_trx_movement_confirmation(conversation)
        return

    if step.action == "mostrar_bloqueo_temporal_trx":
        _load_trx_temporary_block_success(conversation)
        return

    if step.action == "mostrar_bloqueo_definitivo_trx":
        _load_trx_permanent_block_success(conversation)
        return

    if step.action == "mostrar_trx_no_reconocida":
        _load_trx_not_refunded(conversation)
        return

    if step.action == "mostrar_trx_reversada":
        _load_trx_reversed(conversation)
        return

    if step.action == "registrar_devolucion_trx":
        # Sobreescribe el texto estático del YAML con el valor parametrizable
        # de DIAS_HABILES_DEVOLUCION cuando la acción corre en el turn actual.
        from application.chat.chat_service import _trx_env
        try:
            dias_dev = int(_trx_env("DIAS_HABILES_DEVOLUCION", "10"))
        except (ValueError, TypeError):
            dias_dev = 10
        logger.info(
            "execute_workflow_action registrar_devolucion_trx conversation_id=%s dias_dev=%s "
            "dias_env=%s",
            conversation.conversation_id,
            dias_dev,
            _trx_env("DIAS_HABILES_DEVOLUCION", "NOT_FOUND"),
        )
        conversation.captured_data["dynamic_prompt_2.4.0.1.20"] = (
            "Validamos la información de tu solicitud y tu caso aplica "
            "para la devolución automática.\n\n"
            "Gestionaremos el abono de tu dinero y te enviaremos la confirmación "
            "a tu correo electrónico en un máximo de "
            f"{dias_dev} días hábiles. "
            "No necesitas realizar ningún trámite adicional."
        )
        return

    if step.action == "build_satisfaction_si_message":
        _load_satisfaction_si(conversation)
        return

    if step.action == "build_satisfaction_no_message":
        _load_satisfaction_no(conversation)
        return

    if step.action == "consultar_productos_consulta_sin_permiso":
        _load_products_consulta_sin_permiso(conversation)
        return

    if step.action == "consultar_centrales_producto_seleccionado":
        _load_selected_product_central_risk(conversation)
        return

    if step.action == "consultar_todos_productos_centrales":
        _load_all_products_central_risk(conversation)
        return

    if step.action == "consultar_productos_embargo_centrales":
        _load_embargo_products_centrales(conversation)
        return

    if step.action == "mostrar_productos_desembargo_centrales":
        _load_desembargo_products_centrales(conversation)
        return

    if step.action == "continuar_resultado_centrales":
        _continue_centrales_product_result(conversation)
        return

    if step.action == "consultar_productos_cartera_vendida_centrales":
        _load_all_products_central_risk(
            conversation,
            allowed_id_messages=_CARTERA_VENDIDA_CENTRALES_ID_MSGS,
            no_results_step="1.4.1.0.cartera_vendida.sin_resultados",
        )
        return

    if step.action == "consultar_todos_productos_centrales_sin_notificacion":
        _load_products_notificacion_centrales(conversation)
        return

    if step.action == "consultar_notificacion_producto_seleccionado":
        _load_notificacion_producto_seleccionado(conversation)
        return

    if step.action == "build_satisfaction_check_message":
        _load_satisfaction_check(conversation)
        return

    if step.action == "goto_centrales_de_riesgo":
        _goto_centrales_de_riesgo(conversation)
        return

    if step.action == "goto_extractos_bancarios":
        _goto_extractos_bancarios(conversation)
        return

    logger.info(
        "No workflow action handler configured conversation_id=%s action=%s",
        conversation.conversation_id,
        step.action,
    )


def _build_back_data_not_verified_message() -> str:
    """Safe message when the back-data (Postgres/ASO) result could NOT be verified.

    Used whenever ``back_data_result`` is absent because the back-data run
    errored, timed out or is stale. NEVER affirm a positive/negative outcome
    (that was the false "no tienes reportes" / "tienes productos activos" bug).
    """

    return (
        "En este momento no puedo validar el estado de tus productos en las centrales "
        "de riesgo. Por favor inténtalo más tarde o comunícate con nuestro equipo "
        "especializado al 601 401 0000."
    )


@log_execution
def _load_products_consulta_sin_permiso(conversation: Conversation) -> None:
    """
    Handle the 'consultaron mi informacion sin autorizacion' flow.

    When back_data_result is available (populated by the centrales_no_autorizo
    endpoint), iterates all validaciones and dispatches each hallazgo by id_msg
    using the shared responses.yml catalog — exactly like the other centrales
    paths.  Multiple messages are joined with a numbered list.

    Falls back to the legacy static messages when no back_data is present.
    """

    _error_msg = (
        "Lo siento, no pude consultar la informacion de tu consulta en este momento. "
        "Gracias por comunicarte con nosotros."
    )

    back_data_raw = conversation.captured_data.get("back_data_result")

    if not back_data_raw:
        logger.info(
            "consulta_sin_permiso: back_data NOT verified — safe message conversation_id=%s back_data_status=%s",
            conversation.conversation_id,
            conversation.captured_data.get("back_data_status"),
        )
        conversation.status = ConversationStatus.CLOSED
        conversation.captured_data["preserve_terminal_response"] = "true"
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            _build_back_data_not_verified_message()
        )
        return

    try:
        back_data = json.loads(back_data_raw)
    except Exception:
        logger.warning(
            "consulta_sin_permiso: failed to parse back_data conversation_id=%s",
            conversation.conversation_id,
        )
        conversation.status = ConversationStatus.CLOSED
        conversation.captured_data["preserve_terminal_response"] = "true"
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            _error_msg
        )
        return

    payload = _normalize_back_data_payload(back_data)
    validaciones: list[dict[str, Any]] = back_data.get("hallazgos", {}).get(
        "validaciones", []
    )

    if not validaciones:
        flat_id_msg = payload.get("id_msg")
        if flat_id_msg in (None, ""):
            flat_id_msg = payload.get("id")

        if flat_id_msg not in (None, ""):
            validaciones = [
                {
                    "key_id": str(payload.get("key_id") or ""),
                    "hallazgos": [
                        {
                            "id_msg": flat_id_msg,
                            "tipo": payload.get("tipo") or "producto",
                            "valor": payload,
                        }
                    ],
                }
            ]
            logger.info(
                "consulta_sin_permiso: synthesized flat back_data id_msg=%s conversation_id=%s",
                flat_id_msg,
                conversation.conversation_id,
            )

    logger.info(
        "consulta_sin_permiso: validaciones count=%s conversation_id=%s",
        len(validaciones),
        conversation.conversation_id,
    )

    rendered_messages: list[str] = []
    last_option: dict[str, str] | None = None

    for entry in validaciones:
        hallazgos_list: list[dict[str, Any]] = entry.get("hallazgos") or []
        key_id = str(entry.get("key_id") or "").strip()

        primary = next(
            (h for h in hallazgos_list if int(h.get("id_msg") or 0) not in (0,)),
            None,
        )
        if primary is None:
            continue

        id_msg = primary.get("id_msg")
        variables = _resolve_centrales_variables(
            id_msg,
            hallazgo=primary,
            entry=entry,
            key_id=key_id,
        )
        message, option = _load_centrales_response(str(id_msg), variables)
        if message:
            rendered_messages.append(message)
            logger.info(
                "consulta_sin_permiso: id_msg=%s key_id=%s conversation_id=%s",
                id_msg,
                key_id,
                conversation.conversation_id,
            )
        if option:
            last_option = option

    if not rendered_messages:
        logger.info(
            "consulta_sin_permiso: no id_msg messages — using static fallback conversation_id=%s",
            conversation.conversation_id,
        )
        pqr_message = (
            _build_consulta_sin_permiso_no_productos_message()
            if not validaciones
            else _build_consulta_sin_permiso_con_productos_message()
        )
        conversation.captured_data["satisfaction_context_message"] = pqr_message
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            pqr_message
        )
        # Marca este mensaje como formulario PQRS -> el router envía el botón
        # {key:"pqr", label:"Formulario PQR"} y al oprimirlo pasa a satisfacción.
        conversation.captured_data["centrales_riesgo_form_option"] = json.dumps(
            {"key": "pqr", "label": "Formulario PQR"}, ensure_ascii=False
        )
        return

    if len(rendered_messages) == 1:
        final_message = rendered_messages[0]
    else:
        parts = [f"{i + 1}. {msg}" for i, msg in enumerate(rendered_messages)]
        final_message = "\n\n".join(parts)

    conversation.captured_data["satisfaction_context_message"] = final_message
    conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
        final_message
    )

    if last_option:
        conversation.captured_data["centrales_riesgo_form_option"] = json.dumps(
            last_option, ensure_ascii=False
        )
    else:
        conversation.captured_data.pop("centrales_riesgo_form_option", None)


@log_execution
def _build_consulta_sin_permiso_no_productos_message() -> str:
    """
    Return one of two equivalent PQR escalation messages at random.

    Both messages direct the customer to the PQRS form for an unauthorized
    credit-inquiry complaint when no active products are found.
    """

    return (
        "Tu caso requiere una revisión a fondo por parte de nuestro equipo "
        "especializado. Para radicar tu solicitud, por favor completa el "
        "siguiente formulario. Así podremos analizar lo ocurrido con tu reporte "
        "y darte una respuesta oficial."
    )


@log_execution
def _build_satisfaction_combined_prompt(pqr_message: str) -> str:
    """
    Append a random satisfaction-check question and the two reply options
    to the provided PQR message so the full block fits in one dynamic_prompt.
    """

    questions = [
        "¿Te ha ayudado esta informacion con lo que necesitabas?",
        "¿Ha quedado clara tu duda con esta respuesta o necesitas algo mas?",
        "¿He resuelto tu consulta?",
    ]
    question = random.choice(questions)
    return (
        f"{pqr_message}\n\n"
        "---\n\n"
        f"{question}\n\n"
        "1. Si, me ayudo\n"
        "2. No, ver linea de atencion"
    )


@log_execution
def _load_satisfaction_si(conversation: Conversation) -> None:
    """Set the random goodbye message for the satisfaction-yes terminal step."""

    messages = [
        (
            "Que bueno que logramos resolverlo. Recuerda que estoy aqui para "
            "apoyarte siempre que necesites ayuda con tus productos BBVA. "
            "Hasta pronto."
        ),
        (
            "Me alegra haberte ayudado! Estare por aqui para lo que necesites "
            "con tus cuentas o inversiones. Que tengas un buen dia!"
        ),
    ]
    conversation.captured_data["preserve_terminal_response"] = "true"
    conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
        random.choice(messages)
    )


@log_execution
def _load_satisfaction_no(conversation: Conversation) -> None:
    """Set the random call-us message for the satisfaction-no terminal step."""

    messages = [
        (
            "Siento no haber podido resolver tu caso por este canal. Para "
            "revisar tu caso a fondo y darte una solucion, por favor contacta "
            "con nuestro equipo especializado al 601 401 0000."
        ),
        (
            "Lamento no tener la respuesta exacta por este medio. Para que "
            "podamos darte una solucion personalizada, llamanos al "
            "601 401 0000 y un especialista se encargara de todo."
        ),
    ]
    conversation.captured_data["preserve_terminal_response"] = "true"
    conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
        random.choice(messages)
    )


@log_execution
def _build_consulta_sin_permiso_con_productos_message() -> str:
    """
    Return one of two equivalent PQR escalation messages at random.

    Both messages direct the customer to the PQRS form for an unauthorized
    credit-inquiry complaint when the customer has active products.
    """

    return (
        "Tu caso requiere una revisión a fondo por parte de nuestro equipo "
        "especializado. Para radicar tu solicitud, por favor completa el "
        "siguiente formulario. Así podremos analizar lo ocurrido con tu reporte "
        "y darte una respuesta oficial."
    )


def _filter_centrales_validaciones(
    validaciones: list[dict[str, Any]],
    allowed_id_messages: frozenset[int],
) -> list[dict[str, Any]]:
    """Return copies of entries containing only findings for one sub-flow."""

    filtered_validaciones: list[dict[str, Any]] = []
    for entry in validaciones:
        matching_hallazgos = [
            hallazgo
            for hallazgo in (entry.get("hallazgos") or [])
            if int(hallazgo.get("id_msg") or 0) in allowed_id_messages
        ]
        if matching_hallazgos:
            filtered_validaciones.append({**entry, "hallazgos": matching_hallazgos})
    return filtered_validaciones


def _activate_centrales_product_selector(
    conversation: Conversation,
    validaciones: list[dict[str, Any]],
    *,
    selector_step: str = "1.4.1.1",
) -> None:
    """Populate the shared product selector with already-filtered findings."""

    enriched_products: list[dict[str, Any]] = []
    for entry in validaciones:
        key_id = str(entry.get("key_id") or "").strip()
        if not key_id:
            continue
        hallazgos_list: list[dict[str, Any]] = entry.get("hallazgos") or []
        state_dict: dict[str, Any] = {
            str(h.get("tipo", "")).strip(): h.get("valor", "")
            for h in hallazgos_list
            if h.get("tipo")
        }
        enriched_products.append(
            {
                "product_id": key_id,
                "contract_id": str(
                    (entry.get("card_id") or entry.get("contract_id")) or ""
                ).strip(),
                "commercial_product_desc": str(
                    entry.get("commercial_product_desc")
                    or entry.get("product_desc")
                    or "Producto financiero"
                ).strip()
                or "Producto financiero",
                "state_label": _build_state_label_from_back_data(state_dict),
                "state_dict": state_dict,
                "hallazgos": hallazgos_list,
            }
        )

    conversation.captured_data["centrales_riesgo_back_data_map"] = json.dumps(
        enriched_products, ensure_ascii=False
    )
    conversation.captured_data[f"dynamic_prompt_{selector_step}"] = (
        _build_product_selection_prompt_from_back_data(enriched_products)
    )
    conversation.captured_data[f"dynamic_option_labels_{selector_step}"] = json.dumps(
        [
            (
                "CONTRATO "
                f"{p.get('commercial_product_desc') or 'Producto financiero'} "
                f"*{_last4_contrato(p)}"
            )
            for p in enriched_products
        ],
        ensure_ascii=False,
    )
    conversation.current_step = selector_step
    conversation.status = ConversationStatus.ACTIVE


def _build_sin_embargos_message(validaciones: list[dict[str, Any]]) -> str:
    """Build the reassuring message for passive products without an active embargo."""

    products = []
    for entry in validaciones:
        product_type = str(
            entry.get("commercial_product_desc")
            or entry.get("product_desc")
            or "Producto financiero"
        ).strip() or "Producto financiero"
        contract_last4 = _last4_contrato(entry)
        products.append(f"• {product_type} terminado en {contract_last4}")

    return (
        "Revisé tu caso y encontré que la información reportada en las centrales "
        "de riesgo coincide con el estado actual de tus productos en el banco. "
        "Actualmente, **no presentan embargo vigente**:\n\n"
        f"{'\n'.join(products)}\n\n"
        "Quédate con la tranquilidad de que todo está en orden."
    )


@log_execution
def _load_embargo_products_centrales(conversation: Conversation) -> None:
    """Show current embargoes first and retain recorded releases for later."""

    error_message = (
        "En este momento no puedo validar el estado de tus productos en las centrales "
        "de riesgo. Por favor inténtalo más tarde o comunícate con nuestro equipo "
        "especializado al 601 401 0000."
    )
    raw = conversation.captured_data.get("back_data_result")
    if not raw:
        conversation.status = ConversationStatus.CLOSED
        conversation.captured_data["preserve_terminal_response"] = "true"
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            error_message
        )
        return
    try:
        payload = json.loads(raw)
    except Exception:
        conversation.status = ConversationStatus.CLOSED
        conversation.captured_data["preserve_terminal_response"] = "true"
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            error_message
        )
        return

    validaciones: list[dict[str, Any]] = payload.get("hallazgos", {}).get(
        "validaciones", []
    )
    embargos = _filter_centrales_validaciones(
        validaciones, _EMBARGO_VIGENTE_ID_MSGS
    )
    desembargos = _filter_centrales_validaciones(
        validaciones, _DESEMBARGO_REGISTRADO_ID_MSGS
    )
    sin_embargos = _filter_centrales_validaciones(
        validaciones, _SIN_EMBARGO_ID_MSGS
    )
    # id_msg=1 is also used by active products without any report. Only passive
    # products participate in the embargo comparison, so do not present an
    # active product as a no-embargo result. The hallazgo type fallback keeps
    # compatibility with records stored before origin_flag was published.
    sin_embargos = [
        entry
        for entry in sin_embargos
        if str(entry.get("origin_flag") or "").strip().upper() == "PASIVE"
        or any(
            str(hallazgo.get("tipo") or "").strip().casefold() == "embargada"
            for hallazgo in (entry.get("hallazgos") or [])
        )
    ]
    conversation.captured_data[_EMBARGO_REVIEW_MODE_KEY] = "embargo"
    if desembargos:
        conversation.captured_data[_EMBARGO_DESEMBARGOS_MAP_KEY] = json.dumps(
            desembargos, ensure_ascii=False
        )
    else:
        conversation.captured_data.pop(_EMBARGO_DESEMBARGOS_MAP_KEY, None)

    if embargos:
        _activate_centrales_product_selector(conversation, embargos)
        return
    if sin_embargos:
        sin_embargos_message = _build_sin_embargos_message(sin_embargos)
        if desembargos:
            conversation.current_step = "1.4.1.0.embargo.sin_embargos"
            conversation.captured_data[
                "dynamic_prompt_1.4.1.0.embargo.sin_embargos"
            ] = (
                f"{sin_embargos_message}\n\n"
                "Si quieres, también puedo revisar si tienes **desembargos "
                "registrados**. ¿Te gustaría consultarlos?"
            )
        else:
            conversation.current_step = "1.4.1.0.embargo.sin_embargos.sin_desembargos"
            conversation.captured_data[
                "dynamic_prompt_1.4.1.0.embargo.sin_embargos.sin_desembargos"
            ] = sin_embargos_message
        conversation.status = ConversationStatus.ACTIVE
        return
    if desembargos:
        conversation.current_step = "1.4.1.0.embargo.sin_embargos"
        conversation.status = ConversationStatus.ACTIVE
        return

    conversation.current_step = "1.4.1.0.embargo.sin_resultados"
    conversation.status = ConversationStatus.CLOSED


@log_execution
def _load_desembargo_products_centrales(conversation: Conversation) -> None:
    """Load the recorded releases only after the customer explicitly asks for them."""

    raw = conversation.captured_data.get(_EMBARGO_DESEMBARGOS_MAP_KEY)
    try:
        desembargos = json.loads(raw) if raw else []
    except Exception:
        desembargos = []
    if not desembargos:
        conversation.current_step = "1.4.1.0.embargo.sin_resultados"
        conversation.status = ConversationStatus.CLOSED
        return
    conversation.captured_data[_EMBARGO_REVIEW_MODE_KEY] = "desembargo"
    _activate_centrales_product_selector(conversation, desembargos)


@log_execution
def _continue_centrales_product_result(conversation: Conversation) -> None:
    """Offer recorded releases after an embargo response, otherwise continue normally."""

    is_embargo_first_pass = (
        conversation.flow_answers.get("tipo_inconveniente_centrales_de_riesgo")
        == "embargo_o_desembargo"
        and conversation.captured_data.get(_EMBARGO_REVIEW_MODE_KEY) != "desembargo"
    )
    if is_embargo_first_pass and conversation.captured_data.get(
        _EMBARGO_DESEMBARGOS_MAP_KEY
    ):
        conversation.current_step = "1.4.1.1.embargo.ofrecer_desembargos"
        conversation.status = ConversationStatus.ACTIVE
        return

    conversation.current_step = "satisfaction_check"
    conversation.status = ConversationStatus.ACTIVE
    _load_satisfaction_check(conversation)


@log_execution
def _load_all_products_central_risk(
    conversation: Conversation,
    *,
    allowed_id_messages: frozenset[int] | None = None,
    no_results_step: str | None = None,
) -> None:
    """
    Check all customer products in centrales de riesgo via the back-data
    control table (OpenSearch).

    - validaciones = [] or all entries have empty hallazgos → no negative
      reports → send positive message and close the conversation.
    - Any entry has non-empty hallazgos → found issues → keep conversation
      active so the user can continue to product selection (1.4.1.1).
    """

    _error_msg = (
        "En este momento no puedo validar el estado de tus productos en las centrales "
        "de riesgo. Por favor inténtalo más tarde o comunícate con nuestro equipo "
        "especializado al 601 401 0000."
    )

    back_data_raw = conversation.captured_data.get("back_data_result")
    if not back_data_raw:
        logger.warning(
            "No verified back_data_result for all-products central-risk check "
            "conversation_id=%s back_data_status=%s",
            conversation.conversation_id,
            conversation.captured_data.get("back_data_status"),
        )
        conversation.status = ConversationStatus.CLOSED
        conversation.captured_data["preserve_terminal_response"] = "true"
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            _error_msg
        )
        return

    try:
        back_data = json.loads(back_data_raw)
    except Exception:
        logger.warning(
            "Failed to parse back_data_result conversation_id=%s",
            conversation.conversation_id,
        )
        conversation.status = ConversationStatus.CLOSED
        conversation.captured_data["preserve_terminal_response"] = "true"
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            _error_msg
        )
        return

    validaciones: list[dict[str, Any]] = back_data.get("hallazgos", {}).get(
        "validaciones", []
    )

    if allowed_id_messages is not None:
        # Keep only the findings that belong to the selected sub-flow. Filtering
        # entries alone is insufficient: a product can have findings from more
        # than one sub-flow and the selected-product resolver uses the first one.
        validaciones = _filter_centrales_validaciones(
            validaciones, allowed_id_messages
        )
        if not validaciones:
            logger.info(
                "No matching central-risk products conversation_id=%s allowed_id_messages=%s",
                conversation.conversation_id,
                sorted(allowed_id_messages),
            )
            if no_results_step:
                conversation.current_step = no_results_step
            conversation.status = ConversationStatus.CLOSED
            return

    all_hallazgos = [
        h for entry in validaciones for h in (entry.get("hallazgos") or [])
    ]

    logger.info(
        "all_hallazgos count=%s ids=%s conversation_id=%s",
        len(all_hallazgos),
        [h.get("id_msg") for h in all_hallazgos],
        conversation.conversation_id,
    )

    # Compare as int to handle cases where id_msg arrives as string "1"
    all_ok = not all_hallazgos or all(
        int(h.get("id_msg") or 0) == 1 for h in all_hallazgos
    )

    if all_ok:
        logger.info(
            "All products have id_msg=1 — no negative reports conversation_id=%s",
            conversation.conversation_id,
        )
        message, _ = _load_centrales_response("2")
        conversation.captured_data["satisfaction_context_message"] = message
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            message
        )
        return

    logger.info(
        "Negative reports found for customer conversation_id=%s",
        conversation.conversation_id,
    )
    _activate_centrales_product_selector(conversation, validaciones)


@log_execution
def _load_products_notificacion_centrales(conversation: Conversation) -> None:
    """
    Handle the 'reporte negativo sin notificacion' flow (camino 3, step 1.4.1.3).

    The back-data service may return either a flat structure:
        {"caso": "...", "id_msg": 16}
    or a nested one:
        {"data": {"caso": "...", "id": 16}}

    Dispatches by the resolved payload id to responses.yml messages 16, 17, 18.
    Falls back to an error message when back_data_result is missing or unparseable.
    """

    _error_msg = _build_back_data_not_verified_message()

    back_data_raw = conversation.captured_data.get("back_data_result")

    if not back_data_raw:
        logger.info(
            "notificacion_centrales: back_data NOT verified — safe message conversation_id=%s back_data_status=%s",
            conversation.conversation_id,
            conversation.captured_data.get("back_data_status"),
        )
        conversation.status = ConversationStatus.CLOSED
        conversation.captured_data["preserve_terminal_response"] = "true"
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            _error_msg
        )
        return

    try:
        back_data = json.loads(back_data_raw)
    except Exception:
        logger.warning(
            "notificacion_centrales: failed to parse back_data conversation_id=%s",
            conversation.conversation_id,
        )
        conversation.status = ConversationStatus.CLOSED
        conversation.captured_data["preserve_terminal_response"] = "true"
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            _error_msg
        )
        return

    # FASE 1: back_data devuelve validaciones por producto (igual que /consultar).
    # Toleramos ambas formas: {"hallazgos":{"validaciones":[...]}} o {"validaciones":[...]}.
    _hz = back_data.get("hallazgos")
    if isinstance(_hz, dict):
        validaciones = _hz.get("validaciones", []) or []
    else:
        validaciones = back_data.get("validaciones", []) or []

    reported = [
        v
        for v in validaciones
        if any(int(h.get("id_msg") or 0) != 1 for h in (v.get("hallazgos") or []))
    ]

    if not reported:
        # SIN reporte negativo → mensaje 18 genérico → Continuar → satisfaction_check.
        message, _ = _load_centrales_response("18", {})
        if not message:
            message = (
                "¡Buenas noticias! No tienes reportes negativos en las centrales "
                "de riesgo asociados a tus productos."
            )
        conversation.captured_data["satisfaction_context_message"] = message
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            message
        )
        logger.info(
            "notificacion_centrales: sin reporte — mensaje genérico conversation_id=%s",
            conversation.conversation_id,
        )
        return

    # CON reporte → listar los productos reportados (reusa el selector del flujo 1)
    # y avanzar al paso de selección 1.4.1.3.0.
    enriched_products: list[dict[str, Any]] = []
    for entry in reported:
        key_id = str(entry.get("key_id") or "").strip()
        if not key_id:
            continue
        hallazgos_list: list[dict[str, Any]] = entry.get("hallazgos") or []
        state_dict: dict[str, Any] = {
            str(h.get("tipo", "")).strip(): h.get("valor", "")
            for h in hallazgos_list
            if h.get("tipo")
        }
        enriched_products.append(
            {
                "product_id": key_id,
                # El contrato es lo que se PINTA; key_id sigue siendo la clave
                # con la que se cruza contra centrales.
                "contract_id": str(entry.get("contract_id") or "").strip(),
                "state_label": _build_state_label_from_back_data(state_dict),
                "state_dict": state_dict,
                "hallazgos": hallazgos_list,
            }
        )

    if not enriched_products:
        conversation.status = ConversationStatus.CLOSED
        conversation.captured_data["preserve_terminal_response"] = "true"
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            _error_msg
        )
        return

    conversation.captured_data["centrales_riesgo_notif_map"] = json.dumps(
        enriched_products, ensure_ascii=False
    )
    conversation.captured_data["dynamic_prompt_1.4.1.3.0"] = (
        _build_product_selection_prompt_from_back_data(enriched_products)
    )
    conversation.captured_data["dynamic_option_labels_1.4.1.3.0"] = json.dumps(
        [f"*{_last4_contrato(p)}" for p in enriched_products],
        ensure_ascii=False,
    )
    conversation.current_step = "1.4.1.3.0"
    logger.info(
        "notificacion_centrales: %s productos reportados — paso de selección conversation_id=%s",
        len(enriched_products),
        conversation.conversation_id,
    )


@log_execution
def _goto_centrales_de_riesgo(conversation: Conversation) -> None:
    """
    Redirect the conversation to the start of the centrales-de-riesgo workflow.

    Called when a user answers "No" on a FAQ satisfaction_check_faq step,
    indicating they still need help and should be taken to the PQRS flow.
    """

    conversation.workflow = "centrales_de_riesgo"
    conversation.current_step = "1.4.1"
    conversation.status = ConversationStatus.ACTIVE
    conversation.flow_answers.clear()
    conversation.captured_data.pop("centrales_riesgo_form_option", None)
    conversation.captured_data.pop("workflow_entry_hint", None)


@log_execution
def _load_notificacion_producto_seleccionado(conversation: Conversation) -> None:
    """FASE 2 del flujo 3: renderiza el análisis del producto elegido.

    back_data /notificacion_centrales_producto dejó en ``back_data_result``:
      - id_msg 17 → formulario PQRS (Continuar → satisfaction_check en 1.4.1.3.1).
      - id_msg 16 → notificación por extracto (fecha + correo); se muestra el
        mensaje y se avanza al paso "¿te guío?" (1.4.1.3.2).
    """

    _error_msg = _build_back_data_not_verified_message()
    back_data_raw = conversation.captured_data.get("back_data_result")

    def _terminal_error() -> None:
        conversation.status = ConversationStatus.CLOSED
        conversation.captured_data["preserve_terminal_response"] = "true"
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            _error_msg
        )

    if not back_data_raw:
        logger.info(
            "notificacion_producto: back_data NOT verified conversation_id=%s status=%s",
            conversation.conversation_id,
            conversation.captured_data.get("back_data_status"),
        )
        _terminal_error()
        return

    try:
        back_data = json.loads(back_data_raw)
    except Exception:
        logger.warning(
            "notificacion_producto: failed to parse back_data conversation_id=%s",
            conversation.conversation_id,
        )
        _terminal_error()
        return

    payload = _normalize_back_data_payload(back_data)
    id_msg = payload.get("id_msg")
    if id_msg in (None, ""):
        id_msg = payload.get("id")

    key = str(id_msg)
    if key not in {"16", "17"}:
        logger.warning(
            "notificacion_producto: unexpected id_msg=%s conversation_id=%s",
            id_msg,
            conversation.conversation_id,
        )
        _terminal_error()
        return

    variables: dict[str, str] = {}
    if key == "16":
        variables = _build_notificacion_variables(payload)

    message, option = _load_centrales_response(key, variables)
    if not message:
        logger.warning(
            "notificacion_producto: no message for id_msg=%s conversation_id=%s",
            id_msg,
            conversation.conversation_id,
        )
        _terminal_error()
        return

    conversation.captured_data["satisfaction_context_message"] = message
    if option:
        conversation.captured_data["centrales_riesgo_form_option"] = json.dumps(
            option, ensure_ascii=False
        )
    else:
        conversation.captured_data.pop("centrales_riesgo_form_option", None)

    if key == "16":
        # Notificación por extracto → mostrar msg 16 y ofrecer la guía tras Continuar.
        conversation.captured_data["dynamic_prompt_1.4.1.3.2"] = message
        conversation.current_step = "1.4.1.3.2"
    else:
        # id 17 (PQRS) → Continuar → satisfaction_check (paso 1.4.1.3.1).
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            message
        )

    logger.info(
        "notificacion_producto: rendered id_msg=%s conversation_id=%s",
        id_msg,
        conversation.conversation_id,
    )


@log_execution
def _goto_extractos_bancarios(conversation: Conversation) -> None:
    """Redirige a la guía de extractos bancarios (hazlo_tu_mismo).

    Se llama cuando el cliente responde "Sí, ver guía" tras la notificación por
    extracto (msg 16) en el flujo 3.
    """

    conversation.workflow = "extractos_bancarios"
    conversation.current_step = "1"
    conversation.status = ConversationStatus.ACTIVE
    conversation.flow_answers.clear()
    conversation.captured_data.pop("centrales_riesgo_form_option", None)
    conversation.captured_data.pop("workflow_entry_hint", None)


@log_execution
def _route_to_no_products_satisfaction(conversation: Conversation) -> None:
    """Redirect to the satisfaction check when no products were found in ASO.

    Instead of rendering the product selector with no real options, the bot
    informs the customer that no reported products were found and routes the
    conversation to the shared ``satisfaction_check`` step to close gracefully.
    """

    logger.info(
        "No products found for customer — routing to satisfaction_check "
        "conversation_id=%s user_id=%s",
        conversation.conversation_id,
        conversation.user_id,
    )
    conversation.captured_data["satisfaction_context_message"] = (
        "No encontramos productos reportados a tu nombre para consultar."
    )
    conversation.current_step = "satisfaction_check"
    conversation.status = ConversationStatus.ACTIVE
    _load_satisfaction_check(conversation)


@log_execution
def _load_satisfaction_check(conversation: Conversation) -> None:
    """
    Build the satisfaction-check prompt for the shared ``satisfaction_check`` step.

    Reads ``satisfaction_context_message`` from captured_data (set by the calling
    flow), picks a random question from the general messages catalog, and renders
    the full block as ``dynamic_prompt_satisfaction_check``.
    """

    # Clear any pending form option from the previous centrales step so that
    # satisfaction_check always renders its own [si / no] options normally.
    conversation.captured_data.pop("centrales_riesgo_form_option", None)

    general_messages = load_general_messages()
    question = random.choice(general_messages.satisfaction_questions)

    # Mostrar SOLO la pregunta de satisfacción: no re-mostrar el mensaje anterior
    # (evita el duplicado en flujos de centrales) ni el separador "---" (que
    # aparecía como una línea suelta en los flujos de FAQ).
    prompt = question
    conversation.satisfaction_status = "ENTERED"
    conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = prompt


@log_execution
def _load_satisfaction_si(conversation: Conversation) -> None:
    """Terminal step when the customer confirms the information was helpful."""

    general_messages = load_general_messages()
    message = random.choice(general_messages.satisfaction_si_messages)
    conversation.status = ConversationStatus.CLOSED
    conversation.satisfaction_result = True
    conversation.captured_data["preserve_terminal_response"] = "true"
    conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = message


@log_execution
def _load_satisfaction_no(conversation: Conversation) -> None:
    """Terminal step when the customer indicates the information was not helpful."""

    general_messages = load_general_messages()
    message = random.choice(general_messages.satisfaction_no_messages)
    conversation.status = ConversationStatus.CLOSED
    conversation.satisfaction_result = False
    conversation.captured_data["preserve_terminal_response"] = "true"
    conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = message


@log_execution
def _route_trx_no_products_satisfaction(conversation: Conversation) -> None:
    """Close the trx branch gracefully when no active products are available."""

    conversation.captured_data["satisfaction_context_message"] = (
        "No encontramos productos activos asociados a tu caso para revisar transacciones."
    )
    conversation.current_step = "satisfaction_check"
    conversation.status = ConversationStatus.ACTIVE
    _load_satisfaction_check(conversation)


_TRX_MESSAGES_BY_ID: dict[int, str] = {
    201: (
        "No fue posible consultar los productos activos en este momento. "
        "Puedes intentar nuevamente más tarde."
    ),
    202: (
        "Encontré productos activos asociados a tu caso. Continúa para "
        "seleccionar el producto y revisar sus transacciones."
    ),
    203: (
        "No encontramos productos activos asociados a tu caso para revisar "
        "transacciones."
    ),
    204: (
        "Pude identificar el producto seleccionado, pero la fuente de "
        "transacciones aún no está configurada en este servicio."
    ),
    205: (
        "No fue posible identificar el producto seleccionado o no hay "
        "transacciones consultables por ahora."
    ),
    206: "Esta es la información de las transacciones consultadas.",
}


def _trx_message(id_message: int, default: str) -> str:
    return _TRX_MESSAGES_BY_ID.get(id_message, default)


def _build_trx_product_selection_prompt(products: list[dict[str, Any]]) -> str:
    """Cuerpo del selector de productos: UNA frase, sin listar los productos.

    Los productos van en los BOTONES (`_build_trx_product_option_labels`), no en
    el mensaje. Antes se listaban en ambos sitios y el cliente veia sus productos
    dos veces: una en el texto y otra en los botones justo debajo.

    Este es el mismo criterio que ya seguia el selector de movimientos
    (2.4.0.1.9): frase corta arriba, opciones en los botones.

    `products` se recibe aunque no se use: mantiene la firma estable para los
    llamadores y para los tests, y deja explicito que la fuente de los datos son
    las etiquetas.
    """

    # Copy del TABLERO (aplicado 21/08 a peticion de Fabian/Pablo).
    return "Selecciona la cuenta o tarjeta en la que aparece la compra que no reconoces:"


def _build_trx_product_option_labels(products: list[dict[str, Any]]) -> list[str]:
    """Etiquetas de los botones del selector: "Tipo •XXXX".

    Extraida del loader para poder probarla sola: con el copy del tablero el
    prompt ya no lista los productos (es una sola frase), asi que las garantias
    de PROCEDENCIA -los 4 digitos salen de last_four y nunca del contrato ni de
    un identificador- viven aqui, en las etiquetas. Mascara del tablero para el
    SELECTOR: un punto (la confirmacion usa *XXXX por decision de Fabian).
    """

    etiquetas: list[str] = []
    for product in products:
        tipo = str(
            product.get("commercial_product_desc")
            or product.get("product_desc")
            or "Producto financiero"
        ).strip() or "Producto financiero"
        ultimos = str(product.get("last_four") or "").strip()
        if ultimos:
            etiquetas.append(f"{tipo} \u2022{_last4(ultimos)}")
        else:
            # Sin last_four no se INVENTAN digitos: "XXXX" es un crudo
            # prohibido en pantalla (la regla de degradacion de siempre) y
            # unos digitos falsos serian peor. Se muestra solo el tipo.
            etiquetas.append(tipo)
    return etiquetas


def _normalize_trx_products(payload: dict[str, Any]) -> list[dict[str, Any]]:
    products = ((payload.get("data") or {}).get("products") or [])
    normalized: list[dict[str, Any]] = []
    for entry in products:
        product_id = str(
            entry.get("product_id")
            or entry.get("key_id")
            or (entry.get("card_id") or entry.get("contract_id"))
            or ""
        ).strip()
        if not product_id:
            continue
        normalized.append(
            {
                "product_id": product_id,
                "key_id": str(entry.get("key_id") or product_id).strip(),
                "contract_id": str((entry.get("card_id") or entry.get("contract_id")) or "").strip(),
                # "last_four" es la clave que publica el servicio;
                # "last_four_pan_id" es el nombre en la tabla ADA. Se
                # conservan ambas para que ningun consumidor caiga a
                # product_id (el contrato completo) por un desajuste de
                # nombres -- tercer caso del patron (products_map, H-08).
                "last_four": str(
                    entry.get("last_four")
                    or entry.get("last_four_pan_id")
                    or ""
                ).strip(),
                "last_four_pan_id": str(
                    entry.get("last_four_pan_id")
                    or entry.get("last_four")
                    or ""
                ).strip(),
                "commercial_product_desc": str(
                    entry.get("commercial_product_desc")
                    or entry.get("product_desc")
                    or "Producto financiero"
                ).strip()
                or "Producto financiero",
                "account_status_type_desc": str(
                    entry.get("account_status_type_desc") or ""
                ).strip(),
            }
        )
    return normalized


def _resolve_selected_trx_product(
    conversation: Conversation,
    products: list[dict[str, Any]],
) -> dict[str, Any] | None:
    selected_key = conversation.flow_answers.get("producto_trx_no_reconocida")
    if not selected_key:
        return None
    try:
        index = int(str(selected_key).split("_")[-1]) - 1
        return products[index]
    except Exception:
        return None


@log_execution
def _load_trx_active_products_summary(conversation: Conversation) -> None:
    """Render the active-products lookup summary for trx_no_reconocida."""

    raw = conversation.captured_data.get("trx_products_result")
    if not raw:
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            "No pude consultar tus productos activos en este momento. Si lo prefieres, continúa para intentar con otra validación o radicar tu solicitud."
        )
        return

    try:
        payload = json.loads(raw)
    except Exception:
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            "No pude interpretar la respuesta de productos activos en este momento."
        )
        return

    id_message = int(payload.get("id_message") or 0)

    products = _normalize_trx_products(payload)
    if not products:
        if id_message == 203:
            conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
                _trx_message(203, _TRX_MESSAGES_BY_ID[203])
            )
        _route_trx_no_products_satisfaction(conversation)
        return

    conversation.captured_data["trx_products_map"] = json.dumps(
        products,
        ensure_ascii=False,
    )
    conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
        _trx_message(202, _TRX_MESSAGES_BY_ID[202])
    )


@log_execution
def _load_trx_product_selector(conversation: Conversation) -> None:
    """Build the dynamic selector with the active products returned by trx."""

    raw = conversation.captured_data.get("trx_products_result")
    if not raw:
        _route_trx_no_products_satisfaction(conversation)
        return

    try:
        payload = json.loads(raw)
    except Exception:
        _route_trx_no_products_satisfaction(conversation)
        return

    products = _normalize_trx_products(payload)
    if not products:
        _route_trx_no_products_satisfaction(conversation)
        return

    conversation.captured_data["trx_products_map"] = json.dumps(
        products,
        ensure_ascii=False,
    )
    conversation.captured_data["dynamic_prompt_2.4.0.1.5"] = (
        _build_trx_product_selection_prompt(products)
    )
    conversation.captured_data["dynamic_option_labels_2.4.0.1.5"] = json.dumps(
        _build_trx_product_option_labels(products),
        ensure_ascii=False,
    )


@log_execution
def _load_selected_trx_transactions(conversation: Conversation) -> None:
    """Render the day's movements as single-select buttons at step 2.4.0.3.

    Frontend = botones de selección única + chat abierto. No hay "lista dinámica":
    son botones fijos (movimiento_1..3 + no_encuentro en el YAML) cuyas ETIQUETAS
    se rellenan aquí desde los movimientos que devolvió back_trx.
    """

    raw = conversation.captured_data.get("trx_transactions_result")
    movimientos: list[dict[str, Any]] = []
    if raw:
        try:
            payload = json.loads(raw)
            movimientos = ((payload.get("data") or {}).get("movimientos") or [])
        except Exception:
            movimientos = []

    if not movimientos:
        # Sin movimientos consultables: se ofrece el formulario PQR como salida.
        conversation.captured_data["centrales_riesgo_form_option"] = json.dumps(
            {"key": "pqr", "label": "Formulario PQR"}, ensure_ascii=False
        )
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            "No pude consultar los movimientos en este momento. Para que nuestro "
            "equipo especializado revise el caso, radica el formulario PQR."
        )
        return

    def _fmt_amount(value: Any) -> str:
        try:
            return "$" + f"{float(value):,.0f}".replace(",", ".")
        except (TypeError, ValueError):
            return str(value)

    labels: list[str] = []
    for mov in movimientos[:3]:
        desc = str(mov.get("description") or mov.get("descripcion") or "Movimiento")
        valor = _fmt_amount(
            mov.get("amount") if mov.get("amount") is not None else mov.get("valor")
        )
        fecha = str(mov.get("movement_date") or mov.get("fecha") or "")
        labels.append(f"{desc} — {valor} {fecha}".strip(" —"))

    # Solo agregamos el boton "No encuentro..." cuando hay 3 movimientos, para que
    # las etiquetas caigan en las llaves correctas (movimiento_1..3 + no_encuentro)
    # sin desalinear el ruteo (limitacion del override posicional del front).
    if len(labels) == 3:
        labels.append("No encuentro la transacción en este listado.")

    conversation.captured_data["trx_movimientos_map"] = json.dumps(
        movimientos[:3], ensure_ascii=False
    )
    conversation.captured_data["dynamic_option_labels_2.4.0.3"] = json.dumps(
        labels, ensure_ascii=False
    )
    conversation.captured_data["dynamic_prompt_2.4.0.3"] = (
        "Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces:"
    )


# Cuantos movimientos caben en el selector. Debe coincidir con las opciones
# movimiento_N del paso 2.4.0.1.9 en el YAML.
# Tope de movimientos que el selector muestra por fecha. Subido a 100
# Tamano de pagina del selector: el YAML declara 5 casillas de movimiento y el
# servicio (movimientos-pagina) rebana en ese tamano. Fuente unica en el agente.
_TRX_MOVS_POR_PAGINA = 5


@log_execution
def _load_trx_movement_selector(conversation: Conversation) -> None:
    """Botones de movimientos (2.4.0.1.9): pinta la PAGINA que el servicio ya rebano.

    Cambio 04/09 (contrato Fase 0, sabor A): la paginacion vive en el servicio
    (``/v1/trx/movimientos-pagina``). El agente ya NO trocea: ``trx_movimientos_result``
    guarda solo la pagina visible y la metadata (page/total/total_pages/has_prev/
    has_next) la fija el gate. Aqui solo se pinta y se emiten los botones de
    navegacion segun has_prev/has_next. La seleccion es posicional dentro de la
    pagina (movimiento_1..5 -> id del movimiento visible).
    """

    raw_movs = conversation.captured_data.get("trx_movimientos_result")
    movimientos: list[dict[str, Any]] = []
    if raw_movs:
        try:
            movimientos = (json.loads(raw_movs) or {}).get("movimientos") or []
        except Exception:
            movimientos = []

    def _fmt_amount(value: Any) -> str:
        try:
            return "$" + f"{float(value):,.0f}".replace(",", ".")
        except (TypeError, ValueError):
            return str(value)

    cd = conversation.captured_data

    def _int(key: str, default: int) -> int:
        try:
            return int(cd.get(key) or default)
        except (TypeError, ValueError):
            return default

    pagina = _int("trx_movs_pagina", 1)
    total = _int("trx_movs_total", len(movimientos))
    total_pages = _int("trx_movs_total_pages", 1)
    has_prev = cd.get("trx_movs_has_prev") == "1" or pagina > 1
    has_next = cd.get("trx_movs_has_next") == "1"

    labels: list[str] = []
    keys: list[str] = []
    for offset, mov in enumerate(movimientos[:_TRX_MOVS_POR_PAGINA]):
        indice = offset + 1  # POSICIONAL dentro de la pagina visible
        desc = str(mov.get("descripcion") or mov.get("description") or "Movimiento")
        valor = _fmt_amount(mov.get("valor") if mov.get("valor") is not None else mov.get("amount"))
        fecha = _fecha_ddmmaaaa(
            str(mov.get("fecha") or mov.get("movement_date") or "")
        )
        labels.append(f"{desc} — {valor} {fecha}".strip(" —"))
        keys.append(f"movimiento_{indice}")

    # Navegacion segun lo que dijo el servicio. "Anterior" antes que "Ver mas"
    # para que el orden de lectura sea natural.
    if has_prev:
        labels.append("Anterior")
        keys.append("anterior_movimientos")
    if has_next:
        labels.append("Ver más movimientos")
        keys.append("mas_movimientos")

    # "No encuentro..." va SIEMPRE. Con override de keys cada boton declara su
    # destino, asi que la salida deja de ser inalcanzable (H-02).
    labels.append("No encuentro la transacción en este listado.")
    keys.append("no_encuentro")

    cd["dynamic_option_labels_2.4.0.1.9"] = json.dumps(labels, ensure_ascii=False)
    cd["dynamic_option_keys_2.4.0.1.9"] = json.dumps(keys, ensure_ascii=False)

    # El cliente siempre sabe donde esta parado (H-14): tramo y pagina.
    prompt = (
        "Encontré estas transacciones en la fecha indicada. "
        "Selecciona la compra que no reconoces:"
    )
    if total > _TRX_MOVS_POR_PAGINA:
        inicio = (pagina - 1) * _TRX_MOVS_POR_PAGINA
        visibles = len(movimientos[:_TRX_MOVS_POR_PAGINA])
        fin = min(inicio + visibles, total)
        prompt += (
            f"\n\nTe muestro los movimientos {inicio + 1} a {fin} de {total} "
            f"(página {pagina} de {total_pages})."
        )
        if has_next:
            prompt += " Pulsa \"Ver más movimientos\" para seguir viendo."
        if has_prev:
            prompt += " Pulsa \"Anterior\" para volver."
    cd["dynamic_prompt_2.4.0.1.9"] = prompt


def _fmt_amount(value: Any) -> str:
    try:
        return "$" + f"{float(value):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value)


@log_execution
def _load_trx_movement_confirmation(
    conversation: Conversation,
) -> None:
    """Render de la confirmación del movimiento seleccionado (2.4.0.1.11)."""

    mov = _get_selected_trx_movement(conversation)

    if not mov:
        conversation.captured_data[
            "dynamic_prompt_2.4.0.1.11"
        ] = (
            "Confirma los datos de la compra seleccionada. "
            "¿Es la transacción que deseas reportar?"
        )
        return

    # Prefer detailed description from trx_detalle_result (if present),
    # otherwise fall back to the movement description.
    desc = ""
    detalle_raw = conversation.captured_data.get("trx_detalle_result")
    # CONSISTENCIA (Fabian, 27/08): la confirmacion repite lo que el cliente
    # VIO Y PULSO en el listado (mov.descripcion, que ya trae el comercio del
    # 5o bloque de observations). descProvision queda de respaldo: en el ASO
    # real trae un ESTADO ("ACEPTADA"), no una descripcion.
    desc = str(mov.get("descripcion") or mov.get("description") or "").strip()
    if not desc and detalle_raw:
        try:
            detalle = json.loads(detalle_raw) or {}
            desc = str(detalle.get("descProvision") or "").strip()
        except Exception:
            desc = ""
    if not desc:
        desc = "Movimiento"

    valor = _fmt_amount(
        mov.get("valor") if mov.get("valor") is not None else mov.get("amount")
    )

    fecha = _fecha_ddmmaaaa(
        str(
            mov.get("fecha")
            or mov.get("movement_date")
            or ""
        )
    )

    # Use the dedicated helper you added to resolve the selected product's
    # last four digits (centralized logic lives in `_get_selected_trx_last4`).
    last4 = _get_selected_trx_last4(conversation)

    fecha = _fecha_ddmmaaaa(fecha)
    detalle = (
        "Confirma los datos de la compra seleccionada.\n\n"
        # El tablero pinta la primera vineta con el dato CRUDO, sin la
        # etiqueta "Descripcion:".
        f"• {desc}\n"
        f"• Valor: {valor}\n"
        f"• Fecha: {fecha}\n"
    )

    if last4:
        # El tablero pide "[Producto] terminado en...", donde [Producto] es el
        # TIPO (Tarjeta de Credito, Cuenta de Ahorros...), no la palabra
        # literal: antes salia "Producto terminado en *4444" en toda captura.
        producto_sel = _get_selected_trx_product(conversation) or {}
        tipo_producto = str(
            producto_sel.get("commercial_product_desc")
            or producto_sel.get("product_desc")
            or "Producto"
        ).strip() or "Producto"
        detalle += (
            f"• {tipo_producto} terminado en *{last4}\n"
        )

    detalle += (
        "\n¿Es la transacción que deseas reportar?"
    )

    conversation.captured_data[
        "dynamic_prompt_2.4.0.1.11"
    ] = detalle


def _get_selected_trx_product(
    conversation: Conversation,
) -> dict[str, Any] | None:
    """Return the product selected by the user in TXNR."""

    raw = conversation.captured_data.get(
        "trx_products_result"
    )

    selected = conversation.flow_answers.get(
        "producto_trx_no_reconocida"
    )

    logger.info(
        "TXR PRODUCT DEBUG raw_exists=%s selected=%s",
        bool(raw),
        selected,
    )

    if not raw or not selected:
        return None

    try:
        products = (
            json.loads(raw) or {}
        ).get("data", {}).get("products") or []

        products = (
            json.loads(raw) or {}
        ).get("data", {}).get("products") or []

        idx = int(str(selected).split("_")[-1]) - 1

        logger.info(
            "TXR PRODUCT DEBUG selected=%s idx=%s",
            selected,
            idx,
        )

        if 0 <= idx < len(products):
            logger.info(
                "TXR PRODUCT DEBUG selected_product=%s last_four_pan_id=%s",
                products[idx],
                products[idx].get("last_four_pan_id"),
            )
            return products[idx]

    except (TypeError, ValueError, json.JSONDecodeError):
        return None

    return None


def _get_selected_trx_last4(
    conversation: Conversation,
) -> str:
    """Return the last four digits of the selected TXNR product."""

    product = _get_selected_trx_product(conversation)

    if not product:
        logger.warning(
            "TXR LAST4 DEBUG selected product not found"
        )
        return ""
    
    # "last_four" PRIMERO: es la clave que publica el servicio y, tras el
    # gate .4, la que lleva los ultimos 4 del PAN de financial-overview
    # -- la fuente que pidio Fabian. "last_four_pan_id" es el nombre de la
    # columna en ADA y puede traer un valor distinto (cliente J: ADA 9999
    # vs PAN 4321). Con la precedencia al reves el cliente veria los
    # digitos de ADA en la confirmacion: es exactamente H-08.
    last4 = _last4(
        str(
            product.get("last_four")
            or product.get("last_four_pan_id")
            or ""
        )
    )

    logger.info(
        "TXR LAST4 DEBUG last_four_pan_id=%s resolved_last4=%s",
        product.get("last_four_pan_id"),
        last4,
    )

    return last4


def _get_selected_trx_movement(conversation) -> dict:
    """
    Return the transaction selected by the user in the TXNR flow.

    Supports both Fase-1 keys (trx_transactions_result /
    transaccion_trx_no_reconocida) and Fase-2 keys
    (trx_movimientos_result / trx_movimiento_seleccionado).
    """

    # Fase 2 key takes priority; fall back to Fase 1 key.
    raw_movements = (
        conversation.captured_data.get("trx_movimientos_result")
        or conversation.captured_data.get("trx_transactions_result")
    )

    selected = (
        conversation.flow_answers.get("trx_movimiento_seleccionado")
        or conversation.flow_answers.get("transaccion_trx_no_reconocida")
    )

    if not raw_movements or not selected:
        return {}

    try:
        payload = json.loads(raw_movements)

        # Fase 2 uses {"movimientos": [...]}
        # Fase 1 uses {"data": [...]} or {"transactions": [...]}
        movements = (
            payload.get("movimientos")
            or payload.get("data")
            or payload.get("transactions")
            or []
        )

        index = int(str(selected).split("_")[-1]) - 1

        if 0 <= index < len(movements):
            return movements[index]

    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    return {}


@log_execution
def _load_trx_temporary_block_success(
    conversation: Conversation,
) -> None:
    """Render successful temporary card block (2.4.0.1.16.2)."""

    last4 = _get_selected_trx_last4(conversation)

    if last4:
        prompt = (
            f"Listo. Tu tarjeta terminada en •{last4} "
            "quedó apagada temporalmente.\n\n"
            "Podrás volver a encenderla desde tus canales digitales."
        )
    else:
        prompt = (
            "Listo. Tu tarjeta quedó apagada temporalmente.\n\n"
            "Podrás volver a encenderla desde tus canales digitales."
        )

    conversation.captured_data[
        "dynamic_prompt_2.4.0.1.16.3"
    ] = prompt


@log_execution
def _load_trx_not_refunded(
    conversation: Conversation,
) -> None:
    """Render TXNR investigation result without refund (2.4.0.1.19.1)."""

    mov = _get_selected_trx_movement(conversation)

    if not mov:
        conversation.captured_data[
            "dynamic_prompt_2.4.0.1.19.1"
        ] = (
            "Tras analizar los registros del caso, "
            "no fue posible identificar la información "
            "de la transacción seleccionada."
        )
        return

    desc = str(
        mov.get("descripcion")
        or mov.get("description")
        or "Movimiento"
    )

    valor = _fmt_amount(
        mov.get("valor")
        if mov.get("valor") is not None
        else mov.get("amount")
    )

    prompt = (
        f"Revisamos la investigación de la transacción "
        f"{desc} por {valor}.\n\n"
        "Tras analizar los registros del caso, identificamos que "
        "la transacción se realizó de forma presencial con la "
        "lectura física del chip de tu tarjeta y la digitación "
        "de tu clave secreta en el datáfono del establecimiento.\n\n"
        "Conforme al marco del Régimen de Protección al Consumidor "
        "Financiero, cuando una operación cumple con la totalidad "
        "de los mecanismos de autenticación presenciales y los "
        "sistemas del banco no presentan fallas operativas, "
        "la compra se valida como autorizada.\n\n"
        "Por esta razón, no es posible realizar la devolución "
        "del dinero."
    )

    conversation.captured_data[
        "dynamic_prompt_2.4.0.1.19.1"
    ] = prompt


@log_execution
def _load_trx_reversed(
    conversation: Conversation,
) -> None:
    """Render reversed TXNR transaction (2.4.0.1.19.2)."""

    mov = _get_selected_trx_movement(conversation)

    product = _get_selected_trx_product(conversation)
    product_name = "tu producto"
    if product:
        product_name = str(
            product.get("commercial_product_desc")
            or product.get("product_desc")
            or product.get("contract_type_desc")
            or product.get("display_name")
            or "tu producto"
        ).strip()

    if not mov:
        conversation.captured_data[
            "dynamic_prompt_2.4.0.1.19.2"
        ] = (
            f"Te confirmamos que la compra seleccionada "
            f"ya fue devuelta a tu {product_name}."
        )
        return

    valor = _fmt_amount(
        mov.get("valor")
        if mov.get("valor") is not None
        else mov.get("amount")
    )

    fecha_trx = _format_date_ddmmyyyy(
        str(mov.get("fecha") or mov.get("movement_date") or "")
    )

    # dateReverse comes from the raw operation stored in trx_detalle_result.
    fecha_reverso = ""
    try:
        detalle_raw = conversation.captured_data.get("trx_detalle_result")
        if detalle_raw:
            detalle = json.loads(detalle_raw)
            fecha_reverso = _format_date_ddmmyyyy(
                str(detalle.get("dateReverse") or "")
            )
    except Exception:
        pass

    detalle_lines = f"• Transacción: {valor} el {fecha_trx}" if fecha_trx else f"• Transacción: {valor}"
    if fecha_reverso:
        detalle_lines += f"\n\n• Monto devuelto: {valor} el {fecha_reverso}"

    prompt = (
        f"Te confirmamos que la compra por {valor} "
        f"ya fue devuelta a tu {product_name}.\n\n"
        # Sin Markdown: el front no lo interpreta y los ** llegaban
        # literales a pantalla (confirmado por Fabian 20/08).
        "Detalle del reembolso:\n\n"
        f"{detalle_lines}\n\n"
        "Puedes consultar tus movimientos para confirmar "
        "que el valor ya se encuentra reflejado."
    )

    conversation.captured_data[
        "dynamic_prompt_2.4.0.1.19.2"
    ] = prompt


@log_execution
def _load_trx_permanent_block_success(
    conversation: Conversation,
) -> None:
    """Render successful permanent card block (2.4.0.1.17.2)."""

    last4 = _get_selected_trx_last4(conversation)
    try:
        dias = int(load_env_constants().get("DIAS_HABILES_TARJETA") or "10")
    except (ValueError, TypeError):
        dias = 10

    direccion = str(
        conversation.captured_data.get("trx_customer_address") or ""
    ).strip() or "registrada en nuestros sistemas"

    if last4:
        prompt = (
            f"Confirmamos que tu tarjeta terminada en •{last4} "
            "quedó cancelada por seguridad.\n\n"
            "Tu nueva tarjeta ya está en camino.\n\n"
            f"Te la enviaremos a la dirección {direccion} "
            f"en un lapso de {dias} días hábiles."
        )
    else:
        prompt = (
            "Confirmamos que tu tarjeta quedó cancelada por seguridad.\n\n"
            "Tu nueva tarjeta ya está en camino.\n\n"
            f"Te la enviaremos a {direccion} "
            f"en un lapso de {dias} días hábiles."
        )

    conversation.captured_data[
        "dynamic_prompt_2.4.0.1.17.3"
    ] = prompt


@log_execution
def _load_customer_products(conversation: Conversation) -> None:
    """
    Load customer products from the back-data control table (OpenSearch).

    The back-data service populates the control table record before this action
    runs. The ``back_data_result`` key in ``captured_data`` holds the JSON
    string of the ``data`` field from that record.

    Args:
        conversation: Runtime conversation that receives the resolved data.
    """

    back_data_raw = conversation.captured_data.get("back_data_result")
    if not back_data_raw:
        logger.warning(
            "No back_data_result in captured_data — cannot load products "
            "conversation_id=%s user_id=%s",
            conversation.conversation_id,
            conversation.user_id,
        )
        return

    logger.info(
        "Loading customer products from control table conversation_id=%s user_id=%s",
        conversation.conversation_id,
        conversation.user_id,
    )
    _override_product_prompt_from_back_data(conversation, back_data_raw)


@log_execution
def _load_selected_product_central_risk(conversation: Conversation) -> None:
    """
    Load the selected product and simulate a central-risk validation response.

    Args:
        conversation: Runtime conversation that receives the resolved response.
    """

    logger.info(
        "Loading selected product central-risk data conversation_id=%s selected_product=%s",
        conversation.conversation_id,
        conversation.flow_answers.get("producto_centrales_de_riesgo"),
    )
    customer_products: list[dict[str, Any]] = []
    back_data_map: list[dict[str, Any]] = []

    back_data_map_raw = conversation.captured_data.get("centrales_riesgo_back_data_map")
    if back_data_map_raw:
        try:
            back_data_map = json.loads(back_data_map_raw)
            customer_products = [
                _build_product_from_back_data_entry(e) for e in back_data_map
            ]
            logger.info(
                "Loaded products from centrales_riesgo_back_data_map "
                "conversation_id=%s products=%s",
                conversation.conversation_id,
                len(customer_products),
            )
        except Exception:
            logger.warning(
                "Failed to parse centrales_riesgo_back_data_map conversation_id=%s",
                conversation.conversation_id,
            )

    if not customer_products:
        conversation.captured_data["preserve_terminal_response"] = "true"
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            "Lo siento, no pude consultar los productos de esta cuenta en este momento. "
            "Gracias por comunicarte con nosotros."
        )
        return

    selected_product = _resolve_selected_product(
        customer_products,
        conversation.flow_answers.get("producto_centrales_de_riesgo"),
    )

    if selected_product is None:
        logger.info(
            "Selected product could not be resolved conversation_id=%s",
            conversation.conversation_id,
        )
        conversation.captured_data["preserve_terminal_response"] = "true"
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            "Lo siento, no pude identificar el producto seleccionado. "
            "Gracias por comunicarte con nosotros."
        )
        return

    _enrich_product_with_commercial_info(conversation, selected_product)

    obligation_data: dict[str, Any] = {}
    behavior_vector: list[str] = []

    obligation_raw = conversation.captured_data.get(
        "centrales_riesgo_obligacion_json", "{}"
    )
    try:
        obligation_data = json.loads(obligation_raw)
    except Exception:
        obligation_data = {}

    _selected_key = conversation.flow_answers.get("producto_centrales_de_riesgo")
    raw_entry: dict[str, Any] = {}
    primary: dict[str, Any] | None = None
    primary_id_msg: str | None = None

    try:
        _selected_index = int((_selected_key or "").split("_")[-1]) - 1
        raw_entry = back_data_map[_selected_index]
        raw_hallazgos: list[dict[str, Any]] = raw_entry.get("hallazgos") or []
        primary = next(
            (h for h in raw_hallazgos if int(h.get("id_msg") or 0) not in (0, 1)),
            None,
        )
        if primary is not None:
            primary_id_msg = str(primary.get("id_msg") or "").strip() or None
    except Exception:
        logger.warning(
            "Failed to resolve raw back-data entry conversation_id=%s",
            conversation.conversation_id,
        )

    behavior_vector = _resolve_active_behavior_vector(obligation_data, raw_entry)

    # For active products, the 24-month behavior vector is the primary source
    # of truth for mora. If it is available and confirms mora, we short-circuit
    # before any id_msg-based branch can render a shorter legacy message.
    if (
        selected_product.get("product_group") == "activo"
        and behavior_vector
        and primary_id_msg != "99"
        and _active_vector_confirms_mora(selected_product, behavior_vector)
    ):
        mora_profile = _extract_current_mora_profile(behavior_vector)
        logger.info(
            "Active mora resolved from behavior vector conversation_id=%s product_id=%s max_level=%s mora_months=%s",
            conversation.conversation_id,
            selected_product.get("product_id"),
            mora_profile["max_level"],
            mora_profile["mora_months"],
        )
        message_payload = _build_mora_negative_report_message(
            selected_product, obligation_data, behavior_vector
        )
        message, option = _render_centrales_structured_message(message_payload)
        conversation.captured_data["centrales_riesgo_escenario"] = (
            "reporte_negativo_mora_activo"
        )
        conversation.captured_data["satisfaction_context_message"] = message
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            message
        )
        if option:
            conversation.captured_data["centrales_riesgo_form_option"] = json.dumps(
                option, ensure_ascii=False
            )
        else:
            conversation.captured_data.pop("centrales_riesgo_form_option", None)
        return

    # --- id_msg dispatch (back-data driven) ---
    # Resolve the selected index and look up the raw hallazgos saved in the map.
    # If any hallazgo has an id_msg with a mapped message, use it and return early.
    try:
        if primary is not None:
            skip_id_msg_dispatch = (
                selected_product.get("product_group") == "activo"
                and primary_id_msg in {"4", "5", "21"}
            )
            if skip_id_msg_dispatch:
                logger.info(
                    "Skipping id_msg dispatch for activo mora routing conversation_id=%s product_id=%s primary_id_msg=%s",
                    conversation.conversation_id,
                    selected_product.get("product_id"),
                    primary_id_msg,
                )
            else:
                _id_msg = primary.get("id_msg")
                _variables = _resolve_centrales_variables(
                    _id_msg,
                    hallazgo=primary,
                    entry=raw_entry,
                    key_id=str(raw_entry.get("product_id") or ""),
                )
                _message, _option = _load_centrales_response(str(_id_msg), _variables)
                if _message:
                    logger.info(
                        "id_msg dispatch success conversation_id=%s id_msg=%s",
                        conversation.conversation_id,
                        _id_msg,
                    )
                    conversation.captured_data["centrales_riesgo_escenario"] = (
                        f"id_msg_{_id_msg}"
                    )
                    conversation.captured_data["satisfaction_context_message"] = _message
                    conversation.captured_data[
                        f"dynamic_prompt_{conversation.current_step}"
                    ] = _message
                    if _option:
                        conversation.captured_data["centrales_riesgo_form_option"] = (
                            json.dumps(_option, ensure_ascii=False)
                        )
                    else:
                        conversation.captured_data.pop("centrales_riesgo_form_option", None)
                    return
    except Exception:
        logger.warning(
            "id_msg dispatch failed — falling back to flag logic conversation_id=%s",
            conversation.conversation_id,
        )

    if not obligation_data:
        logger.info(
            "No JSON obligation found for product conversation_id=%s product_id=%s — using default handling",
            conversation.conversation_id,
            selected_product.get("product_id"),
        )
        if (
            selected_product.get("default_flag")
            or selected_product.get("written_off_flag")
            or (
                selected_product.get("product_group") == "activo"
                and (primary_id_msg in {"4", "5", "21"})
            )
        ):
            mora_days = int(selected_product.get("mora_days") or 0)
            fallback_months = int(selected_product.get("default_months_number") or 0)
            if fallback_months <= 0:
                fallback_months = max(1, mora_days // 30)
            behavior_vector = ["5"] * fallback_months if mora_days >= 120 else ["1"] * fallback_months
            message_payload = _build_mora_negative_report_message(
                selected_product, {}, behavior_vector
            )
            message, option = _render_centrales_structured_message(message_payload)
            conversation.captured_data["centrales_riesgo_escenario"] = (
                "reporte_negativo_mora_activo"
            )
            conversation.captured_data["satisfaction_context_message"] = message
            conversation.captured_data[
                f"dynamic_prompt_{conversation.current_step}"
            ] = message
            if option:
                conversation.captured_data["centrales_riesgo_form_option"] = (
                    json.dumps(option, ensure_ascii=False)
                )
            else:
                conversation.captured_data.pop("centrales_riesgo_form_option", None)
        elif selected_product.get("vendida_pendiente_flag"):
            message = _build_vendida_pendiente_message(selected_product, {})
            conversation.captured_data["centrales_riesgo_escenario"] = (
                "vendida_pendiente_actualizacion"
            )
            conversation.captured_data["satisfaction_context_message"] = message
            conversation.captured_data[
                f"dynamic_prompt_{conversation.current_step}"
            ] = message
        elif selected_product.get("off_loaded_portfolio_flag"):
            message = _build_off_loaded_portfolio_message(selected_product)
            conversation.captured_data["centrales_riesgo_escenario"] = (
                "cartera_vendida_sin_reporte_central"
            )
            conversation.captured_data["satisfaction_context_message"] = message
            conversation.captured_data[
                f"dynamic_prompt_{conversation.current_step}"
            ] = message
            conversation.captured_data["centrales_riesgo_form_option"] = json.dumps(
                {"key": "pqr", "label": "Formulario PQR"}, ensure_ascii=False
            )
        elif selected_product.get("embargo_state") == "actualizado_sin_embargo":
            message = _build_actualizado_sin_embargo_message(selected_product, {})
            conversation.captured_data["centrales_riesgo_escenario"] = (
                "embargo_actualizado_sin_embargo"
            )
            conversation.captured_data["satisfaction_context_message"] = message
            conversation.captured_data[
                f"dynamic_prompt_{conversation.current_step}"
            ] = message
        else:
            message = _build_no_central_report_message(
                selected_product, customer_products
            )
            conversation.captured_data["centrales_riesgo_escenario"] = (
                "sin_reporte_central_sin_bloqueo"
            )
            conversation.captured_data["preserve_terminal_response"] = "true"
            conversation.captured_data[
                f"dynamic_prompt_{conversation.current_step}"
            ] = message
        return

    if _active_vector_confirms_mora(selected_product, behavior_vector):
        mora_profile = _extract_current_mora_profile(behavior_vector)
        max_level = mora_profile["max_level"]
        logger.info(
            "Cross-validated mora for activo product conversation_id=%s product_id=%s max_level=%s mora_months=%s",
            conversation.conversation_id,
            selected_product.get("product_id"),
            max_level,
            mora_profile["mora_months"],
        )
        message_payload = _build_mora_negative_report_message(
            selected_product, obligation_data, behavior_vector
        )
        message, option = _render_centrales_structured_message(message_payload)
        conversation.captured_data["centrales_riesgo_escenario"] = (
            "reporte_negativo_mora_activo"
        )
        conversation.captured_data["satisfaction_context_message"] = message
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            message
        )
        if option:
            conversation.captured_data["centrales_riesgo_form_option"] = json.dumps(
                option, ensure_ascii=False
            )
        else:
            conversation.captured_data.pop("centrales_riesgo_form_option", None)
        return

    if selected_product.get("vendida_pendiente_flag"):
        message = _build_vendida_pendiente_message(selected_product, obligation_data)
        conversation.captured_data["centrales_riesgo_escenario"] = (
            "vendida_pendiente_actualizacion"
        )
        conversation.captured_data["satisfaction_context_message"] = message
        conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = (
            message
        )
        return

    if selected_product.get("off_loaded_portfolio_flag"):
        message = _build_off_loaded_portfolio_message(selected_product)
        conversation.captured_data["centrales_riesgo_escenario"] = (
            "cartera_vendida_sin_reporte_central"
        )
        conversation.captured_data["satisfaction_context_message"] = message
        conversation.captured_data[
            f"dynamic_prompt_{conversation.current_step}"
        ] = message
        conversation.captured_data["centrales_riesgo_form_option"] = json.dumps(
            {"key": "pqr", "label": "Formulario PQR"}, ensure_ascii=False
        )
        return
    elif selected_product.get("product_group") == "pasivo":
        match_state = _classify_pasivo_embargo_match(selected_product, obligation_data)
        logger.info(
            "Pasivo embargo match state conversation_id=%s product_id=%s match_state=%s",
            conversation.conversation_id,
            selected_product.get("product_id"),
            match_state,
        )
        if match_state == "pendiente_actualizacion":
            message = _build_pendiente_actualizacion_message(
                selected_product, obligation_data
            )
            conversation.captured_data["centrales_riesgo_escenario"] = (
                "embargo_levantado_pendiente_actualizacion"
            )
            conversation.captured_data["satisfaction_context_message"] = message
            conversation.captured_data[
                f"dynamic_prompt_{conversation.current_step}"
            ] = message
            conversation.captured_data["centrales_riesgo_form_option"] = json.dumps(
                {"key": "pqr", "label": "Formulario PQR"}, ensure_ascii=False
            )
            return
        elif match_state == "actualizado_sin_embargo":
            message = _build_actualizado_sin_embargo_message(
                selected_product, obligation_data
            )
            conversation.captured_data["centrales_riesgo_escenario"] = (
                "embargo_actualizado_sin_embargo"
            )
            conversation.captured_data["satisfaction_context_message"] = message
            conversation.captured_data[
                f"dynamic_prompt_{conversation.current_step}"
            ] = message
            return
        elif match_state == "sin_embargo":
            message = _build_pasivo_sin_embargo_message(
                selected_product, obligation_data
            )
            conversation.captured_data["centrales_riesgo_escenario"] = (
                "pasivo_sin_embargo_coincide"
            )
        elif match_state == "embargo_vigente":
            message = _build_pasivo_embargo_vigente_message(
                selected_product, obligation_data
            )
            conversation.captured_data["centrales_riesgo_escenario"] = (
                "pasivo_embargo_vigente_coincide"
            )
        elif match_state == "desembargado":
            message = _build_pasivo_embargo_levantado_message(
                selected_product, obligation_data
            )
            conversation.captured_data["centrales_riesgo_escenario"] = (
                "pasivo_embargo_levantado_coincide"
            )
        else:  # no_coinciden
            message = _build_no_central_report_message(
                selected_product, customer_products
            )
            conversation.captured_data["centrales_riesgo_escenario"] = (
                "pasivo_sin_coincidencia"
            )
    else:
        message = _build_no_central_report_message(selected_product, customer_products)
        conversation.captured_data["centrales_riesgo_escenario"] = (
            "sin_reporte_central_sin_bloqueo"
        )
    conversation.captured_data["preserve_terminal_response"] = "true"
    conversation.captured_data[f"dynamic_prompt_{conversation.current_step}"] = message


def _build_product_from_back_data_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """
    Convert an enriched back-data map entry into a product dict compatible with
    the existing workflow logic (same shape as ADA CSV products).
    """

    product_id = str(entry.get("product_id") or "").strip()
    contract_id = str((entry.get("card_id") or entry.get("contract_id")) or "").strip()
    state_dict: dict[str, Any] = entry.get("state_dict") or {}
    active_mora_payload = state_dict.get("activo_mora")

    # Derive product metadata from the prefix of the key_id (e.g. "4310-AHO")
    parts = product_id.split("-")
    product_prefix = "-".join(parts[:2]) if len(parts) >= 2 else ""
    metadata = _ADA_PRODUCT_DESC_METADATA.get(
        product_prefix, _DEFAULT_ADA_PRODUCT_METADATA
    )

    default_flag = "activo_mora" in state_dict
    written_off_flag = any(k.startswith("activo_castigado") for k in state_dict)
    off_loaded = "vendida" in state_dict
    vendida_pendiente = (
        off_loaded and "pendiente" in str(state_dict.get("vendida", "")).lower()
    )
    seizure = "embargada" in state_dict

    if written_off_flag:
        account_status = "castigado"
    elif default_flag:
        account_status = "en_mora"
    elif seizure:
        account_status = "con_restricciones"
    else:
        account_status = "activo"

    try:
        if isinstance(active_mora_payload, dict):
            mora_days = int(active_mora_payload.get("dias_mora") or 0)
        else:
            mora_days = int(active_mora_payload or 0)
    except (ValueError, TypeError):
        mora_days = 0

    try:
        mora_months = int(
            (active_mora_payload or {}).get("mora_months")
            if isinstance(active_mora_payload, dict)
            else 0
        )
    except (ValueError, TypeError, AttributeError):
        mora_months = 0

    if mora_months <= 0 and mora_days > 0:
        mora_months = mora_days // 30

    return {
        "product_id": product_id,
        "contract_id": contract_id,
        "product_type": str(
            entry.get("commercial_product_desc") or metadata["product_type"]
        ),
        "product_group": metadata["product_group"],
        "account_status": account_status,
        "central_report_status": account_status,
        "default_flag": default_flag,
        "written_off_flag": written_off_flag,
        "off_loaded_portfolio_flag": off_loaded,
        "vendida_pendiente_flag": vendida_pendiente,
        "seizure_flag": seizure,
        "restructured_flag": "activo_reestructurado" in state_dict,
        "mora_days": mora_days,
        "default_months_number": mora_months,
        "embargo_state": (
            "sin_embargo"
            if not seizure
            else "pendiente_actualizacion"
            if "pendiente" in str(state_dict.get("embargada", "")).lower()
            else "actualizado_sin_embargo"
            if "sin embargo" in str(state_dict.get("embargada", "")).lower()
            else "vigente"
        ),
        "customer_name": "",
        "buyer_name": str(state_dict.get("vendida", "")),
    }


@log_execution
def _load_commercial_info_obligations(
    conversation: Conversation,
) -> list[dict[str, Any]]:
    """
    Load the ``history.obligations`` list from the commercial-info JSON file
    for the current customer.

    The file is resolved by personal_id pattern:
    ``commercial_info_{personal_id}.json``.

    Returns:
        List of obligation dictionaries from the JSON, or an empty list
        when the file is missing or malformed.
    """

    personal_id = str(conversation.user_id or "").strip()
    json_path = _COMMERCIAL_INFO_BASE_PATH / f"commercial_info_{personal_id}.json"

    if not json_path.exists():
        logger.warning(
            "Commercial info JSON not found conversation_id=%s path=%s",
            conversation.conversation_id,
            json_path,
        )
        return []

    try:
        raw = json_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        obligations = data.get("data", {}).get("history", {}).get("obligations", [])
        if not isinstance(obligations, list):
            return []
        return obligations
    except Exception:
        logger.exception(
            "Failed to parse commercial info JSON conversation_id=%s path=%s",
            conversation.conversation_id,
            json_path,
        )
        return []


@log_execution
def _find_obligation_by_key_id(
    obligations: list[dict[str, Any]],
    key_id: str | None,
) -> dict[str, Any] | None:
    """
    Find the obligation in the commercial-info JSON whose ``number``
    matches the product's ``key_id`` from the ADA CSV.

    Args:
        obligations: Full list of obligations from the JSON.
        key_id: Product key from the ADA CSV (string representation of the number).

    Returns:
        Matching obligation dictionary or ``None`` when not found.
    """

    if not key_id:
        return None

    raw_key = str(key_id).strip()
    if not raw_key:
        return None

    candidate_numbers: list[int] = []

    # Exact numeric key_id (legacy shape)
    if raw_key.isdigit():
        candidate_numbers.append(int(raw_key))

    # Composite key_id (e.g. "4350-CAB-000100200"): prioritize the last
    # numeric token, then consider all numeric chunks as fallback.
    digit_chunks = re.findall(r"\d+", raw_key)
    if digit_chunks:
        candidate_numbers.append(int(digit_chunks[-1]))
        for chunk in digit_chunks[:-1]:
            candidate_numbers.append(int(chunk))

    # Deduplicate while preserving order.
    seen: set[int] = set()
    ordered_candidates: list[int] = []
    for number in candidate_numbers:
        if number not in seen:
            seen.add(number)
            ordered_candidates.append(number)

    if not ordered_candidates:
        return None

    for obligation in obligations:
        number_raw = obligation.get("number")
        try:
            obligation_number = int(number_raw)
        except (ValueError, TypeError):
            continue
        if obligation_number in ordered_candidates:
            return obligation

    return None


@log_execution
def _enrich_product_with_commercial_info(
    conversation: Conversation,
    selected_product: dict[str, Any],
) -> None:
    """
    Cross-reference the selected product with the commercial-info JSON and
    store the relevant obligation fields in ``conversation.captured_data``.

    Args:
        conversation: Runtime conversation that receives the enriched data.
        selected_product: Already-resolved product from the ADA CSV.
    """

    obligations = _load_commercial_info_obligations(conversation)
    key_id = selected_product.get("product_id")
    obligation = _find_obligation_by_key_id(obligations, key_id)

    if obligation is None:
        logger.info(
            "No commercial info obligation found conversation_id=%s key_id=%s",
            conversation.conversation_id,
            key_id,
        )
        return

    logger.info(
        "Commercial info obligation matched conversation_id=%s key_id=%s",
        conversation.conversation_id,
        key_id,
    )

    contract_type = obligation.get("contractType") or {}
    classification = obligation.get("classificationStatus") or {}
    product_type_info = obligation.get("productType") or {}
    institution = obligation.get("financialInstitutionInformation") or {}
    initial = obligation.get("initial") or {}
    balance = obligation.get("productBalance") or {}
    pending = obligation.get("pending") or {}
    monthly = obligation.get("monthly") or {}
    rating = obligation.get("rating") or {}

    conversation.captured_data["centrales_riesgo_obligacion_tipo_contrato"] = str(
        contract_type.get("id", "")
    )
    conversation.captured_data["centrales_riesgo_obligacion_clasificacion"] = str(
        classification.get("id", "")
    )
    conversation.captured_data["centrales_riesgo_obligacion_tipo_producto"] = str(
        product_type_info.get("name") or ""
    )
    conversation.captured_data["centrales_riesgo_obligacion_institucion"] = str(
        institution.get("name") or ""
    )
    conversation.captured_data["centrales_riesgo_obligacion_monto_inicial"] = str(
        initial.get("amount", 0)
    )
    conversation.captured_data["centrales_riesgo_obligacion_saldo"] = str(
        balance.get("amount", 0)
    )
    conversation.captured_data["centrales_riesgo_obligacion_pendiente"] = str(
        pending.get("amount", 0)
    )
    conversation.captured_data["centrales_riesgo_obligacion_cuota_mensual"] = str(
        monthly.get("amount", 0)
    )
    conversation.captured_data["centrales_riesgo_obligacion_calificacion"] = str(
        rating.get("id") or rating.get("description") or ""
    )

    opening_date = str(obligation.get("openingDate") or "").strip()
    closing_date = str(obligation.get("closingDate") or "").strip()
    if opening_date:
        conversation.captured_data["centrales_riesgo_obligacion_fecha_apertura"] = (
            opening_date[:10]
        )
    if closing_date and closing_date != "9999-01-01T00:00:00.0-0500":
        conversation.captured_data["centrales_riesgo_obligacion_fecha_cierre"] = (
            closing_date[:10]
        )

    conversation.captured_data["centrales_riesgo_obligacion_json"] = json.dumps(
        obligation, ensure_ascii=False
    )


@log_execution
@log_execution
def _resolve_selected_product(
    customer_products: list[dict[str, Any]],
    selected_key: str | None,
) -> dict[str, Any] | None:
    """
    Resolve the selected product from the numeric workflow option.

    Args:
        customer_products: Mock products loaded for the customer.
        selected_key: Stored workflow answer such as `producto_1`.

    Returns:
        Matching product dictionary or `None`.
    """

    if not selected_key or not selected_key.startswith("producto_"):
        return None

    try:
        selected_index = int(selected_key.split("_")[-1]) - 1
    except ValueError:
        return None

    if selected_index < 0 or selected_index >= len(customer_products):
        return None

    return customer_products[selected_index]


@log_execution
def _build_selected_product_central_risk_result(
    product: dict[str, Any],
) -> tuple[str, str]:
    """
    Build the deterministic response for the selected passive product.

    Args:
        product: Selected product loaded from the mock.

    Returns:
        A tuple with the scenario key and the deterministic fallback message.
    """

    account_status = _normalize_status(product.get("account_status", "activa"))
    central_report_status = _normalize_status(
        product.get("central_report_status", account_status)
    )
    embargo_state = str(product.get("embargo_state", "sin_embargo")).strip().lower()
    lifted_at = _parse_date(
        product.get("embargo_lifted_at") or product.get("lifted_at")
    )

    if account_status != central_report_status:
        if lifted_at is not None and _days_since(lifted_at) > 30:
            return "actualizacion_reflejada_en_24_horas", _build_after_30_days_message()

        return (
            "actualizacion_en_proceso_hasta_ciclo_de_reporte",
            _build_before_30_days_message(),
        )

    if embargo_state == "sin_embargo":
        return "sin_embargo_y_reporte_correcto", _build_no_embargo_correct_message(
            account_status
        )

    if embargo_state == "levantado" and lifted_at is not None:
        return "embargo_levantado_y_reporte_correcto", _build_lifted_embargo_message(
            account_status,
            lifted_at,
        )

    return "embargo_vigente_y_reporte_correcto", _build_active_embargo_message(
        product,
        account_status,
    )


@log_execution
def _build_selected_product_central_risk_guidance(
    product: dict[str, Any],
    scenario: str,
) -> str:
    """
    Build the business guidance that the LLM must preserve in its final answer.

    Args:
        product: Selected product loaded from the mock.
        scenario: Technical scenario derived from the mock state.

    Returns:
        Guidance string that summarizes the approved business content.
    """

    account_status = _normalize_status(product.get("account_status", "desconocido"))
    central_status = _normalize_status(
        product.get("central_report_status", "desconocido")
    )

    if scenario == "actualizacion_reflejada_en_24_horas":
        return (
            "Explica que ya realizamos la actualizacion del estado de la cuenta ante "
            "la central de riesgo y que el cambio podra verse reflejado en 24 horas "
            "habiles. Cierra agradeciendo el contacto."
        )

    if scenario == "actualizacion_en_proceso_hasta_ciclo_de_reporte":
        return (
            "Explica que ya recibimos la notificacion de desembargo, que la "
            "actualizacion esta en proceso y que el reflejo en centrales se hara "
            "en el proximo ciclo de reporte de 30 dia mes vencido."
        )

    if scenario == "sin_embargo_y_reporte_correcto":
        return (
            "Explica que la cuenta no presenta bloqueo, que el estado actual es "
            f"'{account_status}' y que el reporte en centrales '{central_status}' "
            "esta acorde con el estado actual de la cuenta."
        )

    if scenario == "embargo_levantado_y_reporte_correcto":
        return (
            "Explica que el embargo ya fue levantado, menciona la fecha de "
            "levantamiento si existe y aclara que el reporte en centrales esta "
            "acorde con el estado actual de la cuenta."
        )

    return (
        "Explica que existe un embargo vigente sobre la cuenta. Incluye los datos "
        "del embargo disponibles, aclara que no es un reporte negativo, explica "
        "que la actualizacion depende del oficio de desembargo y recomienda "
        "contactar directamente a la entidad embargante."
    )


@log_execution
def _format_products(products: list[dict[str, str]]) -> str:
    """
    Convert a list of products into a readable summary string.

    Args:
        products: Product dictionaries loaded from the embargo CSV.

    Returns:
        Human-readable product summary.
    """

    if not products:
        return "Ninguno"

    formatted_products = [
        f"{product['product_id']} ({product['product_type']})" for product in products
    ]
    return ", ".join(formatted_products)


@log_execution
def _format_currency(raw_value: Any) -> str:
    """
    Format a numeric embargo amount for user-facing responses.

    Args:
        raw_value: Raw amount value loaded from the CSV row.

    Returns:
        Currency string in a readable format.
    """

    if raw_value in {None, ""}:
        return "No disponible"

    try:
        amount = Decimal(str(raw_value))
    except InvalidOperation:
        return str(raw_value)

    formatted_amount = f"{amount:,.2f}"
    formatted_amount = (
        formatted_amount.replace(",", "_").replace(".", ",").replace("_", ".")
    )

    if formatted_amount.endswith(",00"):
        formatted_amount = formatted_amount[:-3]

    return f"$ {formatted_amount}"


@log_execution
def _normalize_status(raw_value: Any) -> str:
    """
    Normalize a status value coming from the mock product payload.

    Args:
        raw_value: Raw status value loaded from the product record.

    Returns:
        User-friendly lowercase status.
    """

    normalized_value = str(raw_value or "").strip().lower().replace("_", " ")
    return normalized_value or "desconocido"


@log_execution
def _build_product_selection_prompt(products: list[dict[str, str]]) -> str:
    """
    Build the dynamic product-selector prompt shown to the user.

    Args:
        products: Product dictionaries loaded from the mock file.

    Returns:
        Markdown message with the available products in numeric order.
    """

    lines = ["## Selecciona el producto que deseas consultar", ""]

    for index, product in enumerate(products, start=1):
        lines.append(f"{index}. **{product['product_type']}**")
        lines.append(f"   `**** {_last4_contrato(product)}`")

    lines.append("")
    lines.append("Responde con el numero de la opcion que prefieres.")
    return "\n".join(lines)


@log_execution
@log_execution
def _build_state_label_from_back_data(state_dict: dict[str, Any]) -> str:
    """
    Translate the state dictionary from the back-data validaciones entry
    into a human-readable Spanish label.

    Args:
        state_dict: Findings dict for one product, e.g. {"activo_mora": 3}.

    Returns:
        Comma-separated label string, or "Al dia" when no findings.
    """

    if not state_dict:
        return "Al dia"

    labels: list[str] = []

    if "vendida" in state_dict:
        buyer = str(state_dict["vendida"]).strip()
        labels.append(f"Cartera vendida a {buyer}" if buyer else "Cartera vendida")

    if "embargada" in state_dict:
        embargo_val = str(state_dict["embargada"]).lower()
        if "sin embargo" in embargo_val:
            labels.append("Sin embargo")
        elif "pendiente" in embargo_val:
            labels.append("Pendiente actualizar en centrales")
        elif "desembarg" in embargo_val:
            labels.append("Des-embargada")
        else:
            labels.append("Con embargo")

    if "activo_mora" in state_dict:
        labels.append("En mora")

    if any(
        k in state_dict
        for k in (
            "activo_castigado",
            "activo_castigado_presente",
            "activo_castigado_pasado",
        )
    ):
        labels.append("Castigado")

    if "activo_reestructurado" in state_dict:
        labels.append("Reestructurado")

    return ", ".join(labels) if labels else "Al dia"


@log_execution
def _build_product_selection_prompt_from_back_data(
    products: list[dict[str, Any]],
) -> str:
    """
    Build the dynamic product-selector prompt using enriched back-data products.

    Args:
        products: Enriched product dicts with product_type, product_id and state_label.

    Returns:
        Markdown message with real products and their centrales states.
    """

    lines = ["## Selecciona el producto que deseas consultar", ""]
    lines.append(
        "Las siguiente opciones tienen alguna novedad en centrales de riesgo ¿Cual quieres consultar?"
    )
    lines.append("")

    for product in products:
        last4 = _last4_contrato(product)
        commercial_product_desc = str(
            product.get("commercial_product_desc") or "Producto financiero"
        ).strip() or "Producto financiero"
        lines.append(f"- CONTRATO {commercial_product_desc} *{last4}")

    lines.append("")
    lines.append("Responde con el numero de la opcion que prefieres.")
    return "\n".join(lines)


@log_execution
def _override_product_prompt_from_back_data(
    conversation: Conversation,
    back_data_raw: str,
) -> None:
    """
    Build the product-selector prompt from the back-data control table entry.

    Each entry in ``hallazgos.validaciones`` is expected to carry a
    ``product_desc`` field written by the back-data service (e.g. ``4310-AHO``).
    That code is mapped to a human-readable ``product_type`` via
    ``_ADA_PRODUCT_DESC_METADATA``.

    Args:
        conversation: Runtime conversation that receives the updated prompt.
        back_data_raw: JSON string stored in captured_data["back_data_result"].
    """

    try:
        back_data = json.loads(back_data_raw)
    except Exception:
        logger.warning(
            "Failed to parse back_data_result conversation_id=%s",
            conversation.conversation_id,
        )
        return

    validaciones: list[dict[str, Any]] = back_data.get("hallazgos", {}).get(
        "validaciones", []
    )

    if not validaciones:
        logger.info(
            "back_data_result has no validaciones conversation_id=%s",
            conversation.conversation_id,
        )
        _route_to_no_products_satisfaction(conversation)
        return

    enriched_products: list[dict[str, Any]] = []
    for entry in validaciones:
        key_id = str(entry.get("key_id") or "").strip()
        if not key_id:
            continue
        hallazgos_list: list[dict[str, Any]] = entry.get("hallazgos") or []
        state_dict: dict[str, Any] = {
            str(h.get("tipo", "")).strip(): h.get("valor", "")
            for h in hallazgos_list
            if h.get("tipo")
        }
        enriched_products.append(
            {
                "product_id": key_id,
                # Idem: sin esto este camino caeria al key_id en silencio y
                # quedaria arreglado en unos sitios y roto en otros.
                "contract_id": str(entry.get("contract_id") or "").strip(),
                "commercial_product_desc": str(
                    entry.get("commercial_product_desc")
                    or entry.get("product_desc")
                    or "Producto financiero"
                ).strip()
                or "Producto financiero",
                "state_label": _build_state_label_from_back_data(state_dict),
                "state_dict": state_dict,
            }
        )

    if not enriched_products:
        logger.info(
            "No enriched products built from validaciones conversation_id=%s",
            conversation.conversation_id,
        )
        _route_to_no_products_satisfaction(conversation)
        return

    conversation.captured_data["centrales_riesgo_back_data_map"] = json.dumps(
        enriched_products, ensure_ascii=False
    )
    logger.info(
        "Built back-data product prompt conversation_id=%s products=%s",
        conversation.conversation_id,
        len(enriched_products),
    )
    conversation.captured_data["dynamic_prompt_1.4.1.1"] = (
        _build_product_selection_prompt_from_back_data(enriched_products)
    )
    conversation.captured_data["dynamic_option_labels_1.4.1.1"] = json.dumps(
        [
            (
                "CONTRATO "
                f"{p.get('commercial_product_desc') or 'Producto financiero'} "
                f"*{_last4_contrato(p)}"
            )
            for p in enriched_products
        ],
        ensure_ascii=False,
    )


@log_execution
def _parse_date(raw_value: Any) -> date | None:
    """
    Parse an ISO date string into a `date` object.

    Args:
        raw_value: Raw date value read from the mock file.

    Returns:
        Parsed date or `None` when not available.
    """

    if not raw_value:
        return None

    return date.fromisoformat(str(raw_value))


@log_execution
def _days_since(target_date: date) -> int:
    """
    Return the number of days between today and the provided date.

    Args:
        target_date: Reference date to compare against the current day.

    Returns:
        Positive number of elapsed days.
    """

    return (date.today() - target_date).days


@log_execution
def _format_display_date(target_date: date) -> str:
    """
    Format a date for user-facing responses.

    Args:
        target_date: Date to format.

    Returns:
        Date formatted as `DD/MM/YYYY`.
    """

    return target_date.strftime("%d/%m/%Y")


@log_execution
def _build_no_central_report_message(
    product: dict[str, Any],
    all_products: list[dict[str, Any]] | None = None,
) -> str:
    """
    Build the response when the product has no record in centrales de riesgo
    and no portfolio sale flag in the CSV.

    Shows a positive "no negative reports" message. If the customer has a
    single product the message references that product only; if there are
    multiple products all of them are listed.
    """

    tail = (
        "Puedes tener la tranquilidad de que tu historial crediticio está al día "
        "y no presenta novedades negativas en este momento."
    )

    products = all_products if all_products else [product]

    if len(products) == 1:
        p = products[0]
        product_type = p.get("product_type") or "Producto"
        last4 = _last4_contrato(p)
        return (
            f"¡Buenas noticias! He terminado la validación y no tienes reportes negativos "
            f"en las centrales de riesgo asociados a tu {product_type} terminado en {last4}.\n\n"
            f"{tail}"
        )

    product_lines = ""
    for p in products:
        product_type = p.get("product_type") or "Producto"
        last4 = _last4_contrato(p)
        product_lines += f"- {product_type} terminado en {last4}\n"

    return (
        "¡Buenas noticias! He terminado la revisión y no tienes reportes negativos "
        "en las centrales de riesgo asociados a tus productos:\n\n"
        f"{product_lines}\n"
        f"{tail}"
    )


@log_execution
def _build_off_loaded_portfolio_message(product: dict[str, Any]) -> str:
    """
    Build the response when the product was sold to a new creditor entity
    (off_loaded_portfolio_flag = True).

    Includes buyer information, regulatory notice, and optional PQR form link
    for requesting a creditor update in centrales de riesgo.
    """

    buyer_name = str(product.get("buyer_name") or "").strip() or "No disponible"
    return (
        "🔔 Notificacion sobre tu producto\n\n"
        "Te informamos que tu producto fue vendido a una nueva entidad acreedora "
        "y actualmente se encuentra al dia con BBVA.\n\n"
        f"📌 Nueva entidad acreedora: {buyer_name}\n\n"
        "Esta operacion se realizo conforme a la normativa vigente aplicable.\n\n"
        "Para mas informacion sobre tu obligacion, puedes comunicarte directamente "
        "con la nueva entidad acreedora.\n\n"
        "Si requieres una actualizacion del acreedor en centrales de riesgo, "
        "radica tu solicitud con el boton de abajo."
    )


@log_execution
def _classify_pasivo_embargo_match(
    product: dict[str, Any],
    obligation: dict[str, Any],
) -> str:
    """
    Compare CSV seizure flag vs JSON escrow field to determine embargo agreement.

    Returns:
        "sin_embargo"              – both sources agree: no active embargo.
        "embargo_vigente"          – both sources agree: embargo is active.
        "desembargado"             – JSON escrow record exists with a real closing date,
                                     CSV seizure is already cleared.
        "pendiente_actualizacion"  – embargo lifted but credit bureau report not yet updated.
        "no_coinciden"             – sources disagree; escalate to form link.
    """

    if product.get("embargo_state") == "pendiente_actualizacion":
        return "pendiente_actualizacion"

    if product.get("embargo_state") == "actualizado_sin_embargo":
        return "actualizado_sin_embargo"

    csv_seizure = product.get("seizure_flag", False)
    escrow = obligation.get("escrow")
    escrow_data = escrow or {}

    if not csv_seizure:
        if escrow is None:
            return "sin_embargo"
        closing = str(escrow_data.get("closingDate") or "").strip()
        if closing and "9999" not in closing:
            return "desembargado"
        return "no_coinciden"

    # CSV shows active seizure
    if escrow is not None:
        return "embargo_vigente"
    # CSV says embargo but JSON has no escrow record — use CSV as source of truth
    return "embargo_vigente"


@log_execution
def _map_json_classification_to_label(obligation: dict[str, Any]) -> str:
    """Map classificationStatus.id to a human-readable Spanish account label."""

    classification = str(
        (obligation.get("classificationStatus") or {}).get("id", "")
    ).upper()
    label_map = {
        "NORMA": "activa",
        "VIGE": "activa",
        "INACT": "inactiva",
        "SALDA": "saldada",
        "PTOT": "pagada totalmente",
        "NOREP": "sin reporte",
    }
    return label_map.get(classification, "activa")


@log_execution
def _build_vendida_pendiente_message(
    product: dict[str, Any],
    obligation: dict[str, Any],
) -> str:
    """
    Build the response when vendida = "Actualizacion Pendiente en 30 dias":
    the embargo was lifted and the credit bureau update is within the 30-day window.
    """

    escrow_data = obligation.get("escrow") or {}
    raw_date = str(
        escrow_data.get("closingDate") or obligation.get("closingDate") or ""
    ).strip()
    lifting_date: date | None = None
    if raw_date:
        try:
            lifting_date = date.fromisoformat(raw_date[:10])
        except (ValueError, TypeError):
            pass

    date_str = (
        _format_display_date(lifting_date) if lifting_date else "fecha no disponible"
    )
    status_label = (
        _map_json_classification_to_label(obligation).capitalize()
        if obligation
        else _normalize_status(product.get("account_status", "activa")).capitalize()
    )

    return (
        f"Hice la validacion de tu caso y encontre que el embargo sobre tu cuenta fue "
        f"levantado el dia {date_str}. "
        "La informacion reportada coincide con tu estado actual en el banco.\n\n"
        f"El estado actual de tu cuenta es: {status_label}."
    )


@log_execution
def _build_actualizado_sin_embargo_message(
    product: dict[str, Any],
    obligation: dict[str, Any],
) -> str:
    """
    Build the response when the embargo was lifted AND the credit bureau
    report has already been updated ("Status Actualizado, sin embargo").
    Lists the product with its current status to reassure the customer.
    """

    product_type = str(product.get("product_type") or "Producto")
    last4 = _last4_contrato(product)
    status_label = (
        _map_json_classification_to_label(obligation).capitalize()
        if obligation
        else _normalize_status(product.get("account_status", "activa")).capitalize()
    )

    return (
        "He revisado tus productos y encontre que la informacion reportada coincide "
        "con tu estado actual en el banco. Ninguno de ellos presenta bloqueos que "
        "afecten tu historial:\n\n"
        f"\u2022 {product_type} terminado en {last4}: {status_label}\n\n"
        "Quedate con la tranquilidad de que todo esta en orden y reflejado correctamente."
    )


@log_execution
def _build_pendiente_actualizacion_message(
    product: dict[str, Any],
    obligation: dict[str, Any],
) -> str:
    """
    Build the response when the embargo has been lifted but the credit bureau
    report has not yet been updated ("Pendiente Actualizar Centrales").
    Randomly selects one of two message variants and includes the PQR form link.
    """

    messages = [
        (
            "Tu caso requiere una revision a fondo por parte de nuestro equipo especializado.\n\n"
            "Para radicar tu solicitud, por favor completa el formulario de PQRS con el boton de abajo. "
            "Asi podremos analizar lo ocurrido con tu reporte y darte una respuesta oficial."
        ),
        (
            "Para darte una solucion definitiva, necesitamos que nuestro equipo de especialistas "
            "revise tu reporte detalladamente.\n\n"
            "Por favor, registra tu solicitud con el boton de abajo y nosotros nos encargaremos de analizarlo."
        ),
    ]
    return random.choice(messages)


@log_execution
def _build_pasivo_sin_embargo_message(
    product: dict[str, Any],
    obligation: dict[str, Any],
) -> str:
    """
    Build the response for a pasivo product when both CSV and JSON
    agree there is no active embargo.
    """

    account_label = _map_json_classification_to_label(obligation)
    return (
        "🔔 Notificacion importante sobre tu cuenta\n\n"
        "Te informamos que tu cuenta no presenta ningun bloqueo y el estado "
        "corresponde al status actual de tu cuenta ante el banco.\n\n"
        f"📌 Estado actual de la cuenta: {account_label}\n\n"
        "📊 Reporte en centrales de riesgo: La informacion reportada se encuentra "
        "acorde con el estado actual de tu cuenta.\n\n"
        "Gracias por comunicarte con nosotros."
    )


@log_execution
def _build_pasivo_embargo_levantado_message(
    product: dict[str, Any],
    obligation: dict[str, Any],
) -> str:
    """
    Build the response when both sources agree the embargo on a pasivo
    product has been lifted.
    """

    escrow_data = obligation.get("escrow") or {}
    raw_date = str(escrow_data.get("closingDate") or "").strip()
    lifting_date: date | None = None
    if raw_date:
        try:
            lifting_date = date.fromisoformat(raw_date[:10])
        except (ValueError, TypeError):
            pass

    account_label = _map_json_classification_to_label(obligation)
    date_str = (
        _format_display_date(lifting_date) if lifting_date else "fecha no disponible"
    )
    return (
        "🔔 Notificacion importante sobre tu cuenta\n\n"
        f"Te informamos que el embargo sobre tu cuenta ha sido levantado el dia {date_str}.\n\n"
        f"📌 Estado actual de la cuenta: {account_label}\n\n"
        "📊 Reporte en centrales de riesgo: La informacion reportada se encuentra "
        "acorde con el estado actual de tu cuenta.\n\n"
        "Gracias por comunicarte con nosotros."
    )


@log_execution
def _build_pasivo_embargo_vigente_message(
    product: dict[str, Any],
    obligation: dict[str, Any],
) -> str:
    """
    Build the response when both sources confirm an active embargo on a
    pasivo product.
    """

    escrow_data = obligation.get("escrow") or {}
    entity_name = str(
        escrow_data.get("entityName") or escrow_data.get("entity") or "No disponible"
    )
    embargo_number = str(
        escrow_data.get("number") or escrow_data.get("id") or "No disponible"
    )
    official_notice = str(
        escrow_data.get("officialNotice")
        or escrow_data.get("notice")
        or "No disponible"
    )
    raw_date = str(escrow_data.get("date") or escrow_data.get("startDate") or "")[:10]
    embargo_date_str = raw_date if raw_date else "No disponible"
    amount_str = _format_currency(escrow_data.get("amount"))

    return (
        "🔔 Notificacion sobre tu cuenta\n\n"
        "Te informamos que actualmente presentas un embargo vigente sobre tu cuenta, "
        "con el siguiente detalle:\n\n"
        f"• Entidad embargante: {entity_name}\n"
        f"• Numero de embargo: {embargo_number}\n"
        f"• Oficio de embargo: {official_notice}\n"
        f"• Fecha: {embargo_date_str}\n"
        f"• Monto: {amount_str}\n\n"
        "📌 Informacion importante: Este reporte no es negativo. Corresponde al "
        "estado actual de tu producto debido a la medida de embargo.\n\n"
        "El estado de la cuenta se actualizara una vez recibamos el oficio de "
        "desembargo por parte de la entidad correspondiente. Este proceso puede "
        "tomar hasta 30 dias posteriores a su recepcion.\n\n"
        "➡️ ¿Que puedes hacer? Para gestionar el levantamiento del embargo, te "
        "recomendamos comunicarte directamente con la entidad embargante, quien "
        "podra brindarte informacion sobre los pasos a seguir.\n\n"
        "Gracias por comunicarte con nosotros."
    )


@log_execution
def _parse_behavior_vector(obligation: dict[str, Any]) -> list[str]:
    """
    Extract the 24-month payment behavior vector from an obligation.

    Returns a list of symbols such as ["N", "N", "1", "2", "C"], oldest first.
    Returns an empty list when no vector is found.
    """

    for entry in obligation.get("behaviorLiabilities") or []:
        if str(entry.get("behaviorType", "")).upper() == "TWENTY_FOUR_MONTHS":
            description = str(entry.get("description") or "").strip()
            if description:
                return _normalize_behavior_vector(description)
    return []


@log_execution
def _normalize_behavior_vector(raw_vector: Any) -> list[str]:
    """Normalize behavior-vector input into uppercase tokens."""

    if isinstance(raw_vector, str):
        tokens = raw_vector.split()
    elif isinstance(raw_vector, list):
        tokens = raw_vector
    else:
        return []

    normalized: list[str] = []
    for token in tokens:
        symbol = str(token or "").strip().upper()
        if symbol:
            normalized.append(symbol)
    return normalized


@log_execution
def _extract_behavior_vector_from_mora_payload(payload: Any) -> list[str]:
    """Read a propagated ASO behavior vector from a hallazgo/state payload."""

    if not isinstance(payload, dict):
        return []

    return _normalize_behavior_vector(payload.get("behavior_vector"))


@log_execution
def _resolve_active_behavior_vector(
    obligation: dict[str, Any],
    back_data_entry: dict[str, Any],
) -> list[str]:
    """Resolve the active-product behavior vector from ASO or propagated back-data."""

    behavior_vector = _parse_behavior_vector(obligation)
    if behavior_vector:
        return behavior_vector

    # First, look for explicit behavior_vector payloads in any hallazgo value.
    for hallazgo in back_data_entry.get("hallazgos") or []:
        behavior_vector = _extract_behavior_vector_from_mora_payload(
            hallazgo.get("valor")
        )
        if behavior_vector:
            return behavior_vector

    # Backward-compatible path when hallazgo.tipo is explicitly activo_mora.
    for hallazgo in back_data_entry.get("hallazgos") or []:
        if str(hallazgo.get("tipo") or "").strip() != "activo_mora":
            continue
        behavior_vector = _extract_behavior_vector_from_mora_payload(
            hallazgo.get("valor")
        )
        if behavior_vector:
            return behavior_vector

    state_dict = back_data_entry.get("state_dict") or {}
    # Prefer activo_mora entry, but scan all state values as fallback.
    behavior_vector = _extract_behavior_vector_from_mora_payload(
        state_dict.get("activo_mora")
    )
    if behavior_vector:
        return behavior_vector

    for value in state_dict.values():
        behavior_vector = _extract_behavior_vector_from_mora_payload(value)
        if behavior_vector:
            return behavior_vector

    return []


@log_execution
def _get_max_mora_level(behavior_vector: list[str]) -> int:
    """
    Return the maximum mora level in the vector.

    N=0, 1-6=numeric mora level, C=7 (castigado).
    """

    level_map = {"N": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "C": 7}
    return max(
        (level_map.get(symbol.upper(), 0) for symbol in behavior_vector),
        default=0,
    )


@log_execution
def _cross_validate_mora(
    product: dict[str, Any],
    behavior_vector: list[str],
) -> bool:
    """
    Return True when BOTH the CSV and the JSON behavior vector confirm mora
    for an activo product (not Cuenta de Ahorros).

    Conditions:
    - product_group == "activo"
    - default_flag == True  (CSV source)
    - at least one delinquency symbol (1-6/C) in the vector  (JSON source)
    """

    if product.get("product_group") != "activo":
        return False
    if not product.get("default_flag"):
        return False
    return any(str(symbol).upper() in {"1", "2", "3", "4", "5", "6", "C"} for symbol in behavior_vector)


@log_execution
def _extract_current_mora_profile(behavior_vector: list[str]) -> dict[str, int | None]:
    """Return mora metrics only for the trailing active delinquency segment."""

    normalized_vector = _normalize_behavior_vector(behavior_vector)
    delinquency_symbols = {"1", "2", "3", "4", "5", "6", "C"}
    level_map = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "C": 7}

    if not normalized_vector:
        return {
            "mora_months": 0,
            "max_level": 0,
            "start_index": None,
            "end_index": None,
        }

    end_index = len(normalized_vector) - 1
    if normalized_vector[end_index] not in delinquency_symbols:
        return {
            "mora_months": 0,
            "max_level": 0,
            "start_index": None,
            "end_index": None,
        }

    start_index = end_index
    while start_index >= 0 and normalized_vector[start_index] in delinquency_symbols:
        start_index -= 1
    start_index += 1

    segment = normalized_vector[start_index : end_index + 1]
    max_level = max((level_map.get(symbol, 0) for symbol in segment), default=0)
    return {
        "mora_months": len(segment),
        "max_level": max_level,
        "start_index": start_index,
        "end_index": end_index,
    }


@log_execution
def _active_vector_confirms_mora(
    product: dict[str, Any],
    behavior_vector: list[str],
) -> bool:
    """Return whether an active product has current mora according to the vector."""

    if product.get("product_group") != "activo":
        return False

    mora_profile = _extract_latest_mora_profile(behavior_vector)
    return int(mora_profile.get("mora_months") or 0) > 0


@log_execution
def _extract_latest_mora_profile(behavior_vector: list[str]) -> dict[str, int | None]:
    """Return mora metrics for the latest delinquency period in a 24m behavior vector.

    ``mora_months`` is the contiguous length of the most recent block with
    symbols 1-6/C. ``start_index`` and ``end_index`` refer to vector positions
    (oldest=0, newest=len(vector)-1). ``max_level`` is the highest severity
    level in that block where C maps to 7.
    """

    delinquency_symbols = {"1", "2", "3", "4", "5", "6", "C"}
    level_map = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "C": 7}

    latest_start: int | None = None
    latest_end: int | None = None
    idx = len(behavior_vector) - 1
    while idx >= 0:
        symbol = str(behavior_vector[idx]).upper()
        if symbol in delinquency_symbols:
            latest_end = idx
            start = idx
            while start >= 0 and str(behavior_vector[start]).upper() in delinquency_symbols:
                start -= 1
            latest_start = start + 1
            break
        idx -= 1

    if latest_start is None or latest_end is None:
        return {
            "mora_months": 0,
            "max_level": 0,
            "start_index": None,
            "end_index": None,
        }

    segment = behavior_vector[latest_start : latest_end + 1]
    max_level = max((level_map.get(str(s).upper(), 0) for s in segment), default=0)
    return {
        "mora_months": len(segment),
        "max_level": max_level,
        "start_index": latest_start,
        "end_index": latest_end,
    }


@log_execution
def _add_months_to_date(base: date, months: int) -> date:
    """Return ``base`` shifted forward by ``months`` calendar months."""
    return base + relativedelta(months=months)

@log_execution
def _calculate_permanencia_end(
    mora_months: int,
    payment_date_str: str | None,
) -> date | None:
    """
    Calculate the end date of the negative report permanencia.

    Rules (Colombian banking regulation):
    - permanencia = 2 × mora_months from payment date
    - Maximum permanencia = 4 years (48 months)
    Returns None when the payment date is not available.
    """
    if not payment_date_str:
        return None
    try:
        payment_date = date.fromisoformat(str(payment_date_str)[:10])
    except (ValueError, TypeError):
        return None

    meses_permanencia = min(mora_months * 2, 48)
    return _add_months_to_date(payment_date, meses_permanencia)


@log_execution
def _render_centrales_structured_message(
    message_payload: dict[str, Any],
) -> tuple[str, dict[str, str] | None]:
    """Render a message payload with ``id_msg`` into final text from responses.yml."""

    id_msg = str(message_payload.get("id_msg") or "").strip()
    variables = {k: v for k, v in message_payload.items() if k != "id_msg"}

    # Backward-compatible aliases for legacy templates (id_msg 4/5).
    if id_msg in {"4", "5"}:
        variables.setdefault("tipo_producto", str(variables.get("product_type") or ""))
        variables.setdefault("key_id_last", str(variables.get("last_four") or ""))
        variables.setdefault("motivo_reporte", str(variables.get("motivo") or ""))

    if not id_msg:
        return "", None
    text, option = _load_centrales_response(id_msg, variables)
    return text, option

@log_execution
def _build_mora_negative_report_message(
    product: dict[str, Any],
    obligation: dict[str, Any],
    behavior_vector: list[str],
) -> dict[str, Any]:
    """
    Build the mora-report dictionary mapped to responses.yml.

    The threshold is based on mora-month duration from the latest delinquency
    segment in the 24-month behavior vector:
    - mora_months > 4  (mora > 120 days): id_msg 20 with permanencia details.
    - mora_months <= 4 (mora <= 120 days): id_msg 4 without castigo period.
    """
    mora_profile = _extract_latest_mora_profile(behavior_vector)
    max_level = int(mora_profile["max_level"] or 0)
    mora_months = int(mora_profile["mora_months"] or 0)

    if mora_months <= 0 and not behavior_vector:
        mora_months = int(product.get("default_months_number") or 0)
    if max_level <= 0:
        max_level = _get_max_mora_level(behavior_vector)

    product_type = str(product.get("product_type") or "").strip()
    # Ya usaba el contract_id correctamente; se unifica en el ayudante para
    # que la regla viva en un solo sitio.
    last_four = _last4_contrato(product)

    normalized_vector = _normalize_behavior_vector(behavior_vector)
    classification_id = str(
        (obligation.get("classificationStatus") or {}).get("id", "")
    ).upper()
    # Castigo: hay una 'C' en el vector, o BBVA lo marca (written_off / CAST).
    has_castigo = (
        "C" in normalized_vector
        or bool(product.get("written_off_flag"))
        or classification_id == "CAST"
    )

    if has_castigo:
        motivo = "cartera castigada por incumplimiento en el pago de la obligacion"
    else:
        motivo = "mora en el pago de la obligacion"

    # Castigo (siempre) o mora > 120 dias (>4 meses) -> id_msg 20 con permanencia.
    if has_castigo or mora_months > 4:
        if mora_months * 2 <= 48:
            permanencia_desc = f"{mora_months * 2} meses"
        else:
            permanencia_desc = "4 años"

        # Fecha de inicio del reporte calculada del vector: la ultima posicion
        # es el mes actual y se retrocede hasta el inicio del bloque de mora.
        fecha = ""
        start_index = mora_profile.get("start_index")
        if isinstance(start_index, int) and behavior_vector:
            month_anchor = date.today().replace(day=1)
            months_back = (len(behavior_vector) - 1) - start_index
            if months_back >= 0:
                start_month = _add_months_to_date(month_anchor, -months_back)
                fecha = start_month.strftime("%m/%Y")

        # Retorna la estructura de datos que el engine mapeara contra responses.yml
        return {
            "id_msg": 20,
            "product_type": product_type,
            "last_four": last_four,
            "motivo": motivo,
            "permanencia_desc": permanencia_desc,
            "fecha": fecha,
        }

    # Mora <= 120 dias -> id_msg 4 (sin castigo ni permanencia)
    return {
        "id_msg": 4,
        "product_type": product_type,
        "last_four": last_four,
        "motivo": motivo,
    }

@log_execution
def _build_after_30_days_message() -> str:
    """Build the response used when the embargo update exceeds 30 days."""

    return (
        "## Actualizacion del estado de tu cuenta\n\n"
        "Te informamos que ya realizamos la actualizacion del estado de tu cuenta "
        "ante la central de riesgo.\n\n"
        "Esta informacion podra verse reflejada en un plazo de 24 horas habiles.\n\n"
        "Gracias por comunicarte con nosotros."
    )


@log_execution
def _build_before_30_days_message() -> str:
    """Build the response used when the embargo update is still within 30 days."""

    return (
        "## Actualizacion en proceso\n\n"
        "Te informamos que recibimos la notificacion de desembargo de tu cuenta en BBVA, "
        "ya realizamos la actualizacion del estado y actualmente se encuentra en proceso "
        "de levantamiento en centrales.\n\n"
        "La actualizacion en centrales de riesgo se realizara en el proximo ciclo de "
        "reporte (30 dia mes vencido)."
    )


@log_execution
def _build_no_embargo_correct_message(account_status: str) -> str:
    """Build the response used when there is no embargo and central data matches."""

    return (
        "## Notificacion importante sobre tu cuenta\n\n"
        "Te informamos que tu cuenta no presenta ningun bloqueo y el estado corresponde "
        "al status actual de tu cuenta ante el banco.\n\n"
        "### Estado actual de la cuenta\n\n"
        f"{account_status}\n\n"
        "### Reporte en centrales de riesgo\n\n"
        "La informacion reportada se encuentra acorde con el estado actual de tu cuenta.\n\n"
        "Gracias por comunicarte con nosotros."
    )


@log_execution
def _build_lifted_embargo_message(account_status: str, lifted_at: date) -> str:
    """Build the response used when the embargo was lifted and central data matches."""

    return (
        "## Notificacion importante sobre tu cuenta\n\n"
        f"Te informamos que el embargo sobre tu cuenta ha sido levantado el dia "
        f"{_format_display_date(lifted_at)}.\n\n"
        "### Estado actual de la cuenta\n\n"
        f"{account_status}\n\n"
        "### Reporte en centrales de riesgo\n\n"
        "La informacion reportada se encuentra acorde con el estado actual de tu cuenta."
    )


@log_execution
def _build_active_embargo_message(product: dict[str, Any], account_status: str) -> str:
    """Build the response used when the account remains under an active embargo."""

    embargo_details = product.get("embargo_details", {}) or {}
    embargo_date = _parse_date(embargo_details.get("date"))
    formatted_embargo_date = (
        _format_display_date(embargo_date) if embargo_date is not None else "Sin fecha"
    )

    return (
        "## Notificacion sobre tu cuenta\n\n"
        "Te informamos que actualmente presentas un embargo vigente sobre tu cuenta, "
        "con el siguiente detalle:\n\n"
        f"- **Entidad embargante:** {embargo_details.get('entity_name', 'No disponible')}\n"
        f"- **Numero de embargo:** {embargo_details.get('embargo_number', 'No disponible')}\n"
        f"- **Oficio de embargo:** {embargo_details.get('official_notice', 'No disponible')}\n"
        f"- **Fecha:** {formatted_embargo_date}\n"
        f"- **Monto:** {embargo_details.get('amount', 'No disponible')}\n\n"
        "### Informacion importante\n\n"
        "Este reporte no es negativo. Corresponde al estado actual de tu producto "
        "debido a la medida de embargo.\n\n"
        "El estado de la cuenta se actualizara una vez recibamos el oficio de "
        "desembargo por parte de la entidad correspondiente. Este proceso puede "
        "tomar hasta 30 dias posteriores a su recepcion.\n\n"
        "### Que puedes hacer\n\n"
        "Para gestionar el levantamiento del embargo, te recomendamos comunicarte "
        "directamente con la entidad embargante, quien podra brindarte informacion "
        "sobre los pasos a seguir.\n\n"
        "### Estado actual de la cuenta\n\n"
        f"{account_status}\n\n"
        "Gracias por comunicarte con nosotros."
    )
