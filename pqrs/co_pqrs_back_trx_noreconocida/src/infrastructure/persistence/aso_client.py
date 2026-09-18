"""Cliente HTTP para los ASOs de TXNR (simulador o real, según `ASO_SOURCE`).

Fail-safe: cualquier fallo devuelve None / False (nunca levanta al llamador).
El TSEC se solicita al grantingTicket y se propaga en el header `tsec`.
La base URL sale de `TrxAsoSettings.base_url` (apunta al simulador o al ASO real).
"""

from __future__ import annotations

import os
import hashlib
import time
from datetime import datetime
import uuid

import httpx
from typing import Any

from infrastructure.core.config import TrxAsoSettings, load_trx_aso_settings
from infrastructure.core.logger import get_logger
from infrastructure.observability.trace_audit import (
    body_snapshot,
    mask_pii,
    e2e_debug_enabled,
    schedule_trace_event,
)

logger = get_logger(__name__)

# Headers que SI se pueden trazar. Allowlist deliberada: el header `tsec` y
# `authorization` NUNCA deben quedar en el trace (son credenciales).
_HEADER_ALLOWLIST: frozenset[str] = frozenset(
    {
        "content-type",
        "content-length",
        "date",
        "server",
        "x-request-id",
        "x-correlation-id",
        "x-amzn-trace-id",
        "www-authenticate",
        # Cabeceras de la SUBIDA DE NIVEL (reto de autenticacion previo al
        # bloqueo). Sin ellas no se puede leer el reto ni trazarlo: el ASO
        # devuelve el tipo de autenticacion en el 403 y el challenge/state en el
        # 401. No son secretos del cliente, son identificadores de la operacion.
        "authenticationtype",
        "authenticationchallenge",
        "authenticationstate",
        "retry-after",
    }
)


def _local_contingency_enabled() -> bool:
    raw = (os.getenv("LOCAL_CONTINGENCY_MODE") or "").strip().casefold()
    return raw in {"1", "true", "yes", "on"}


def _safe_json(resp: Any) -> Any:
    """Devuelve el body JSON de la respuesta o None (nunca levanta)."""
    try:
        return resp.json()
    except Exception:
        try:
            return {"raw": resp.text[:500]}
        except Exception:
            return None


def _headers_subset(response: Any) -> dict[str, str]:
    try:
        return {
            key: value
            for key, value in response.headers.items()
            if key.lower() in _HEADER_ALLOWLIST
        }
    except Exception:  # noqa: BLE001
        return {}


def _flag(nombre: str, default: str = "false") -> bool:
    """Lee un toggle booleano del entorno (prioriza el .env del configmap)."""

    try:
        from infrastructure.core.config import load_env_constants

        crudo = load_env_constants().get(nombre)
    except Exception:  # noqa: BLE001
        crudo = None
    if crudo in (None, ""):
        crudo = os.getenv(nombre)
    return str(crudo if crudo not in (None, "") else default).strip().casefold() in {
        "1", "true", "yes", "on",
    }


def _tsec_debug(tsec: str | None) -> dict[str, Any]:
    """Huella verificable del TSEC enviado en la peticion.

    Longitud, prefijo, sufijo y SHA256: suficiente para comprobar que el ASO 2
    recibio exactamente el token que devolvio el grantingTicket. El valor
    completo NUNCA se escribe (KYNS IT 3): el TSEC es una credencial de sesion y
    el flag ``ASO_TRACE_TSEC_FULL`` que lo permitia se retiro.
    """

    if not tsec:
        return {
            "tsec_enviado": False,
            "tsec_motivo": "el llamador no paso tsec: la peticion sale SIN autenticar",
        }
    debug: dict[str, Any] = {
        "tsec_enviado": True,
        "tsec_longitud": len(tsec),
        "tsec_prefijo": tsec[:12],
        # El sufijo permite ver el padding base64 ('==') completo.
        "tsec_sufijo": tsec[-8:],
        "tsec_sha256": hashlib.sha256(tsec.encode("utf-8")).hexdigest(),
        "tsec_termina_en_padding": tsec.endswith("="),
    }
    # ``ASO_TRACE_TSEC_FULL`` se retiro: el TSEC es una credencial de sesion y la
    # huella de arriba (longitud, prefijo, sufijo, sha256) permite comparar dos
    # tokens sin exponer ninguno. Si el flag sigue en un ConfigMap, no hace nada.
    return debug


# Nombre publico de la huella del TSEC, para que otras trazas (la ceremonia de
# subida de nivel) registren el mismo formato que las trazas por llamada al ASO.
huella_tsec = _tsec_debug


def _request_debug(
    *,
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    json_payload: Any = None,
) -> dict[str, Any]:
    """Debug de COMO se armo la peticion: metodo, URL, params, headers y cuerpo.

    Antes solo se trazaban los `params`, asi que era imposible saber desde las
    trazas si el `tsec` se habia enviado o con que URL exacta se llamo. Ahora se
    registra la peticion completa.

    Unica excepcion deliberada: la contrasena del grantingTicket va SIEMPRE
    enmascarada (se conserva solo su longitud). Es una credencial permanente y
    volcarla al bucket de trazas es un riesgo de otra magnitud; el flag
    ``ASO_TRACE_PASSWORD_FULL`` que lo permitia se retiro (KYNS IT 3).
    """

    cabeceras = dict(headers or {})
    tsec = cabeceras.pop("tsec", None)

    debug: dict[str, Any] = {
        "method": method,
        "url": url,
        "url_completa": str(httpx.URL(url).copy_merge_params(params or {})),
        "params": params or {},
        "headers": cabeceras,
    }
    debug.update(_tsec_debug(tsec))

    if json_payload is not None:
        debug["body_enviado"] = _mask_password(json_payload)
        debug["body_es_json"] = True
    return debug


def _mask_password(payload: Any) -> Any:
    """Copia del payload con la contrasena del granting SIEMPRE enmascarada.

    Antes existia ``ASO_TRACE_PASSWORD_FULL`` para volcarla; se retiro (control
    KYNS IT 3: ninguna credencial permanente en las trazas). El flag, si sigue
    en algun ConfigMap, ya no tiene efecto.
    """

    try:
        import copy

        limpio = copy.deepcopy(payload)
        auth = (limpio or {}).get("authentication", {})
        for item in auth.get("authenticationData", []) or []:
            if str(item.get("idAuthenticationData", "")).casefold() == "password":
                valores = item.get("authenticationData") or []
                item["authenticationData"] = [f"<oculto len={len(str(v))}>" for v in valores]
        return limpio
    except Exception:  # noqa: BLE001
        return {"<no se pudo enmascarar el payload>": True}


def _response_debug(response: Any, *, payload: Any = None) -> dict[str, Any]:
    """Construye el DEBUG de lo que respondio el ASO: siempre, falle o no.

    Incluye status, content-type, headers seguros y el cuerpo. El cuerpo va
    enmascarado+truncado por defecto (`ASO_TRACE_FULL_BODY`) y COMPLETO cuando
    `E2E_DEBUG_TRACE=true`. Si no hubo respuesta (timeout/DNS/proxy) se marca
    explicitamente para poder distinguir ese caso de un error del ASO.
    """

    if response is None:
        return {"no_response": True, "reason": "sin respuesta del ASO (timeout/red/proxy)"}

    debug: dict[str, Any] = {
        "status_code": getattr(response, "status_code", None),
        "content_type": _headers_subset(response).get("content-type", ""),
        "headers": _headers_subset(response),
    }

    # Cuerpo: si el payload ya viene parseado se usa; si no, se intenta JSON y
    # como ultimo recurso el texto crudo (justo el caso "respondio HTML/vacio").
    body: Any = payload
    if body is None:
        try:
            body = response.json()
            debug["body_is_json"] = True
        except Exception:  # noqa: BLE001
            debug["body_is_json"] = False
            try:
                body = response.text
            except Exception:  # noqa: BLE001
                try:
                    body = f"<cuerpo no textual bytes={len(response.content)}>"
                except Exception:  # noqa: BLE001
                    body = None
    else:
        debug["body_is_json"] = True

    if body is not None:
        debug.update(body_snapshot(body))
        if e2e_debug_enabled():
            # Cuerpo completo (sin truncar) pero ENMASCARADO: PAN a ultimos 4 y
            # correos ocultos. Antes iba en claro, con el PAN y el titular del
            # financial-overview dentro (hallazgo KYNS IT 3, 31/08).
            import json as _json

            try:
                texto = body if isinstance(body, str) else _json.dumps(body, ensure_ascii=False, default=str)
            except Exception:  # noqa: BLE001
                texto = str(body)
            debug["body_full_masked"] = mask_pii(texto)
    else:
        debug["body_empty"] = True
    return debug

# Cache de operaciones por (base_url, card_id, fecha). TTL corto: dentro de una
# conversacion el dia consultado no cambia, y fuera de ella no interesa retener.
_OPERATIONS_CACHE: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}
_OPERATIONS_TTL_SECONDS = 900.0
_OPERATIONS_CACHE_MAX = 256


class TrxAsoClient:
    def __init__(self, settings: TrxAsoSettings | None = None) -> None:
        # Id de cadena: permite AGRUPAR en las trazas el grantingTicket con los
        # ASO que usaron ese token. Antes eran eventos sueltos y habia que
        # adivinar cual iba con cual.
        self._chain_id = uuid.uuid4().hex[:12]
        self.settings = settings or load_trx_aso_settings()

    # --- infra ------------------------------------------------------------
    def _client(self):
        import httpx

        return httpx.Client(
            verify=self.settings.api_verify_ssl,
            timeout=self.settings.api_timeout,
        )

    def _base(self) -> str:
        return (self.settings.base_url or self.settings.aso_base_url or "").rstrip("/")

    def _challenge_base(self) -> str:
        if self.settings.source == "real" and self.settings.challenge_base_url:
            return self.settings.challenge_base_url
        return self._base()

    def _emit(
        self,
        *,
        operation: str,
        url: str,
        outcome: str,
        response: Any = None,
        payload: Any = None,
        elapsed_ms: float | None = None,
        request_summary: dict[str, Any] | None = None,
        error: Exception | None = None,
        customer_id: str | None = None,
        extra_response: dict[str, Any] | None = None,
        request_debug: dict[str, Any] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Emite el trace-event de una llamada ASO con el DEBUG del response.

        Adjunta las DOS mitades de la llamada, en exito y en error:
          - como se armo la peticion (metodo, URL, params, headers, cuerpo y el
            estado del tsec),
          - que respondio el ASO (status, headers, cuerpo).

        Asi se puede diagnosticar sin reproducir el caso.
        """
        peticion = dict(request_summary or {})
        if request_debug:
            peticion.update(request_debug)
        peticion["aso_chain_id"] = self._chain_id
        request_summary = peticion
        response_summary = _response_debug(response, payload=payload)
        if extra_response:
            response_summary.update(extra_response)
        schedule_trace_event(
            event_type="aso",
            operation=operation,
            outcome=outcome,
            status_code=getattr(response, "status_code", None),
            elapsed_ms=elapsed_ms,
            target=url,
            request_summary=request_summary or {},
            response_summary=response_summary,
            # Sin excepcion, el llamador puede marcar un error funcional (p. ej. un
            # 400 del ASO que no lanza) con error_type/error_message explicitos.
            error_type=type(error).__name__ if error else error_type,
            error_message=str(error) if error else error_message,
            customer_id=customer_id,
            tags=["aso", operation],
        )

    def get_tsec(self) -> str:
        """Solicita el TSEC (grantingTicket). Devuelve token o "" si falla."""
        base = self._base()
        url = (self.settings.ticket_url or f"{base}/TechArchitecture/co/grantingTicket/V02")
        payload = {
            "authentication": {
                "userID": self.settings.api_user_id,
                "consumerID": self.settings.api_consumer_id,
                "authenticationType": self.settings.api_authentication_type,
                "authenticationData": [
                    {
                        "idAuthenticationData": "password",
                        "authenticationData": [self.settings.api_password],
                    }
                ],
            },
            "backendUserRequest": {"userId": "", "accessCode": "", "dialogId": ""},
        }
        cabeceras = {"Content-Type": "application/json", "Accept": "application/json"}
        peticion = _request_debug(
            method="POST", url=url, headers=cabeceras, json_payload=payload
        )
        start = time.perf_counter()
        resp = None
        try:
            with self._client() as client:
                resp = client.post(url, headers=cabeceras, json=payload)
            resp.raise_for_status()
            # Extraccion calcada de la implementacion PROBADA de centrales
            # (commercial_info_client._request_tsec): el granting de dev puede
            # devolver el ticket en la cabecera O en el cuerpo. Leer solo la
            # cabecera dejaba el tsec vacio -> el FO salia sin autenticacion ->
            # 204 sin cuerpo (incidente DEV 25/08, usuario 00235597).
            tsec = (resp.headers.get("tsec") or "").strip() or (resp.text or "").strip()
            # El token NUNCA se traza (la allowlist de headers lo excluye); solo se
            # reporta si vino o no, mas el debug del cuerpo de la respuesta.
            self._emit(
                operation="tsec",
                url=url,
                outcome="ok" if tsec else "error",
                response=resp,
                elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                request_summary={"user_id": self.settings.api_user_id},
                request_debug=peticion,
                extra_response=_tsec_debug(tsec) | {"has_tsec": bool(tsec)},
            )
            return tsec
        except Exception as exc:
            logger.exception(
                "TSEC request failed url=%s status=%s",
                url,
                getattr(resp, "status_code", None),
            )
            self._emit(
                operation="tsec", url=url, outcome="error", response=resp,
                elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                request_summary={"user_id": self.settings.api_user_id},
                request_debug=peticion,
                error=exc, extra_response={"has_tsec": False},
            )
            return ""

    def _headers(self, tsec: str | None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if tsec:
            headers["tsec"] = tsec
        return headers

    def _get(
        self,
        path: str,
        params: dict[str, Any],
        tsec: str | None,
        *,
        operation: str = "aso_get",
        customer_id: str | None = None,
        base_url: str | None = None,
    ) -> dict[str, Any] | None:
        base = (base_url or self._base()).rstrip("/")
        if not base:
            logger.warning("ASO base URL no configurada (ASO_BASE_URL)")
            return None
        url = f"{base}{path}"
        cabeceras = self._headers(tsec)
        peticion = _request_debug(
            method="GET", url=url, params=params, headers=cabeceras
        )
        start = time.perf_counter()
        resp = None  # se conserva fuera del try para poder trazar el response en el error
        try:
            with self._client() as client:
                resp = client.get(url, params=params, headers=cabeceras)
            resp.raise_for_status()
            # 204 (y cualquier 2xx sin cuerpo) significa "no hay datos", NO un
            # fallo. Antes `resp.json()` explotaba con el cuerpo vacio y el caso
            # se trazaba como error con status=204, mezclando "el cliente no
            # tiene informacion" con "el ASO fallo".
            if resp.status_code == 204 or not (resp.content or b"").strip():
                self._emit(
                    operation=operation, url=url, outcome="no_content", response=resp,
                    elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                    request_summary={"params": params}, request_debug=peticion,
                    customer_id=customer_id,
                    extra_response={"sin_contenido": True,
                                    "detalle": "2xx sin cuerpo: el ASO no tiene datos"},
                )
                return {}
            data = resp.json()
            self._emit(
                operation=operation, url=url, outcome="ok", response=resp, payload=data,
                elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                request_summary={"params": params}, request_debug=peticion,
                customer_id=customer_id,
            )
            return data
        except Exception as exc:
            logger.warning(
                "ASO GET fallo url=%s status=%s (fail-open)",
                url,
                getattr(resp, "status_code", None),
            )
            self._emit(
                operation=operation, url=url, outcome="error", response=resp,
                elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                request_summary={"params": params}, request_debug=peticion,
                error=exc, customer_id=customer_id,
            )
            return None

    # --- ASOs -------------------------------------------------------------
    def salesforce_issues(self, target_user_id: str, tsec: str | None = None) -> dict[str, Any] | None:
        return self._get(
            self.settings.salesforce_path,
            {"targetUserId": target_user_id},
            tsec,
            operation="salesforce_issues",
            customer_id=target_user_id,
        )

    def financial_overview(
        self,
        *,
        customer_id: str | None = None,
        contract_id: str | None = None,
        tsec: str | None = None,
    ) -> dict[str, Any] | None:
        """financial-overview con SOLO ``customer.id`` (Fabian, 24/08).

        Incidente PRD 24/08: la peticion filtrada por ``contracts.id`` (el
        contract_id de ADA es un LIC, no el identificador que el filtro del
        ASO real indexa) fallaba y todos los productos quedaban ``fo_error``
        -> el cliente veia "no pudimos consultar tus productos" TENIENDO
        productos. Decision de Fabian en el equipo: quitar el filtro por
        contrato Y el de ``contracts.productType=CARDS`` -- nos traemos TODO
        el financial del cliente y ajustamos a partir del JSON real.

        ``contract_id`` se conserva en la firma porque los llamadores lo
        siguen pasando (y sirve para trazar), pero NO viaja al ASO. La
        tarjeta se localiza en la RESPUESTA por los campos configurables
        (FO_CONTRACT_MATCH_FIELD=number, FO_CARD_NUMBER_PATH=id), igual que
        siempre: traer todo no cambia como se casa el contrato elegido.
        """

        normalized_contract = str(contract_id or "").strip()
        normalized_customer = str(customer_id or "").strip()
        if normalized_contract:
            logger.debug(
                "financial-overview: contract_id=%s recibido pero NO se envia "
                "como filtro (decision Fabian 24/08: solo customer.id)",
                normalized_contract,
            )
        params = {"customer.id": normalized_customer}

        return self._get(
            self.settings.financial_overview_path,
            params,
            tsec,
            operation="financial_overview",
            customer_id=normalized_customer or None,
        )

    def operations(
        self,
        card_id: str,
        *,
        operation_date: str,
        page_size: int = 100,
        pagination_key: int = 1,
        tsec: str | None = None,
    ) -> dict[str, Any] | None:
        """Operaciones del dia para una tarjeta.

        El ASO devuelve TODAS las operaciones de la fecha en una respuesta, pero
        el flujo pedia el detalle una vez por cada movimiento que el cliente
        elegia (y el caso admite hasta 3 transacciones). Se cachea por
        (card_id, fecha) durante una ventana corta: la primera consulta trae el
        dia entero y las siguientes se sirven de memoria.

        Cache de proceso, deliberadamente: es una optimizacion, no una fuente de
        verdad. Con varios pods un cliente que cambie de pod repite la llamada,
        que es el comportamiento anterior -- nunca sirve un dato incorrecto.
        """

        clave = (self._base(), card_id, operation_date)
        entrada = _OPERATIONS_CACHE.get(clave)
        if entrada is not None:
            guardado, payload = entrada
            if (time.time() - guardado) < _OPERATIONS_TTL_SECONDS:
                schedule_trace_event(
                    event_type="aso", operation="operations", outcome="cache_hit",
                    request_summary={"card_id": card_id,
                                     "operation_date": operation_date},
                )
                return payload
            _OPERATIONS_CACHE.pop(clave, None)

        # Se recorren TODAS las paginas del ASO y se acumulan: sin esto, un dia
        # con mas de ``pageSize`` operaciones quedaba recortado a la primera
        # pagina (100) y los movimientos siguientes eran irreportables. El ASO
        # informa ``pagination.totalPages``; ``paginationKey`` es el numero de
        # pagina (entero). El simulador devuelve todo en una pagina
        # (totalPages=1), asi que el bucle termina en la primera.
        payload = self._get(
            self.settings.operations_path,
            {
                "operationDate": operation_date,
                "cardId": card_id,
                "pageSize": page_size,
                "paginationKey": pagination_key,
            },
            tsec,
            operation="operations",
        )
        if payload is not None:
            try:
                total_pages = int(((payload.get("pagination") or {}).get("totalPages")) or 1)
            except (TypeError, ValueError):
                total_pages = 1
            # Tope de seguridad ante un totalPages malformado del ASO: 200
            # paginas * pageSize cubre cualquier dia real sin arriesgar un
            # bucle infinito. Si se alcanza, se registra.
            _MAX_PAGINAS = 200
            pagina = pagination_key + 1
            while pagina <= total_pages and pagina <= _MAX_PAGINAS:
                extra = self._get(
                    self.settings.operations_path,
                    {
                        "operationDate": operation_date,
                        "cardId": card_id,
                        "pageSize": page_size,
                        "paginationKey": pagina,
                    },
                    tsec,
                    operation="operations",
                )
                if extra is None:
                    # Fallo a mitad de paginacion: se devuelve lo acumulado en
                    # vez de nada. El listado marca fuera_de_rango/total con lo
                    # que hay; nunca se afirma un dato falso.
                    logger.warning(
                        "operations: fallo en la pagina %s de %s card=****%s fecha=%s "
                        "(se devuelve lo acumulado)",
                        pagina, total_pages, str(card_id)[-4:], operation_date,
                    )
                    break
                for bloque in (extra.get("data") or []):
                    payload.setdefault("data", []).append(bloque)
                pagina += 1
            if pagina > _MAX_PAGINAS and _MAX_PAGINAS < total_pages:
                logger.warning(
                    "operations: se alcanzo el tope de %s paginas (totalPages=%s) "
                    "card=****%s fecha=%s", _MAX_PAGINAS, total_pages,
                    str(card_id)[-4:], operation_date,
                )
            if len(_OPERATIONS_CACHE) >= _OPERATIONS_CACHE_MAX:
                _OPERATIONS_CACHE.clear()
            _OPERATIONS_CACHE[clave] = (time.time(), payload)
        return payload

    # --- SUBIDA DE NIVEL (notificacion push previa al bloqueo) -------------
    #
    # Ceremonia de 4 llamadas contra el ASO, en este orden:
    #   1. GET  /security/v0/user-status      -> deviceId activo del cliente
    #   2. POST /cards/v2/operations          -> 403 + cabecera authenticationtype
    #   3. POST /cards/v2/operations (+data)  -> 401 + challenge/state, ENVIA el push
    #   4. GET  /security/v0/order-chanel/... -> pending | accepted
    # y solo para el bloqueo DEFINITIVO:
    #   5. POST /cards/v2/operations (+state) -> 200, ejecuta la cancelacion
    #
    # SEGURIDAD DEL CASO TEMPORAL: los pasos 2 y 3 devuelven 403 y 401, es decir
    # NO ejecutan la operacion; solo disparan el reto y la notificacion. El unico
    # que ejecuta es el paso 5, y en el bloqueo temporal NO se llama: tras el
    # `accepted` se hace el PATCH de apagado. Asi, un error de rama no puede
    # cancelar la tarjeta de quien solo queria apagarla.

    def user_status(self, profile_id: str, *, tsec: str | None = None) -> dict[str, Any]:
        """Dispositivo activo del cliente (paso 1 de la subida de nivel).

        `profile_id` se arma como ``CC`` + ``personal_id`` de Postgres.

        Devuelve ``{"device_id": str, "activo": bool, "total_dispositivos": int}``.
        Si hay varios dispositivos activos se toma el PRIMERO, segun el contrato.
        """

        payload = self._get(
            self.settings.user_status_path,
            {"profileId": profile_id},
            tsec,
            operation="user_status",
            base_url=self._challenge_base(),
        )
        if not payload:
            return {"device_id": "", "activo": False, "total_dispositivos": 0}

        dispositivos = payload.get("data") or []
        activos = []
        for item in dispositivos:
            if not isinstance(item, dict):
                continue
            device = item.get("device") or {}
            soft = (device.get("softToken") or {}).get("status") or {}
            canal = (item.get("channel") or {}).get("status") or {}
            device_id = str(device.get("id") or "").strip()
            # Se exige ACTIVE en el softToken; el canal se reporta pero no filtra
            # (el contrato muestra el mismo valor en ambos y no se quiere excluir
            # un dispositivo valido por una diferencia de nomenclatura).
            if device_id and str(soft.get("id") or "").strip().upper() == "ACTIVE":
                activos.append(
                    {"device_id": device_id, "canal": str(canal.get("id") or "")}
                )

        if not activos:
            logger.warning(
                "user-status sin dispositivos ACTIVE profile_id=%s total=%s",
                profile_id,
                len(dispositivos),
            )
            return {
                "device_id": "",
                "activo": False,
                "total_dispositivos": len(dispositivos),
            }
        return {
            "device_id": activos[0]["device_id"],
            "activo": True,
            "total_dispositivos": len(dispositivos),
            "activos": len(activos),
        }

    def _challenge_body(self, card_id: str) -> dict[str, Any]:
        """Cuerpo comun de las tres llamadas a /cards/v2/operations."""

        ahora = datetime.now()
        return {
            "card": {
                "cardId": card_id,
                "cardInformation": {
                    "reason": self.settings.challenge_reason,
                    "requestDate": ahora.strftime("%Y-%m-%d"),
                    "requestHour": ahora.strftime("%H:%M"),
                    "description": "Cliente reporta transaccion no reconocida bot PQRs",
                    "retentionName": self.settings.challenge_retention_name,
                },
            }
        }

    def _authentication_data(
        self,
        *,
        device_id: str,
        profile_id: str,
        account_last_four: str,
    ) -> str:
        """Cadena ``authenticationdata`` del reto.

        El estado de autenticacion viaja como header, no dentro de esta cadena.
        """

        # Defensa (27/08): si el parametro llega sin resolver (p. ej. un
        # default Query de FastAPI en una llamada directa), NO se interpola su
        # repr en la cadena que viaja al ASO.
        if not isinstance(account_last_four, str):
            account_last_four = ""
        producto = (
            f"cuenta-{account_last_four}"
            if account_last_four
            else "cuenta-"
        )
        campos = [
            f"deviceId={device_id}",
            f"profileId={profile_id}",
            f"channel={self.settings.challenge_channel}",
            f"operation={self.settings.challenge_operation}",
            f"smc={self.settings.challenge_smc}",
            "amount=",
            f"product={producto}",
            f"description={self.settings.challenge_description}",
        ]
        return ",".join(campos)

    def _post_operations(
        self,
        card_id: str,
        *,
        tsec: str | None,
        extra_headers: dict[str, str] | None = None,
        operation: str,
        error_si_no_2xx: bool = False,
        mensajes_error: dict[int, str] | None = None,
    ) -> tuple[int | None, dict[str, str], dict[str, Any] | None]:
        """POST a /cards/v2/operations. Devuelve (status, cabeceras, cuerpo).

        NO lanza por status: los 403 y 401 son parte esperada del protocolo, no
        errores. El llamador decide.

        Con `error_si_no_2xx=True` (paso que SI debe responder 2xx, como la
        confirmacion del bloqueo) un codigo no-2xx se traza con `error_type` y
        `error_message`; `mensajes_error` permite explicar codigos concretos.
        """

        base = self._challenge_base()
        if not base:
            return None, {}, None
        url = f"{base}{self.settings.operations_path}"
        body = self._challenge_body(card_id)
        cabeceras = {**self._headers(tsec), "Content-Type": "application/json"}
        if extra_headers:
            cabeceras.update(extra_headers)
        peticion = _request_debug(
            method="POST", url=url, headers=cabeceras, json_payload=body
        )
        start = time.perf_counter()
        resp = None
        try:
            with self._client() as client:
                resp = client.post(url, headers=cabeceras, json=body)
            cuerpo = _safe_json(resp)
            # Las cabeceras del reto llegan en minusculas o mixtas segun el ASO.
            recibidas = {k.lower(): v for k, v in dict(resp.headers).items()}
            es_2xx = 200 <= resp.status_code < 300
            marcar_error = error_si_no_2xx and not es_2xx
            self._emit(
                operation=operation, url=url,
                outcome="ok" if es_2xx else f"http_{resp.status_code}",
                error_type="HTTPStatusError" if marcar_error else None,
                error_message=(
                    (mensajes_error or {}).get(
                        resp.status_code, f"ASO respondio {resp.status_code}"
                    )
                    if marcar_error
                    else None
                ),
                response=resp, payload=cuerpo,
                elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                request_debug=peticion,
                extra_response={
                    "authenticationtype": recibidas.get("authenticationtype", ""),
                    "tiene_challenge": bool(recibidas.get("authenticationchallenge")),
                    "tiene_state": bool(recibidas.get("authenticationstate")),
                },
            )
            return resp.status_code, recibidas, cuerpo
        except Exception as exc:
            self._emit(
                operation=operation, url=url, outcome="error", response=resp,
                elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                request_debug=peticion, error=exc,
            )
            return None, {}, None

    def challenge_iniciar(self, card_id: str, *, tsec: str | None = None) -> dict[str, Any]:
        """Paso 2: primer POST. Se espera 403 con la cabecera authenticationtype."""

        status_code, cabeceras, _ = self._post_operations(
            card_id, tsec=tsec, operation="challenge_iniciar"
        )
        tipo = str(cabeceras.get("authenticationtype") or "").strip()
        esperado = self.settings.challenge_auth_type
        return {
            "status_code": status_code,
            "authentication_type": tipo,
            # El contrato dice 403; se acepta cualquier respuesta que traiga el
            # tipo esperado, para no romper si el ASO cambia el codigo.
            "ok": tipo == esperado,
            "esperado": esperado,
        }

    def challenge_enviar_push(
        self,
        card_id: str,
        *,
        device_id: str,
        profile_id: str,
        account_last_four: str,
        tsec: str | None = None,
    ) -> dict[str, Any]:
        """Paso 3: segundo POST. ENVIA la notificacion al dispositivo.

        Se espera 401 con las cabeceras ``authenticationChallenge`` y
        ``authenticationstate``, que hay que conservar para los pasos siguientes.
        """

        status_code, cabeceras, _ = self._post_operations(
            card_id,
            tsec=tsec,
            extra_headers={
                "authenticationtype": self.settings.challenge_auth_type,
                "authenticationdata": self._authentication_data(
                    device_id=device_id,
                    profile_id=profile_id,
                    account_last_four=account_last_four,
                ),
            },
            operation="challenge_enviar_push",
        )
        challenge = str(cabeceras.get("authenticationchallenge") or "").strip()
        challenge = challenge.rstrip(":;")
        estado = str(cabeceras.get("authenticationstate") or "").strip()
        return {
            "status_code": status_code,
            "challenge": challenge,
            "authentication_state": estado,
            "ok": bool(challenge),
        }

    def order_channel_status(
        self, challenge: str, *, tsec: str | None = None
    ) -> dict[str, Any]:
        """Paso 4: estado de la notificacion en el dispositivo del cliente.

        ``pending`` mientras no responde, ``accepted`` cuando autoriza.
        """

        path = self.settings.order_channel_path.format(challenge=challenge)
        payload = self._get(
            path,
            {},
            tsec,
            operation="order_channel_status",
            base_url=self._challenge_base(),
        )
        if payload is None:
            # El ASO fallo (red, 4xx/5xx). Distinto de un 2xx sin cuerpo ({}),
            # que sigue contando como pendiente.
            return {"estado": "error", "aceptado": False, "pendiente": False}
        estado = str(
            (((payload.get("data") or {}).get("status") or {}).get("id") or "")
        ).strip().casefold()
        return {
            "estado": estado,
            "aceptado": estado in {"accepted", "approved"},
            "pendiente": estado in {"pending", ""},
        }

    def challenge_confirmar(
        self,
        card_id: str,
        *,
        device_id: str,
        profile_id: str,
        account_last_four: str,
        challenge: str,
        authentication_state: str,
        tsec: str | None = None,
    ) -> dict[str, Any]:
        """Paso 5: tercer POST. EJECUTA la cancelacion + reexpedicion (200).

        SOLO para bloqueo DEFINITIVO. En el temporal no se llama: tras el
        `accepted` se hace el PATCH de apagado.
        """

        status_code, _, cuerpo = self._post_operations(
            card_id,
            tsec=tsec,
            extra_headers={
                "authenticationtype": self.settings.challenge_auth_type,
                "authenticationstate": authentication_state,
                "authenticationdata": self._authentication_data(
                    device_id=device_id,
                    profile_id=profile_id,
                    account_last_four=account_last_four,
                ),
            },
            operation="challenge_confirmar",
            error_si_no_2xx=True,
            mensajes_error={400: "ASO respondio 400: el cliente no autorizo la operacion"},
        )
        return {
            "status_code": status_code,
            "ok": bool(status_code and 200 <= status_code < 300),
            # 400 = el cliente no autorizo la operacion.
            "rechazado": status_code == 400,
            "detalle": cuerpo,
        }

    def block_temporary(self, card_id: str, *, is_active: bool = False, tsec: str | None = None) -> bool:
        """PATCH activations ON_OFF. True si 2xx."""
        base = self._base()
        if not base:
            return False
        url = f"{base}{self.settings.activations_path.format(card_id=card_id)}"
        body = {
            "root": [
                {
                    "id": "ON_OFF",
                    "isActive": is_active,
                    "additionalInformation1": None,
                    "additionalInformation2": 0,
                    "additionalInformation3": None,
                    "additionalInformation4": None,
                }
            ]
        }
        cabeceras = self._headers(tsec)
        peticion = _request_debug(
            method="PATCH", url=url, headers=cabeceras, json_payload=body
        )
        start = time.perf_counter()
        resp = None
        try:
            with self._client() as client:
                resp = client.patch(url, headers=cabeceras, json=body)
            ok = 200 <= resp.status_code < 300
            self._emit(
                operation="block_temporary", url=url, outcome="ok" if ok else "error",
                error_type=None if ok else "HTTPStatusError",
                error_message=(
                    None if ok else f"ASO respondio {resp.status_code} al apagado de la tarjeta"
                ),
                response=resp, elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                request_summary={"isActive": is_active},
            request_debug=peticion,
                )
            return ok
        except Exception as exc:
            logger.warning(
                "ASO PATCH activations fallo url=%s status=%s (fail-open)",
                url,
                getattr(resp, "status_code", None),
            )
            self._emit(
                operation="block_temporary", url=url, outcome="error", response=resp,
                elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                request_summary={"isActive": is_active}, error=exc,
            request_debug=peticion,
                )
            return False

    def block_permanent(self, card_id: str, *, tsec: str | None = None) -> bool:
        """POST reemisión (bloqueo permanente + nueva tarjeta). True si 2xx."""
        base = self._base()
        if not base:
            return False
        url = f"{base}{self.settings.reissuance_path}"
        body = {
            "card": {
                "cardId": card_id,
                "reissuance": {
                    "isStampingDisabled": False,
                    "isRestockingFee": True,
                    "changeNumber": True,
                    "isNewCardApplication": True,
                    "cardInformation": {
                        "reason": "Fraude",
                        "description": "El cliente efectuara el bloqueo permanente por BOT PQR",
                        "country": {"id": "01", "name": "Colombia"},
                    },
                },
            }
        }

        logger.info(
            "ASO BLOCK PERMANENT request card_id=%s url=%s",
            card_id,
            url,
        )

        logger.info(
            "ASO BLOCK PERMANENT body=%s",
            body,
        )

        cabeceras = self._headers(tsec)
        peticion = _request_debug(
            method="POST", url=url, headers=cabeceras, json_payload=body
        )
        start = time.perf_counter()
        resp = None
        try:
            with self._client() as client:
                resp = client.post(url, headers=cabeceras, json=body)
            ok = 200 <= resp.status_code < 300
            
            logger.info(
                "ASO BLOCK PERMANENT response status=%s ok=%s body=%s",
                resp.status_code,
                ok,
                _safe_json(resp),
            )

            self._emit(
                operation="block_permanent", url=url, outcome="ok" if ok else "error",
                response=resp, elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                request_summary={"reason": "Fraude"},
            request_debug=peticion,
                )
            return ok
        except Exception as exc:
            logger.warning(
                "ASO POST reissuance fallo url=%s status=%s (fail-open)",
                url,
                getattr(resp, "status_code", None),
            )
            self._emit(
                operation="block_permanent", url=url, outcome="error", response=resp,
                elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                request_summary={"reason": "Fraude"}, error=exc,
            request_debug=peticion,
                )
            return False
