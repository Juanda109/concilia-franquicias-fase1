"""Servicios de aplicacion para consultas y validaciones de clientes.

Este modulo concentra los flujos de consulta general, validaciones contra
centrales de riesgo, notificacion y persistencia en OpenSearch.

Nota de mantenimiento: se conserva la logica actual de negocio, incluidos los
nombres de campos esperados por consumidores externos.
"""

from typing import Any

import base64
import os

import pandas as pd
from pandas import DataFrame

from application.customer.send_emails.send_email_service import (
    enviar_correo_extracto,
    enviar_correo_extracto_prueba,
)

from infrastructure.core.logger import bind_correlation, get_logger, log_execution
from infrastructure.core.config import load_env_constants
from infrastructure.entrypoint.api.errors.exceptions import CustomerNotFoundError
from infrastructure.observability.error_audit import schedule_error_report
from infrastructure.observability.trace_audit import schedule_trace_event
from infrastructure.persistence.commercial_info_client import CommercialInfoClient
from infrastructure.persistence.customer_identity_repository import CustomerIdentityRepository
from infrastructure.persistence.opensearch_client import OpenSearchClient

logger = get_logger(__name__)


def _e2e_debug_enabled() -> bool:
    """Whether E2E DEBUG tracing (full inputs/outputs, no masking) is enabled.

    Reads from the merged .env constants (configmap mounts .env as a file), so
    os.getenv alone would NOT see it; falls back to real env vars.
    """

    try:
        value = load_env_constants().get("E2E_DEBUG_TRACE")
    except Exception:  # noqa: BLE001
        value = None
    if value is None:
        value = os.getenv("E2E_DEBUG_TRACE")
    return str(value or "false").strip().casefold() in {"1", "true", "yes", "on"}


def _emit_decision_debug(
    operation: str,
    *,
    request_summary: dict[str, Any] | None = None,
    response_summary: dict[str, Any] | None = None,
) -> None:
    """Emit a DEBUG trace of a decision/comparison step (Postgres vs ASO).

    Fire-and-forget and only when E2E_DEBUG_TRACE is on. No masking: the goal is
    to see the full E2E inputs/outputs used to resolve id_msg/caso.
    """

    if not _e2e_debug_enabled():
        return
    try:
        schedule_trace_event(
            event_type="debug",
            operation=operation,
            outcome="debug",
            request_summary=dict(request_summary or {}),
            response_summary=dict(response_summary or {}),
            tags=["debug", "e2e", "decision"],
        )
    except Exception:  # noqa: BLE001 - observability must never break the flow
        logger.debug("E2E decision debug trace failed op=%s", operation)


def _df_records(df: "DataFrame | None") -> list[dict[str, Any]]:
    """Return the full DataFrame as a list of dict rows (for DEBUG traces)."""

    if df is None:
        return []
    try:
        return df.astype(str).to_dict(orient="records")
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Lectura y normalizacion de informacion de centrales
# ---------------------------------------------------------------------------


def get_behavior_vector(obligation: dict[str, Any]) -> list[str]:
    """Obtiene el vector historico de comportamiento a 24 meses."""

    # Obtiene el arreglo behaviorLiabilities de la obligacion
    behavior_liabilities = obligation.get("behaviorLiabilities") or []

    # Recorre todos los comportamientos historicos
    for item in behavior_liabilities:

        # Busca especificamente el vector de 24 meses
        if item.get("behaviorType") == "TWENTY_FOUR_MONTHS":

            # Obtiene el string:
            # "N N N N 1 2"
            description = item.get("description")

            # Si existe, lo convierte en lista:
            # ["N", "N", "N", "1", "2"]
            if description:
                return _normalize_behavior_vector(description)

    # Si no encuentra vector, retorna lista vacia
    return []


def _normalize_behavior_vector(raw_vector: Any) -> list[str]:
    """Normaliza el vector ASO en tokens uppercase."""

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


def _extract_current_mora_profile(behavior_vector: list[str]) -> dict[str, int | None]:
    """Retorna el bloque de mora mas reciente del vector.

    Toma el ultimo bloque contiguo de simbolos de morosidad (1-6/C),
    saltando los meses "al dia" (N/-) finales. Asi un reporte que se
    mantiene en el vector aunque el ultimo mes ya este al dia sigue
    contando como mora vigente (p.ej. "... 1 2 3 N").
    """

    normalized_vector = _normalize_behavior_vector(behavior_vector)
    delinquency_symbols = {"1", "2", "3", "4", "5", "6", "C"}
    level_map = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "C": 7}

    empty: dict[str, int | None] = {
        "mora_months": 0,
        "max_level": 0,
        "start_index": None,
        "end_index": None,
    }

    if not normalized_vector:
        return empty

    # Ubicar el final del bloque de mora mas reciente (saltando N/- finales).
    end_index = len(normalized_vector) - 1
    while end_index >= 0 and normalized_vector[end_index] not in delinquency_symbols:
        end_index -= 1

    if end_index < 0:
        return empty

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


def _build_active_mora_payload(behavior_vector: list[str]) -> dict[str, Any]:
    """Construye el payload canonico de mora activa basado en el vector ASO."""

    normalized_vector = _normalize_behavior_vector(behavior_vector)
    mora_profile = _extract_current_mora_profile(normalized_vector)
    mora_months = int(mora_profile.get("mora_months") or 0)

    if mora_months <= 0:
        return {}

    return {
        "behavior_vector": normalized_vector,
        "mora_months": mora_months,
        "dias_mora": mora_months * 30,
        "max_level": int(mora_profile.get("max_level") or 0),
    }


def read_json_centrales(commercial_info_response: dict[str, Any]) -> dict[str, Any]:
    """Extrae hallazgos de centrales asociados a obligaciones BBVA."""

    dicci = {}

    # 1. Extraemos 'data' (o un diccionario vacío si no existe)
    data = commercial_info_response.get("data", {})

    # 2. Buscamos 'creditHistory'. Si no existe, usamos 'history' como respaldo.
    # Si ninguno de los dos existe, devuelve un diccionario vacío {}.
    history_node = data.get("creditHistory", data.get("history", {}))

    # 3. Finalmente extraemos 'obligations'
    obligations = history_node.get("obligations", [])

    for obligation in obligations:

        financial_name = (
            obligation.get("financialInstitutionInformation", {})
            .get("name", "")
            .upper()
        )


        # Validacion 1: que sea BBVA
        if "BBVA" in financial_name:

            id_obligation = obligation.get("number")
            lista_hallazgo = {}

            classification_status = (
                obligation.get("classificationStatus", {})
                .get("id")
            )

            vector = get_behavior_vector(obligation)
            active_mora_payload = _build_active_mora_payload(vector)

            # Validacion 1.1: Pasivo Embargado
            if classification_status in ["ACEMB", "INEMB"]:

                lista_hallazgo["pasivo"] = "embargado"

            # Validacion 1.2.1: Activo Castigado

            if len(vector) == 0:
                if classification_status in ["CAST"]:
                    lista_hallazgo["activo_castigado_presente"] = "castigado"

                # Validacion 1.2.2: Activo Reestructurado
                elif classification_status in ["REES"]:
                    lista_hallazgo["activo_reestructurado"] = "reestructurado"

                # Validacion 1.2.3: Activo en mora
                elif classification_status in ["MORA"]:
                    lista_hallazgo["activo_mora"] = "mora"
                    #
            else:

                # Validar ultimo elemento
                if vector[-1] == "C":
                    cantidad_c = 0
                    i = len(vector) - 1

                    # Cuenta C consecutivas desde el final.
                    while i >= 0 and (vector[i] == "C" or str(vector[i]).isdigit()):
                        cantidad_c += 1
                        i -= 1
                    if active_mora_payload:
                        lista_hallazgo["activo_mora"] = active_mora_payload
                    lista_hallazgo["activo_castigado_presente"] = cantidad_c * 2

                elif "C" in vector:

                    ultima_c = len(vector) - 1 - vector[::-1].index("C")
                    hace_cuanto = len(vector) - ultima_c - 1
                    deuda = 0

                    for i in range(ultima_c, -1, -1):
                        valor = vector[i]

                        if valor == "C" or valor.isdigit():
                            deuda += 1
                        else:
                            break

                    lista_hallazgo["activo_castigado_pasado"] = {
                        "meses_desde_castigo": hace_cuanto + 1,
                        "meses_desde_pago": hace_cuanto,
                        "meses_en deuda": deuda,
                        "meses_reportado": deuda * 2,
                    }

                if active_mora_payload:
                    lista_hallazgo["activo_mora"] = active_mora_payload

                if "R" in vector:

                    for i in range(len(vector) - 1, -1, -1):

                        if vector[i] == "R":
                            posicion_desde_final = len(vector) - i
                            lista_hallazgo["activo_reestructurado"] = posicion_desde_final
                            break

            if len(lista_hallazgo) > 0:

                dicci[id_obligation] = lista_hallazgo

    _emit_decision_debug(
        "read_json_centrales",
        request_summary={"aso_commercial_info_response": commercial_info_response},
        response_summary={"centrales_data": dicci},
    )
    return dicci

# ---------------------------------------------------------------------------
# Obtencion de extractos
# ---------------------------------------------------------------------------


def obtener_id_y_fecha_reciente(response):
    """Retorna el id y la fecha de corte del extracto mas reciente."""
    data = response.get("data", []) if response else []

    if not data:
        return None, None

    registro_reciente = max(data, key=lambda x: x["cutOffDate"])
    return registro_reciente["id"], registro_reciente["cutOffDate"]


def obtener_pdf_extracto(contract_id, commercial_info_client):
    """Busca y descarga el PDF de extracto mas reciente para un contrato.

    Los paths de cada familia de producto se toman de la configuracion
    (``CommercialInfoSettings`` / configmap); si el cliente no expone
    ``settings`` se usan los defaults. Placeholders: {contract_id}, {id_extracto}.
    """
    settings = getattr(commercial_info_client, "settings", None)

    def _tpl(attr: str, default: str) -> str:
        value = getattr(settings, attr, None) if settings is not None else None
        return value or default

    productos = [
        {
            "nombre": "prestamos",
            "listado": _tpl(
                "extracto_prestamos_listado",
                "/loans/v1/loans/{contract_id}/financial-statements",
            ),
            "pdf": _tpl(
                "extracto_prestamos_pdf",
                "/loans/v1/loans/{contract_id}/financial-statements/{id_extracto}",
            ),
        },
        {
            "nombre": "cuentas",
            "listado": _tpl(
                "extracto_cuentas_listado",
                "/accounts/v0/accounts/{contract_id}/financial-statements",
            ),
            "pdf": _tpl(
                "extracto_cuentas_pdf",
                "/accounts/v0/accounts/{contract_id}/financial-statements/{id_extracto}",
            ),
        },
        {
            "nombre": "tdc",
            "listado": _tpl(
                "extracto_tdc_listado",
                "/cards/v1/cards/{contract_id}/financial-statements",
            ),
            "pdf": _tpl(
                "extracto_tdc_pdf",
                "/cards/v1/cards/{contract_id}/financial-statements/{id_extracto}",
            ),
        },
        {
            "nombre": "leasing",
            "listado": _tpl(
                "extracto_leasing_listado",
                "/leasings/v0/leasings/{contract_id}/financial-statements",
            ),
            "pdf": _tpl(
                "extracto_leasing_pdf",
                "/leasings/v0/leasings/{contract_id}/financial-statements/{id_extracto}",
            ),
        },
        {
            "nombre": "fondos",
            "listado": _tpl(
                "extracto_fondos_listado",
                "/investment-funds/v0/investment-funds/"
                "{contract_id}/funds/{contract_id}/financial-statements",
            ),
            "pdf": _tpl(
                "extracto_fondos_pdf",
                "/investment-funds/v0/investment-funds/"
                "{contract_id}/funds/{contract_id}/financial-statements/{id_extracto}",
            ),
        },
    ]

    for producto in productos:
        try:
            listado_path = producto["listado"].format(contract_id=contract_id)
            response = commercial_info_client.request_aso(listado_path)

            id_extracto, fecha = obtener_id_y_fecha_reciente(response)

            if not id_extracto:
                continue

            pdf_path = producto["pdf"].format(
                contract_id=contract_id,
                id_extracto=id_extracto,
            )
            pdf_extracto = commercial_info_client.request_aso_pdf(pdf_path)

            return pdf_extracto, fecha

        except Exception:
            continue

    return None, None


# ---------------------------------------------------------------------------
# Construccion de respuestas de negocio
# ---------------------------------------------------------------------------


def build_notificacion_centrales_data(
    centrales_data: dict[str, Any],
    customer_identity_df: DataFrame,
    commercial_info_client: CommercialInfoClient | None = None,
) -> dict[str, Any]:
    """
    EDITAR AQUI: esta funcion recibe los hallazgos crudos de read_json_centrales
    y construye el payload final que se guarda en data de OpenSearch para el
    endpoint /notificacion_centrales.

    - centrales_data: diccionario retornado por read_json_centrales(...).
    - customer_identity_df: DataFrame con todas las columnas y filas del cliente
      consultado en PostgreSQL/CSV.

    Cambia el return de esta funcion para aplicar reglas de negocio,
    renombrar campos, filtrar hallazgos, cruzar contra datos del cliente o
    construir otra estructura.
    """

    if not centrales_data:
        resp = {
            "caso": "sin reporte en centrales",
            "id_msg": 18,
        }
    else:

        if customer_identity_df["adelanto_nomina_flag"].str.lower().eq("true").any():
            resp = {
                "caso": "adelanto de nomina",
                "id_msg": 17,
            }
        else:

            centrales_keys = {
                key_norm
                for key_norm in (_normalize_key_id(key) for key in centrales_data.keys())
                if key_norm
            }
            resp = {
                "caso": "no extracto",
                "id_msg": 17,
            }

            key_id_no_ceros = customer_identity_df["key_id"].map(_normalize_key_id)
            for _, row in customer_identity_df[
                key_id_no_ceros.isin(centrales_keys)
            ].iterrows():

                contract_id = _row_text(row, "contract_id")

                response_pdf, fecha = obtener_pdf_extracto(
                    contract_id,
                    commercial_info_client,
                )

                if response_pdf is None:
                    resp = {
                        "caso": "no extracto",
                        "id_msg": 17,
                    }

                else:

                    user, domain = _row_text(row, "customer_mail").split("@")
                    correo_anonimo = f"{user[:3]}****@{domain}"
                    resp = {
                        "caso": "si extracto",
                        "correo": correo_anonimo,
                        "user_email": fecha,
                        "id_msg": 16,
                    }


                    # LLAMAR FUNCION ENVIAR CORREO
                    # --- Envio real -------------------------------------------------
                    # Quedan disponibles las variables:
                    # nombre_cliente, producto, fecha, correo y el adjunto en base64
                    # (el adjunto es opcional). Una vez disponibles, descomenta:

                    # enviar_correo_extracto(
                    #     nombre_cliente=_row_text(row, "customer_name"),
                    #     producto=_row_text(row, "commercial_product_desc"),
                    #     fecha=fecha,
                    #     correo=_row_text(row, "customer_mail"),
                    #     adjunto_base64=adjunto_base64,
                    # )

                    # --- Envio de PRUEBA (testing) ----------------------------------
                    # Poner MAIL_ENABLED=true en el .env para que salga el correo.
                    # enviar_correo_extracto_prueba("tu.correo.personal@gmail.com")

    return resp


# ---------------------------------------------------------------------------
# FASE 2 del flujo 3 (notificacion): analisis del producto elegido
# ---------------------------------------------------------------------------


def _format_fecha_ddmmaaaa(fecha: Any) -> str:
    """Formatea una fecha ISO (YYYY-MM-DD) del ASO a DD/MM/AAAA. Best-effort."""

    raw = str(fecha or "").strip()
    if not raw:
        return ""
    # Tomar solo la parte de fecha si viene con hora.
    date_part = raw.split("T")[0].split(" ")[0]
    parts = date_part.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        y, m, d = parts
        return f"{d.zfill(2)}/{m.zfill(2)}/{y}"
    return raw


def _anonimizar_correo(correo: str) -> str:
    """Devuelve el correo anonimizado (abc****@dominio) para mostrar en el chat."""

    valor = str(correo or "").strip()
    if "@" not in valor:
        return ""
    user, _, domain = valor.partition("@")
    return f"{user[:3]}****@{domain}"


def _extract_pdf_base64_from_aso(raw: Any) -> str | None:
    """Extrae el PDF (como base64) de la respuesta del ASO.

    El ASO devuelve el extracto en una respuesta multipart
    (``--<boundary> ... Content-Type: application/pdf ...``). Este helper es
    best-effort: localiza la parte application/pdf y devuelve su contenido en
    base64. Si la parte ya viene en base64 (Content-Transfer-Encoding: base64)
    la retorna tal cual; si no, codifica los bytes crudos.
    """

    if raw is None:
        return None
    data = raw if isinstance(raw, (bytes, bytearray)) else str(raw).encode("utf-8", "replace")
    stripped = data.lstrip()
    # Si no parece multipart, asumimos que ya es el binario del PDF.
    if not stripped.startswith(b"--"):
        try:
            return base64.b64encode(data).decode("ascii")
        except Exception:  # noqa: BLE001
            return None

    first_line = stripped.split(b"\n", 1)[0].strip()
    boundary = first_line[2:].strip()  # quitar "--"
    if not boundary:
        return None

    for part in data.split(b"--" + boundary):
        norm = part.replace(b"\r\n", b"\n")
        if b"application/pdf" not in norm.lower():
            continue
        sep = norm.find(b"\n\n")
        if sep == -1:
            continue
        headers = norm[:sep].lower()
        body = norm[sep + 2:].rstrip(b"-\n\r \t")
        if not body:
            continue
        if b"base64" in headers:
            return body.decode("ascii", "ignore").replace("\n", "").strip() or None
        try:
            return base64.b64encode(body).decode("ascii")
        except Exception:  # noqa: BLE001
            return None
    return None


def _enviar_extracto_por_correo(
    *,
    nombre_cliente: str,
    producto: str,
    fecha: str,
    correo: str,
    pdf_multipart: Any,
) -> None:
    """Envia el extracto al correo real del cliente con el PDF adjunto.

    El gate ``MAIL_ENABLED`` lo aplica ``enviar_correo_extracto`` (modo mock si
    esta apagado). No propaga excepciones para no romper el flujo.
    """

    try:
        adjunto_base64 = _extract_pdf_base64_from_aso(pdf_multipart)
        enviar_correo_extracto(
            nombre_cliente=nombre_cliente,
            producto=producto,
            fecha=fecha,
            correo=correo,
            adjunto_base64=adjunto_base64,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Fallo enviando el extracto por correo (continuando) correo=%s",
            _anonimizar_correo(correo),
        )


def build_notificacion_producto_data(
    *,
    customer_identity_df: DataFrame,
    key_id: str,
    commercial_info_client: CommercialInfoClient | None = None,
) -> dict[str, Any]:
    """FASE 2: analiza el producto elegido del flujo 3 (notificacion).

    Reglas (por el producto seleccionado):
      1. adelanto de nomina (flag de la fila)  -> id_msg 17 (PQRS), sin importar extracto.
      2. si no, ¿tiene extracto? (ASO)
           - no  -> id_msg 17 (PQRS).
           - si  -> id_msg 16 (fecha DD/MM/AAAA + correo anon) + envio del extracto por correo.
    """

    target_key = _normalize_key_id(key_id)
    if not target_key:
        logger.warning("notificacion fase 2: producto no encontrado key_id=%s", key_id)
        return {"caso": "producto no encontrado", "id_msg": 17}

    rows = customer_identity_df[
        customer_identity_df["key_id"].map(_normalize_key_id) == target_key
    ]
    if rows.empty:
        logger.warning("notificacion fase 2: producto no encontrado key_id=%s", target_key)
        return {"caso": "producto no encontrado", "id_msg": 17}

    row = rows.iloc[0]

    # 1) Adelanto de nomina (por el flag de la fila del producto elegido).
    if _flag_is_true(row, "adelanto_nomina_flag"):
        return {"caso": "adelanto de nomina", "id_msg": 17}

    # 2) ¿Extracto del producto en el ASO?
    contract_id = _row_text(row, "contract_id")
    response_pdf, fecha = obtener_pdf_extracto(contract_id, commercial_info_client)

    if response_pdf is None:
        return {"caso": "no extracto", "id_msg": 17}

    # 3) Con extracto -> notificacion por extracto (msg 16) + envio del correo.
    fecha_fmt = _format_fecha_ddmmaaaa(fecha)
    customer_mail = _row_text(row, "customer_mail")

    _enviar_extracto_por_correo(
        nombre_cliente=_row_text(row, "customer_name"),
        producto=_row_text(row, "commercial_product_desc"),
        fecha=fecha_fmt,
        correo=customer_mail,
        pdf_multipart=response_pdf,
    )

    return {
        "caso": "si extracto",
        "fecha": fecha_fmt,
        "correo": _anonimizar_correo(customer_mail),
        "id_msg": 16,
    }


@log_execution
async def notificacion_producto_customer(
    *,
    customer_id: str,
    key_id: str,
    identity_repository: CustomerIdentityRepository,
    commercial_info_client: CommercialInfoClient,
) -> dict[str, Any]:
    """FASE 2 orquestada: analiza el producto elegido del cliente."""

    normalized_customer_id = customer_id.strip()
    customer_identity_df = identity_repository.read_customer_identity_df(
        customer_id=normalized_customer_id,
    )
    identity = identity_repository.find_by_customer_id_in_df(
        customer_id=normalized_customer_id,
        customer_identity_df=customer_identity_df,
    )
    if identity is None:
        logger.warning("Customer data not found customer_id=%s", normalized_customer_id)
        raise CustomerNotFoundError(normalized_customer_id)

    return build_notificacion_producto_data(
        customer_identity_df=customer_identity_df,
        key_id=key_id,
        commercial_info_client=commercial_info_client,
    )


@log_execution
async def process_notificacion_producto_request(
    *,
    customer_id: str,
    workflow: str,
    key_id: str,
    identity_repository: CustomerIdentityRepository,
    commercial_info_client: CommercialInfoClient,
    opensearch_client: OpenSearchClient,
    correlation_id: str | None = None,
    run_id: str | None = None,
) -> None:
    """Analiza el producto elegido (fase 2) y persiste el resultado en OpenSearch."""

    bind_correlation(conversation_id=correlation_id, customer_id=customer_id)
    try:
        data = await notificacion_producto_customer(
            customer_id=customer_id,
            key_id=key_id,
            identity_repository=identity_repository,
            commercial_info_client=commercial_info_client,
        )
        logger.info(
            "DECISION notificacion_producto (fase 2) customer_id=%s key_id=%s id_msg=%s caso=%s",
            customer_id,
            key_id,
            data.get("id_msg"),
            data.get("caso"),
        )
        await opensearch_client.update_client_control_data(
            customer_id=customer_id.strip(),
            workflow=workflow.strip(),
            data=data,
            status="ok",
            run_id=run_id,
        )
    except Exception as error:
        logger.exception(
            "Failed to process notificacion_producto background task customer_id=%s workflow=%s",
            customer_id,
            workflow,
        )
        schedule_error_report(
            error=error,
            source="process_notificacion_producto_request",
            conversation_id=correlation_id,
            extra_context={
                "customer_id": customer_id,
                "workflow": workflow,
                "key_id": key_id,
                "operation": "notificacion_producto",
            },
        )
        try:
            await opensearch_client.update_client_control_data(
                customer_id=customer_id.strip(),
                workflow=workflow.strip(),
                status="error",
                run_id=run_id,
                error=_build_back_data_error(error),
            )
        except Exception:
            logger.exception(
                "Failed to write ERROR envelope for notificacion_producto customer_id=%s workflow=%s",
                customer_id,
                workflow,
            )


def read_flags_table(df: pd.DataFrame) -> dict:
    """
    Retorna un diccionario con solo las banderas que estan en True.

    Formato:
    {
        key_id: ["default_flag", "written_off_flag"]
    }
    """

    flag_columns = [
        "default_flag",
        "seizure_flag",
        "written_off_flag",
        "restructured_flag",
        "off_loaded_portfolio_flag",
    ]

    result = {}

    for _, row in df.iterrows():
        key_id = _row_text(row, "key_id")

        if not key_id:
            continue

        true_flags = [flag for flag in flag_columns if _flag_is_true(row, flag)]

        # Solo agrega registros con al menos una bandera en True.
        if true_flags:
            result[key_id] = true_flags

    return result


# ---------------------------------------------------------------------------
# Helpers de DataFrame y normalizacion
# ---------------------------------------------------------------------------


def _row_text(row: pd.Series, column: str, default: str = "") -> str:
    """Return a normalized string value from a DataFrame row."""

    value = row.get(column, default)

    if pd.isna(value):
        return default

    return str(value).strip()


def _flag_is_true(row: pd.Series, column: str) -> bool:
    """Return whether a row flag is enabled, tolerating missing CSV columns."""

    return _row_text(row, column).lower() in {"t", "true", "1", "yes", "si"}


def _derive_motivo_reporte(row: pd.Series) -> str:
    """Derive the report reason text from the customer status flags.

    The source table has no free-text reason column, so the reason is inferred
    from the boolean flags in ``ada_info_detail``.
    """

    if _flag_is_true(row, "written_off_flag"):
        return "cartera castigada por impago"
    if _flag_is_true(row, "default_flag"):
        return "mora en tu obligación"
    if _flag_is_true(row, "restructured_flag"):
        return "reestructuración de tu obligación"
    return ""


def _extract_given_names(
    customer_name: str,
    first_last_name: str,
    second_last_name: str,
) -> str:
    """Return only the given names (nombres de pila) in Title Case.

    Removes the trailing surname tokens (``first_last_name`` and
    ``second_last_name``) from ``customer_name``. Example:
    "NELSON DE JESUS GONZALEZ HOYOS" - {GONZALEZ, HOYOS} -> "Nelson De Jesus".
    Returns "" when no given names can be isolated (e.g. legal entities).
    """

    full_name = (customer_name or "").strip()
    if not full_name:
        return ""

    surname_tokens = {
        token.upper()
        for surname in (first_last_name, second_last_name)
        for token in (surname or "").split()
    }

    tokens = full_name.split()
    end = len(tokens)
    while end > 0 and tokens[end - 1].upper() in surname_tokens:
        end -= 1

    given_tokens = tokens[:end]
    if not given_tokens:
        return ""

    return " ".join(token.capitalize() for token in given_tokens)


@log_execution
def get_customer_display_name(
    *,
    customer_id: str,
    identity_repository: CustomerIdentityRepository,
) -> str:
    """Return the customer given names from PostgreSQL (ada_info_detail).

    Uses a targeted query filtered by ``customer_id`` (no full-table scan) and
    returns only the nombres de pila. Returns "" when the customer or name is
    not available. Never raises: greeting resolution must stay best-effort.
    """

    try:
        customer_identity_df = identity_repository.read_customer_identity_df(
            customer_id=customer_id,
        )
    except Exception:
        logger.exception(
            "Customer display-name lookup failed customer_id=%s", customer_id
        )
        return ""

    if customer_identity_df is None or customer_identity_df.empty:
        return ""

    row = customer_identity_df.iloc[0]
    return _extract_given_names(
        _row_text(row, "customer_name"),
        _row_text(row, "first_last_name"),
        _row_text(row, "second_last_name"),
    )


def _row_int(row: pd.Series, column: str, default: int = 0) -> int:
    """Return an integer from a row value that may come as 540 or 540.0."""

    value = _row_text(row, column)

    if not value:
        return default

    try:
        return int(value)
    except ValueError:
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return default


def _normalize_customer_id(customer_id: str) -> str:
    normalized_customer_id = customer_id.strip().lstrip("0")
    return normalized_customer_id or "0"


def _customer_rows(customer_identity_df: DataFrame, customer_id: str) -> DataFrame:
    customer_id_values = customer_identity_df["customer_id"].astype(str).str.strip()
    normalized_customer_id = _normalize_customer_id(customer_id)

    return customer_identity_df[
        (customer_id_values == customer_id.strip())
        | (customer_id_values.map(_normalize_customer_id) == normalized_customer_id)
    ]


def _normalize_key_id(value: Any) -> str:
    """Cast key IDs to text and trim outer zero padding from numeric values."""

    text = "" if value is None else str(value).strip()
    if not text:
        return ""

    if text.isdigit():
        return text.strip("0") or "0"

    return text


def _normalize_central_data(value: Any) -> dict[str, Any]:
    """Normalize central-risk findings into a single dictionary."""

    if isinstance(value, dict):
        return value

    if isinstance(value, list):
        normalized: dict[str, Any] = {}
        for item in value:
            if isinstance(item, dict):
                normalized.update(item)
        return normalized

    return {}


def _append_validation(
    validation: dict[str, Any],
    validation_type: str,
    value: Any,
    id_msg: int,
) -> None:
    """Append a validation using stable field names for OpenSearch mappings."""

    validation["hallazgos"].append(
        {
            "tipo": validation_type,
            "id_msg": id_msg,
            "valor": value,
        }
    )

def _lookup_embargo_data_for_contract(
    *,
    contract_id: str,
    embargo_repository: CustomerIdentityRepository | None,
    cache: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    """
    Fetch DEM embargo data per contract_id from repository with per-request cache.

    A repository error intentionally propagates to the caller. Treating an
    unavailable DEM query as an empty result would incorrectly report that the
    contract has no embargo.
    """
    normalized_contract_id = (contract_id or "").strip()
    if not normalized_contract_id or embargo_repository is None:
        return []

    if normalized_contract_id in cache:
        return cache[normalized_contract_id]

    embargo_data = embargo_repository.read_embargo_join_by_contract_id(
        contract_id=normalized_contract_id
    )

    # Compatibilidad defensiva para implementaciones antiguas del repositorio.
    if isinstance(embargo_data, dict):
        embargo_data = [embargo_data] if embargo_data else []

    cache[normalized_contract_id] = embargo_data
    return embargo_data


def build_data_from_customer_df_and_centrales(
    customer_identity_df: DataFrame,
    centrales_data: dict[str, Any],
    customer_id: str,
    embargo_repository: CustomerIdentityRepository | None = None,
) -> dict[str, Any]:
    """
    EDITAR AQUI: esta es la funcion pensada para cruzar la tabla CSV mock
    con el diccionario que retorna read_json_centrales.

    - customer_identity_df: DataFrame completo leido desde datos_ada_*.csv.
    - centrales_data: diccionario retornado por read_json_centrales(...).
    - customer_id: ID recibido por la API. El for de esta funcion solo recorre
      las filas de este cliente.

    Cambia el return de esta funcion para construir el diccionario final que
    necesitas devolver en la API.
    """

    customer_df = _customer_rows(customer_identity_df, customer_id)

    dicci_centrales_data = {
        _normalize_key_id(key): value for key, value in centrales_data.items()
    }
    list_validacion = []
    embargo_cache: dict[str, list[dict[str, str]]] = {}

    contratos_procesados = set()

    for _, row in customer_df.iterrows():
        key_id = _row_text(row, "key_id")

        if not key_id or _row_text(row, "contract_status_type_desc") in ["CANCELADO", "CANCELADA"]  or _row_text(row, "account_status_type_desc") in ["INACTIVE", "CANCELADA"]:
            continue

        contract_id = _row_text(row, "contract_id")

        if contract_id:
            if contract_id in contratos_procesados:
                continue
            contratos_procesados.add(contract_id)

        central_data = _normalize_central_data(
            dicci_centrales_data.get(_normalize_key_id(key_id), {})
        )
        dicci_validacion = {
            "key_id": key_id,
            "contract_id": contract_id,
            "commercial_product_desc": _row_text(row, "commercial_product_desc")
            or "Producto financiero",
            "origin_flag": _row_text(row, "origin_flag"),
            "hallazgos": [],
        }

        if _row_text(row, "origin_flag") == "PASIVE":
            # Caso 2 (Embargos)
            # DEM es la fuente BBVA. Centrales se usa exclusivamente para
            # identificar una discrepancia con esa fuente.
            has_central_pasivo = bool(central_data.get("pasivo"))

            embargo_data = _lookup_embargo_data_for_contract(
                contract_id=contract_id,
                embargo_repository=embargo_repository,
                cache=embargo_cache,
            )
            dem_folios = [
                (folio, str(folio.get("dem_estado") or "").strip().upper())
                for folio in embargo_data
            ]
            dem_embargo_folios = [
                folio for folio, dem_estado in dem_folios if dem_estado == "A"
            ]
            has_dem_embargo = bool(dem_embargo_folios)
            has_dem_desembargo = bool(dem_folios) and all(
                dem_estado == "D" for _, dem_estado in dem_folios
            )

            # Caso 2.1: embargo confirmado por DEM y centrales.
            # Si hay A y D para el contrato, A prevalece y solo se muestran
            # los folios vigentes (A).
            if has_dem_embargo and has_central_pasivo:
                id_msg = 12
                lista_oficios = []
                for folio in dem_embargo_folios:
                    lista_oficios.append({
                        "nombre_entidad": folio.get("emb_juzgado"),
                        "numero_oficio": folio.get("emb_nro_ofic"),
                        "fecha_oficio": folio.get("emb_fecha_ofic"),
                        "valor_pago": str(folio.get("emb_imp_total")),
                    })

                _append_validation(dicci_validacion, "embargada", lista_oficios, id_msg)

            # Caso 2.2: desembargo confirmado por DEM y sin embargo en
            # centrales. Se muestran todos los folios D del contrato.
            elif has_dem_desembargo and not has_central_pasivo:
                id_msg = 11
                status_cuenta = _row_text(row, "contract_status_type_desc")
                lista_desembargos = []
                for folio in embargo_data:
                    lista_desembargos.append(
                        {
                            "nombre_entidad": folio.get("emb_juzgado"),
                            "numero_oficio": folio.get("emb_nro_ofic"),
                            "fecha_oficio": folio.get("emb_fecha_ofic"),
                            "valor_pago": str(folio.get("emb_imp_total")),
                            "fecha_desembargo": folio.get("dem_timest_umo"),
                            "status": status_cuenta,
                        }
                    )

                _append_validation(
                    dicci_validacion,
                    "Cuenta Desembargada",
                    lista_desembargos,
                    id_msg,
                )

            # Caso 2.3: cualquier desacuerdo entre DEM y centrales. Incluye
            # DEM no concluyente cuando centrales reporta embargo.
            elif has_dem_embargo or has_dem_desembargo or has_central_pasivo:
                id_msg = 13
                _append_validation(
                    dicci_validacion,
                    "embargada solo centrales",
                    "Pendiente Actualizar Centrales",
                    id_msg,
                )

            # Caso 2.4: DEM no confirma embargo/desembargo y centrales no
            # reporta embargo.
            else:
                id_msg = 1
                _append_validation(
                    dicci_validacion,
                    "embargada",
                    "Status Actualizado, sin embargo",
                    id_msg,
                )

        else:

            # Caso 1 (Cartera Vendida)
            if _flag_is_true(row, "off_loaded_portfolio_flag"):

                dicci_vendida = {}
                dicci_vendida["comprador"] = _row_text(row, "buyer_name")

                # PONER AQUI EL VALIDADOR de si entregan la info de los nuevos acreedores o no.
                tenemos_info = False
                if tenemos_info:
                    id_msg = 3
                    dicci_vendida["telefono"] = "falta"
                    dicci_vendida["direccion"] = "falta"
                    _append_validation(
                        dicci_validacion,
                        "vendida con info",
                        dicci_vendida,
                        id_msg,
                    )
                else:
                    id_msg = 19
                    _append_validation(
                        dicci_validacion,
                        "vendida sin info",
                        dicci_vendida,
                        id_msg,
                    )

            else:

                # Caso 3 (Activos)
                # Caso 3.1 (reestructurado)
                # Caso 3.1.1 (reestructura igual)
                """if _flag_is_true(row, "restructured_flag") and central_data.get("activo_reestructurado"):
                    _append_validation(dicci_validacion, "activo_reestructurado", central_data.get("activo_reestructurado"))

                # Caso 3.1.1 (reestructura solo BBVA)
                elif _flag_is_true(row, "restructured_flag"):
                    _append_validation(dicci_validacion, "activo_reestructurado", "No aparece en Centrales")

                # Caso 3.1.1 (reestructura solo centrales)
                elif central_data.get("activo_reestructurado"):
                    _append_validation(dicci_validacion, "activo_reestructurado", "No aparece en BBVA")

                """

                # Caso 3 (Activos): castigo / mora / discrepancia.
                # Regla: un unico hallazgo por producto.
                #   - Castigo (C en centrales) + written_off_flag -> id_msg 20 (siempre).
                #   - Mora (centrales) + default_flag -> 4 (<=120d) / 20 (>120d).
                #   - Cualquier desincronia centrales<->BBVA -> id_msg 99 (Formulario PQRS).
                wo_flag = _flag_is_true(row, "written_off_flag")
                default_flag = _flag_is_true(row, "default_flag")
                has_castigo_central = bool(
                    central_data.get("activo_castigado_presente")
                    or central_data.get("activo_castigado_pasado")
                )
                central_mora = central_data.get("activo_mora")
                has_mora_central = bool(central_mora)

                if wo_flag and has_castigo_central:
                    # Castigo confirmado (BBVA + centrales) -> id_msg 20 (siempre).
                    dicci_castigo = {
                        "tipo_producto": _row_text(row, "commercial_product_desc"),
                        "motivo_reporte": _derive_motivo_reporte(row),
                        "fecha_inicio_mora": _row_text(row, "default_date"),
                    }
                    if isinstance(central_mora, dict):
                        dicci_castigo["mora_months"] = central_mora.get("mora_months")
                        dicci_castigo["dias_mora"] = str(
                            central_mora.get("dias_mora") or ""
                        )
                        dicci_castigo["behavior_vector"] = (
                            central_mora.get("behavior_vector") or []
                        )
                    _append_validation(
                        dicci_validacion, "activo castigado", dicci_castigo, 20
                    )

                elif default_flag and has_mora_central:
                    # Mora confirmada (BBVA + centrales) -> 4 (<=120d) / 20 (>120d).
                    mora_months = 0
                    if isinstance(central_mora, dict):
                        try:
                            mora_months = int(central_mora.get("mora_months") or 0)
                        except (ValueError, TypeError):
                            mora_months = 0

                    id_msg = 20 if mora_months > 4 else 4
                    dicci_mora = {
                        "tipo_producto": _row_text(row, "commercial_product_desc"),
                        "motivo_reporte": _derive_motivo_reporte(row),
                    }
                    if isinstance(central_mora, dict):
                        dicci_mora["dias_mora"] = str(
                            central_mora.get("dias_mora") or ""
                        )
                        dicci_mora["mora_months"] = mora_months
                        dicci_mora["behavior_vector"] = (
                            central_mora.get("behavior_vector") or []
                        )
                    _append_validation(
                        dicci_validacion, "activo_mora", dicci_mora, id_msg
                    )

                elif (
                    wo_flag
                    or default_flag
                    or has_castigo_central
                    or has_mora_central
                ):
                    # Discrepancia: centrales y las flags de BBVA no coinciden
                    # (mora/castigo en centrales sin flag, o flag sin respaldo en el
                    # vector) -> id_msg 99 (flujo de Formulario PQRS).
                    _append_validation(
                        dicci_validacion,
                        "discrepancia centrales",
                        "Revision especializada requerida",
                        99,
                    )

        if dicci_validacion["hallazgos"]:
            list_validacion.append(dicci_validacion)
        else:
            id_msg = 1
            _append_validation(
                dicci_validacion,
                _row_text(row, "commercial_product_desc"),
                "Al dia",
                id_msg,
            )
            list_validacion.append(dicci_validacion)

    decision = [
        (v.get("key_id"), h.get("id_msg"))
        for v in list_validacion
        for h in v.get("hallazgos", [])
    ]
    logger.info(
        "DECISION consultar customer_id=%s validaciones=%s id_msgs=%s",
        customer_id,
        len(list_validacion),
        decision,
    )

    _emit_decision_debug(
        "build_data_from_customer_df_and_centrales",
        request_summary={
            "customer_id": customer_id,
            "centrales_data": dicci_centrales_data,
            "customer_rows_full": _df_records(customer_df),
        },
        response_summary={"validaciones": list_validacion, "id_msgs": decision},
    )
    return {
        # "hallazgos_centrales": dicci_centrales_data,
        # "registros_tabla": dicci_csv,
        "validaciones": list_validacion,
    }


def build_consultar_data(
    commercial_info_response: dict[str, Any],
    customer_identity_df: DataFrame,
    customer_id: str,
    embargo_repository: CustomerIdentityRepository | None = None,
) -> dict[str, Any]:
    """
    Select the piece of the external API response returned by this endpoint.
    """

    tabla_y_centrales_data = build_data_from_customer_df_and_centrales(
        customer_identity_df=customer_identity_df,
        centrales_data=read_json_centrales(commercial_info_response),
        customer_id=customer_id,
        embargo_repository=embargo_repository,
    )

    data = commercial_info_response.get("data", {})
    customer = data.get("customer", {})
    identity_document = customer.get("identityDocument", {})
    history = data.get("history", {})
    score_items = history.get("score") or []
    score = score_items[0] if score_items else {}

    return {
        "fullname": customer.get("fullname"),
        "document_number": identity_document.get("documentNumber"),
        "document_type": identity_document.get("documentType", {}).get("description"),
        "credit_score": score.get("creditScore"),
        "hallazgos": tabla_y_centrales_data,
    }


def _select_latest_by_contract_register_date(df: DataFrame):
    """Return the single row with the most recent contract_register_date.

    Safe parsing: rows with unparseable/empty dates are ignored for the max;
    if none is parseable, falls back to the first row (stable).
    """

    try:
        dates = pd.to_datetime(
            df["contract_register_date"], errors="coerce"
        ).reset_index(drop=True)
        if dates.notna().any():
            return df.iloc[int(dates.idxmax())]
    except Exception:  # noqa: BLE001 - never break the flow on date parsing
        pass
    return df.iloc[0]


def build_centrales_no_autorizo_data(
    customer_identity_df: DataFrame,
    customer_id: str,
) -> dict[str, Any]:
    """Build the OpenSearch data payload for central-risk authorization.

    - id_msg 14: hay al menos un producto con ``account_status_type_desc == 'ACTIVO'``.
      Se toma UNA sola fila: la de ``contract_register_date`` MAS RECIENTE, y se
      devuelve ``tipo=commercial_product_desc``, ``fecha=contract_register_date`` y
      ``contract_id_last4`` (ultimos 4 de ``contract_id``). NO se envia correo.
    - id_msg 15: no hay producto activo -> se escala a PQR (igual que antes).
    """

    customer_df = _customer_rows(customer_identity_df, customer_id)

    if customer_df.empty:
        raise CustomerNotFoundError(customer_id)

    rows_with_flag = customer_df[
        customer_df["account_status_type_desc"].astype(str).str.strip() == "ACTIVO"
    ]

    if rows_with_flag.empty:
        resp_15 = {
            "bandera": "false",
            "id_msg": 15,
            "tipo": "",
        }
        _emit_decision_debug(
            "build_centrales_no_autorizo_data",
            request_summary={"customer_id": customer_id, "rows_activo": 0},
            response_summary=resp_15,
        )
        return resp_15

    selected_row = _select_latest_by_contract_register_date(rows_with_flag)
    contract_id = _row_text(selected_row, "contract_id")

    resp_14 = {
        "bandera": "true",
        "id_msg": 14,
        "tipo": _row_text(selected_row, "commercial_product_desc"),
        "fecha": _row_text(selected_row, "contract_register_date"),
        "contract_id_last4": contract_id[-4:] if contract_id else "",
    }
    _emit_decision_debug(
        "build_centrales_no_autorizo_data",
        request_summary={
            "customer_id": customer_id,
            "rows_activo": int(len(rows_with_flag)),
            "candidatos": _df_records(rows_with_flag),
        },
        response_summary=resp_14,
    )
    return resp_14


# ---------------------------------------------------------------------------
# Casos de uso publicos
# ---------------------------------------------------------------------------


@log_execution
async def consultar_customer(
    *,
    customer_id: str,
    identity_repository: CustomerIdentityRepository,
    commercial_info_client: CommercialInfoClient,
    embargo_repository: CustomerIdentityRepository | None = None,
) -> dict[str, Any]:
    """Return selected commercial data for a customer id."""

    normalized_customer_id = customer_id.strip()
    logger.info("Consulting customer data customer_id=%s", normalized_customer_id)

    customer_identity_df = identity_repository.read_customer_identity_df(
        customer_id=normalized_customer_id,
    )

    identity = identity_repository.find_by_customer_id_in_df(
        customer_id=normalized_customer_id,
        customer_identity_df=customer_identity_df,
    )

    if identity is None:
        logger.warning("Customer data not found customer_id=%s", normalized_customer_id)
        raise CustomerNotFoundError(normalized_customer_id)

    commercial_info_response = commercial_info_client.get_commercial_info(identity)
    return build_consultar_data(
        commercial_info_response=commercial_info_response,
        customer_identity_df=customer_identity_df,
        customer_id=normalized_customer_id,
        embargo_repository=embargo_repository,
    )


@log_execution
async def centrales_no_autorizo_customer(
    *,
    customer_id: str,
    identity_repository: CustomerIdentityRepository,
) -> dict[str, str]:
    """Return central-risk authorization data for a customer id."""

    normalized_customer_id = customer_id.strip()
    logger.info(
        "Consulting centrales_no_autorizo data customer_id=%s",
        normalized_customer_id,
    )

    customer_identity_df = identity_repository.read_customer_identity_df(
        customer_id=normalized_customer_id,
    )
    identity = identity_repository.find_by_customer_id_in_df(
        customer_id=normalized_customer_id,
        customer_identity_df=customer_identity_df,
    )

    if identity is None:
        logger.warning("Customer data not found customer_id=%s", normalized_customer_id)
        raise CustomerNotFoundError(normalized_customer_id)

    return build_centrales_no_autorizo_data(
        customer_identity_df=customer_identity_df,
        customer_id=normalized_customer_id,
    )


@log_execution
async def notificacion_centrales_customer(
    *,
    customer_id: str,
    identity_repository: CustomerIdentityRepository,
    commercial_info_client: CommercialInfoClient,
    embargo_repository: CustomerIdentityRepository | None = None,
) -> dict[str, Any]:
    """FASE 1 del flujo 3 (notificación): listar productos reportados.

    Reutiliza ``build_data_from_customer_df_and_centrales`` para devolver las
    validaciones por producto (mismo formato que /consultar). El agente lista
    los productos con id_msg != 1 y, tras la selección, se llama la FASE 2
    (``/notificacion_centrales_producto``) para analizar el producto elegido.
    """

    normalized_customer_id = customer_id.strip()
    logger.info(
        "Consulting notificacion_centrales data customer_id=%s",
        normalized_customer_id,
    )

    customer_identity_df = identity_repository.read_customer_identity_df(
        customer_id=normalized_customer_id,
    )
    identity = identity_repository.find_by_customer_id_in_df(
        customer_id=normalized_customer_id,
        customer_identity_df=customer_identity_df,
    )

    if identity is None:
        logger.warning("Customer data not found customer_id=%s", normalized_customer_id)
        raise CustomerNotFoundError(normalized_customer_id)

    commercial_info_response = commercial_info_client.get_commercial_info(identity)
    centrales_data = read_json_centrales(commercial_info_response)

    return build_data_from_customer_df_and_centrales(
        customer_identity_df=customer_identity_df,
        centrales_data=centrales_data,
        customer_id=normalized_customer_id,
        embargo_repository=embargo_repository,
    )


# ---------------------------------------------------------------------------
# Tareas de background y persistencia
# ---------------------------------------------------------------------------


def _build_back_data_error(error: Exception) -> dict[str, Any]:
    """Build a compact, safe error envelope for the control table."""

    details = getattr(error, "details", None)
    status_code = None
    if isinstance(details, dict):
        status_code = details.get("status_code")
    return {
        "type": type(error).__name__,
        "status_code": status_code,
        "message": str(error)[:500],
    }


@log_execution
async def process_consultar_customer_request(
    *,
    customer_id: str,
    workflow: str,
    identity_repository: CustomerIdentityRepository,
    commercial_info_client: CommercialInfoClient,
    opensearch_client: OpenSearchClient,
    embargo_repository: CustomerIdentityRepository | None = None,
    correlation_id: str | None = None,
    run_id: str | None = None,
) -> None:
    """Process the customer query and persist the generated JSON in OpenSearch."""

    bind_correlation(conversation_id=correlation_id, customer_id=customer_id)
    try:
        data = await consultar_customer(
            customer_id=customer_id,
            identity_repository=identity_repository,
            commercial_info_client=commercial_info_client,
            embargo_repository=embargo_repository,
        )
        await opensearch_client.update_client_control_data(
            customer_id=customer_id.strip(),
            workflow=workflow.strip(),
            data=data,
            status="ok",
            run_id=run_id,
        )
        logger.info(
            "OpenSearch write OK consultar customer_id=%s workflow=%s run_id=%s",
            customer_id,
            workflow,
            run_id,
        )
    except Exception as error:
        logger.exception(
            "Failed to process consultar background task customer_id=%s workflow=%s",
            customer_id,
            workflow,
        )
        schedule_error_report(
            error=error,
            source="process_consultar_customer_request",
            conversation_id=correlation_id,
            extra_context={
                "customer_id": customer_id,
                "workflow": workflow,
                "operation": "consultar",
            },
        )
        # Always record an ERROR envelope so the agent never serves a stale
        # "no reports" result when the ASO/back-data failed.
        try:
            await opensearch_client.update_client_control_data(
                customer_id=customer_id.strip(),
                workflow=workflow.strip(),
                status="error",
                run_id=run_id,
                error=_build_back_data_error(error),
            )
        except Exception:
            logger.exception(
                "Failed to write ERROR envelope for consultar customer_id=%s workflow=%s",
                customer_id,
                workflow,
            )


@log_execution
async def process_notificacion_centrales_request(
    *,
    customer_id: str,
    workflow: str,
    identity_repository: CustomerIdentityRepository,
    commercial_info_client: CommercialInfoClient,
    opensearch_client: OpenSearchClient,
    correlation_id: str | None = None,
    run_id: str | None = None,
    embargo_repository: CustomerIdentityRepository | None = None,
) -> None:
    """Process central-risk findings and persist the result in OpenSearch."""

    bind_correlation(conversation_id=correlation_id, customer_id=customer_id)
    try:
        data = await notificacion_centrales_customer(
            customer_id=customer_id,
            identity_repository=identity_repository,
            commercial_info_client=commercial_info_client,
            embargo_repository=embargo_repository,
        )
        logger.info(
            "DECISION notificacion_centrales (fase 1) customer_id=%s validaciones=%s",
            customer_id,
            len(data.get("validaciones", [])),
        )
        await opensearch_client.update_client_control_data(
            customer_id=customer_id.strip(),
            workflow=workflow.strip(),
            data=data,
            status="ok",
            run_id=run_id,
        )
        logger.info(
            "OpenSearch write OK notificacion_centrales customer_id=%s workflow=%s run_id=%s",
            customer_id,
            workflow,
            run_id,
        )
    except Exception as error:
        logger.exception(
            "Failed to process notificacion_centrales background task customer_id=%s workflow=%s",
            customer_id,
            workflow,
        )
        schedule_error_report(
            error=error,
            source="process_notificacion_centrales_request",
            conversation_id=correlation_id,
            extra_context={
                "customer_id": customer_id,
                "workflow": workflow,
                "operation": "notificacion_centrales",
            },
        )
        try:
            await opensearch_client.update_client_control_data(
                customer_id=customer_id.strip(),
                workflow=workflow.strip(),
                status="error",
                run_id=run_id,
                error=_build_back_data_error(error),
            )
        except Exception:
            logger.exception(
                "Failed to write ERROR envelope for notificacion_centrales customer_id=%s workflow=%s",
                customer_id,
                workflow,
            )


@log_execution
async def process_centrales_no_autorizo_request(
    *,
    customer_id: str,
    workflow: str,
    identity_repository: CustomerIdentityRepository,
    opensearch_client: OpenSearchClient,
    correlation_id: str | None = None,
    run_id: str | None = None,
) -> None:
    """Process central-risk authorization and persist the result in OpenSearch."""

    bind_correlation(conversation_id=correlation_id, customer_id=customer_id)
    try:
        data = await centrales_no_autorizo_customer(
            customer_id=customer_id,
            identity_repository=identity_repository,
        )
        logger.info(
            "DECISION centrales_no_autorizo customer_id=%s id_msg=%s bandera=%s",
            customer_id,
            data.get("id_msg"),
            data.get("bandera"),
        )
        await opensearch_client.update_client_control_data(
            customer_id=customer_id.strip(),
            workflow=workflow.strip(),
            data=data,
            status="ok",
            run_id=run_id,
        )
        logger.info(
            "OpenSearch write OK centrales_no_autorizo customer_id=%s workflow=%s run_id=%s",
            customer_id,
            workflow,
            run_id,
        )
    except Exception as error:
        logger.exception(
            "Failed to process centrales_no_autorizo background task customer_id=%s workflow=%s",
            customer_id,
            workflow,
        )
        schedule_error_report(
            error=error,
            source="process_centrales_no_autorizo_request",
            conversation_id=correlation_id,
            extra_context={
                "customer_id": customer_id,
                "workflow": workflow,
                "operation": "centrales_no_autorizo",
            },
        )
        try:
            await opensearch_client.update_client_control_data(
                customer_id=customer_id.strip(),
                workflow=workflow.strip(),
                status="error",
                run_id=run_id,
                error=_build_back_data_error(error),
            )
        except Exception:
            logger.exception(
                "Failed to write ERROR envelope for centrales_no_autorizo customer_id=%s workflow=%s",
                customer_id,
                workflow,
            )
