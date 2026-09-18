"""Mock client for the external commercial-info API."""

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

from domain.customer.models import CustomerIdentity
from infrastructure.core.config import (
    CommercialInfoSettings,
    load_commercial_info_settings,
    load_env_constants,
)
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.entrypoint.api.errors.exceptions import DataSourceError
from infrastructure.observability.trace_audit import schedule_trace_event

logger = get_logger(__name__)


# --- Detalle de traza ASO ---------------------------------------------------
# Por defecto NO se guarda el cuerpo (PII/credito): solo resumen enmascarado.
# El cuerpo completo (enmascarado + truncado) se guarda solo con el flag dev
# ASO_TRACE_FULL_BODY=true. Nunca se traza el tsec ni el password.
_PII_DIGITS_RE = re.compile(r"\d{6,}")
_PII_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_HEADER_ALLOWLIST = {"content-type", "content-length", "date", "x-b3-traceid"}


def _env_const(name: str) -> str | None:
    """Read a value from the merged .env constants (file mounted at /app/.env),
    falling back to real env vars. os.getenv alone does NOT see the .env file.
    """
    try:
        value = load_env_constants().get(name)
    except Exception:  # noqa: BLE001
        value = None
    if value is None:
        value = os.getenv(name)
    return value


def _aso_trace_full_body() -> bool:
    return str(_env_const("ASO_TRACE_FULL_BODY") or "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _trace_body_maxlen() -> int:
    try:
        return max(200, int(str(_env_const("TRACE_BODY_MAXLEN") or "4000").strip()))
    except (TypeError, ValueError):
        return 4000


def _mask_pii(text: str) -> str:
    """Mask emails and long digit runs (documents/ids) leaving the last 4."""
    text = _PII_EMAIL_RE.sub("***@***", text)
    text = _PII_DIGITS_RE.sub(lambda m: "****" + m.group(0)[-4:], text)
    return text


def _headers_subset(response: "httpx.Response") -> dict[str, str]:
    return {
        key: value
        for key, value in response.headers.items()
        if key.lower() in _HEADER_ALLOWLIST
    }


def _body_snapshot(text: str) -> dict[str, Any]:
    """Return a masked+truncated snapshot of a response body for tracing."""
    full_len = len(text or "")
    snap: dict[str, Any] = {"body_length": full_len}
    if _aso_trace_full_body():
        limit = _trace_body_maxlen()
        snap["body_masked"] = _mask_pii((text or "")[:limit])
        snap["body_truncated"] = full_len > limit
    return snap


# --- Traza DEBUG E2E (SIN enmascarado ni truncado) --------------------------
# Con E2E_DEBUG_TRACE=true se guarda el response COMPLETO del ASO tal cual llega
# (la data ya trae PII desde el origen). Nunca incluye tsec ni password.
def _e2e_debug_enabled() -> bool:
    return str(_env_const("E2E_DEBUG_TRACE") or "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }



_PAN_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SAFE_RESPONSE_HEADERS = ("content-type", "content-length", "date", "x-request-id", "x-correlation-id")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def _mask_text(text: str) -> str:
    """PAN a ultimos 4 y correos ocultos, en cualquier texto.

    Misma regla que el sanitizador del error handler: 13-19 digitos que empiezan
    como una tarjeta (2 a 6) y pasan Luhn, o 16 que empiezan por 4/5. Los
    contratos y productos del banco (0013..., 1300...) no se tocan.
    """

    def _pan(match: "re.Match[str]") -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if digits[:1] in "23456" and (_luhn_ok(digits) or (len(digits) == 16 and digits[0] in "45")):
            return "*" * (len(digits) - 4) + digits[-4:]
        return raw

    return _EMAIL_RE.sub("***@***", _PAN_RE.sub(_pan, text or ""))


def _safe_headers(response: Any) -> dict[str, str]:
    """Solo cabeceras inofensivas: nunca tsec, cookies ni autorizacion."""

    if response is None:
        return {}
    return {k: v for k, v in response.headers.items() if k.lower() in _SAFE_RESPONSE_HEADERS}

def _emit_aso_debug(
    *,
    operation: str,
    status_code: int | None,
    url: str,
    request_summary: dict[str, Any],
    response: "httpx.Response | None",
    outcome: str = "debug",
) -> None:
    """Emit an E2E debug trace with the full ASO response body, masked."""

    if not _e2e_debug_enabled():
        return
    body_full: Any = None
    content_type = ""
    if response is not None:
        content_type = response.headers.get("content-type", "")
        try:
            if "application/json" in content_type.lower():
                body_full = response.json()
            else:
                body_full = response.text
        except Exception:  # noqa: BLE001 - fall back to raw text/bytes info
            try:
                body_full = response.text
            except Exception:  # noqa: BLE001
                body_full = f"<non-text body bytes={len(response.content)}>"
    # El cuerpo completo va ENMASCARADO (PAN a ultimos 4, correos ocultos):
    # antes salia tal cual, con el PAN y el titular del financial-overview.
    try:
        body_text = body_full if isinstance(body_full, str) else json.dumps(body_full, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        body_text = str(body_full)
    schedule_trace_event(
        event_type="debug",
        operation=operation,
        outcome=outcome,
        status_code=status_code,
        target=url,
        request_summary=request_summary,
        response_summary={
            "content_type": content_type,
            "headers": _safe_headers(response),
            "body_full_masked": _mask_text(body_text) if body_full is not None else None,
        },
        tags=["debug", "e2e", "aso", operation],
    )


class CommercialInfoClient:
    """Load commercial-info responses from mocks or the real API."""

    def __init__(self, settings: CommercialInfoSettings | None = None) -> None:
        self.settings = settings or load_commercial_info_settings()

    @log_execution
    def get_commercial_info(self, identity: CustomerIdentity) -> dict[str, Any]:
        """Return the external commercial-info response for the given identity."""

        if self.settings.source == "api":
            return self._get_commercial_info_from_api(identity)

        return self._get_commercial_info_from_mock(identity)

    def _get_commercial_info_from_mock(
        self,
        identity: CustomerIdentity,
    ) -> dict[str, Any]:
        json_path = self._find_mock_path(identity.personal_id)
        logger.info(
            "Reading commercial info mock path=%s personal_id=%s personal_type=%s",
            json_path,
            identity.personal_id,
            identity.personal_type,
        )

        if not json_path.exists():
            raise DataSourceError(
                "Commercial info JSON mock was not found.",
                details={
                    "path": str(json_path),
                    "personal_id": identity.personal_id,
                    "personal_type": identity.personal_type,
                },
            )

        with json_path.open("r", encoding="utf-8") as json_file:
            return json.load(json_file)

    def _get_commercial_info_from_api(
        self,
        identity: CustomerIdentity,
    ) -> dict[str, Any]:
        self._validate_api_settings()
        document_number = identity.personal_id.zfill(
            self.settings.api_customer_id_length
        )
        document_type = self._map_document_type(identity.personal_type)
        last_name = self._extract_last_name(identity.first_last_name)
        if not last_name:
            # Fallback for legacy sources that do not provide first_last_name.
            last_name = self._extract_last_name(
                identity.customer_name,
                from_full_name=True,
            )
        masked_document = self._mask_document(document_number)
        request_summary = {
            "document_type": document_type,
            "document_number": masked_document,
            "personal_type": identity.personal_type,
        }

        logger.info(
            "Reading commercial info API document_type=%s document_number=%s personal_type=%s",
            document_type,
            masked_document,
            identity.personal_type,
        )
        request_summary.update(
            {"method": "GET", "url": self.settings.overview_url, "last_name": last_name}
        )
        # BEFORE: traza previa a la llamada (visibilidad del "antes").
        schedule_trace_event(
            event_type="aso",
            operation="commercial_info_overview",
            outcome="started",
            target=self.settings.overview_url,
            request_summary=request_summary,
            tags=["aso", "overview", "started"],
        )

        with httpx.Client(
            verify=self.settings.api_verify_ssl,
            timeout=self.settings.api_timeout,
        ) as client:
            tsec = self._request_tsec(client)
            start = time.perf_counter()
            try:
                response = client.get(
                    self.settings.overview_url,
                    params={
                        "identityDocument.documentType": document_type,
                        "identityDocument.documentNumber": document_number,
                        "customer.lastName": last_name,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "tsec": tsec,
                    },
                )
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPError as exc:
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                status_code = self._status_code_of(exc)
                logger.error(
                    "ASO overview request failed url=%s document_number=%s status=%s elapsed_ms=%s error=%s",
                    self.settings.overview_url,
                    masked_document,
                    status_code,
                    elapsed_ms,
                    exc,
                )
                err_summary: dict[str, Any] = {}
                err_resp = getattr(exc, "response", None)
                if err_resp is not None:
                    err_summary["headers"] = _headers_subset(err_resp)
                    try:
                        err_summary.update(_body_snapshot(err_resp.text))
                    except Exception:  # noqa: BLE001
                        pass
                schedule_trace_event(
                    event_type="aso",
                    operation="commercial_info_overview",
                    outcome="error",
                    status_code=status_code,
                    elapsed_ms=elapsed_ms,
                    target=self.settings.overview_url,
                    request_summary=request_summary,
                    response_summary=err_summary,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    tags=["aso", "overview"],
                )
                _emit_aso_debug(
                    operation="commercial_info_overview",
                    status_code=status_code,
                    url=self.settings.overview_url,
                    request_summary={
                        "document_type": document_type,
                        "document_number": document_number,
                        "last_name": last_name,
                    },
                    response=err_resp,
                    outcome="debug_error",
                )
                raise DataSourceError(
                    "Commercial info API request failed.",
                    details={
                        "document_number": document_number,
                        "personal_id": identity.personal_id,
                        "source": self.settings.source,
                        "status_code": status_code,
                        "error": str(exc),
                    },
                ) from exc
            except json.JSONDecodeError as exc:
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                logger.error(
                    "ASO overview returned invalid JSON url=%s document_number=%s status=%s elapsed_ms=%s",
                    self.settings.overview_url,
                    masked_document,
                    getattr(response, "status_code", None),
                    elapsed_ms,
                )
                schedule_trace_event(
                    event_type="aso",
                    operation="commercial_info_overview",
                    outcome="error",
                    status_code=getattr(response, "status_code", None),
                    elapsed_ms=elapsed_ms,
                    target=self.settings.overview_url,
                    request_summary=request_summary,
                    error_type="JSONDecodeError",
                    error_message=str(exc),
                    tags=["aso", "overview"],
                )
                raise DataSourceError(
                    "Commercial info API returned invalid JSON.",
                    details={
                        "document_number": document_number,
                        "personal_id": identity.personal_id,
                        "source": self.settings.source,
                    },
                ) from exc

        response_summary = self._summarize_commercial_info(response, payload)
        response_summary["headers"] = _headers_subset(response)
        response_summary.update(_body_snapshot(response.text))
        logger.info(
            "ASO overview OK url=%s document_number=%s status=%s elapsed_ms=%s bytes=%s obligations=%s",
            self.settings.overview_url,
            masked_document,
            response.status_code,
            elapsed_ms,
            response_summary.get("bytes"),
            response_summary.get("obligations"),
        )
        schedule_trace_event(
            event_type="aso",
            operation="commercial_info_overview",
            outcome="ok",
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            target=self.settings.overview_url,
            request_summary=request_summary,
            response_summary=response_summary,
            tags=["aso", "overview"],
        )
        _emit_aso_debug(
            operation="commercial_info_overview",
            status_code=response.status_code,
            url=self.settings.overview_url,
            request_summary={
                "document_type": document_type,
                "document_number": document_number,
                "last_name": last_name,
            },
            response=response,
        )
        return payload

    @log_execution
    def request_aso_pdf(self, path: str) -> bytes:
        """Download a financial-statement document from ASO.

        This is intentionally separate from :meth:`request_aso`: document GETs
        do not send ``Content-Type`` (there is no request body) and ASO can
        negotiate the representation differently from the JSON list endpoint.
        A 406 is retried with the next supported ``Accept`` value only.
        """

        self._validate_api_settings()
        url = f"{self.settings.aso_base_url.rstrip('/')}/{path.lstrip('/')}"
        accept_variants = ("*/*", "application/pdf", "multipart/mixed")

        with httpx.Client(
            verify=self.settings.api_verify_ssl,
            timeout=self.settings.api_timeout,
        ) as client:
            tsec = self._request_tsec(client)
            last_response: httpx.Response | None = None

            for accept in accept_variants:
                start = time.perf_counter()
                try:
                    response = client.get(
                        url,
                        headers={
                            "Accept": accept,
                            "tsec": tsec,
                        },
                    )
                    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                except httpx.HTTPError as exc:
                    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                    status_code = self._status_code_of(exc)
                    logger.error(
                        "ASO PDF request failed url=%s status=%s elapsed_ms=%s error=%s",
                        url,
                        status_code,
                        elapsed_ms,
                        exc,
                    )
                    raise DataSourceError(
                        "ASO PDF request failed.",
                        details={"url": url, "accept": accept, "error": str(exc)},
                    ) from exc

                if response.status_code == 406:
                    last_response = response
                    logger.info(
                        "ASO PDF request returned 406 url=%s accept=%s; trying next variant",
                        url,
                        accept,
                    )
                    continue

                try:
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    err_summary: dict[str, Any] = {"headers": _headers_subset(response)}
                    try:
                        err_summary.update(_body_snapshot(response.text))
                    except Exception:  # noqa: BLE001
                        pass
                    schedule_trace_event(
                        event_type="aso",
                        operation="request_aso_pdf",
                        outcome="error",
                        status_code=response.status_code,
                        elapsed_ms=elapsed_ms,
                        target=url,
                        request_summary={"accept": accept},
                        response_summary=err_summary,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                        tags=["aso", "pdf"],
                    )
                    raise DataSourceError(
                        "ASO PDF request failed.",
                        details={"url": url, "accept": accept, "error": str(exc)},
                    ) from exc

                content_type = response.headers.get("content-type", "").lower()
                content = response.content
                is_supported_document = (
                    "application/pdf" in content_type
                    or content_type.startswith("multipart/")
                    or content.lstrip().startswith(b"%PDF")
                    or content.lstrip().startswith(b"--")
                )
                if not is_supported_document:
                    schedule_trace_event(
                        event_type="aso",
                        operation="request_aso_pdf",
                        outcome="error",
                        status_code=response.status_code,
                        elapsed_ms=elapsed_ms,
                        target=url,
                        request_summary={"accept": accept},
                        response_summary={
                            "content_type": content_type,
                            **_body_snapshot(response.text),
                        },
                        error_type="UnexpectedDocumentContent",
                        error_message="ASO response is not a PDF or multipart document",
                        tags=["aso", "pdf"],
                    )
                    raise DataSourceError(
                        "ASO PDF response did not contain a PDF or multipart document.",
                        details={"url": url, "accept": accept, "content_type": content_type},
                    )

                logger.info(
                    "ASO PDF request OK url=%s status=%s elapsed_ms=%s bytes=%s content_type=%s accept=%s",
                    url,
                    response.status_code,
                    elapsed_ms,
                    len(content),
                    content_type,
                    accept,
                )
                schedule_trace_event(
                    event_type="aso",
                    operation="request_aso_pdf",
                    outcome="ok",
                    status_code=response.status_code,
                    elapsed_ms=elapsed_ms,
                    target=url,
                    request_summary={"accept": accept},
                    response_summary={"bytes": len(content), "content_type": content_type},
                    tags=["aso", "pdf"],
                )
                _emit_aso_debug(
                    operation="request_aso_pdf",
                    status_code=response.status_code,
                    url=url,
                    request_summary={"accept": accept, "bytes": len(content)},
                    response=response,
                )
                return content

        status_code = last_response.status_code if last_response is not None else None
        response_summary: dict[str, Any] = {}
        if last_response is not None:
            response_summary["headers"] = _headers_subset(last_response)
            try:
                response_summary.update(_body_snapshot(last_response.text))
            except Exception:  # noqa: BLE001
                pass
        schedule_trace_event(
            event_type="aso",
            operation="request_aso_pdf",
            outcome="error",
            status_code=status_code,
            target=url,
            request_summary={"accept_variants": list(accept_variants)},
            response_summary=response_summary,
            error_type="HTTPStatusError",
            error_message="ASO rejected all supported PDF representations with HTTP 406",
            tags=["aso", "pdf"],
        )
        raise DataSourceError(
            "ASO rejected all supported PDF representations.",
            details={"url": url, "accept_variants": list(accept_variants)},
        )

    @log_execution
    def request_aso(
        self,
        path: str,
        *,
        accept: str = "application/json",
    ) -> Any:
        """Call an ASO endpoint using the shared TSEC authentication flow."""

        self._validate_api_settings()
        url = f"{self.settings.aso_base_url.rstrip('/')}/{path.lstrip('/')}"

        with httpx.Client(
            verify=self.settings.api_verify_ssl,
            timeout=self.settings.api_timeout,
        ) as client:
            tsec = self._request_tsec(client)
            start = time.perf_counter()
            try:
                response = client.get(
                    url,
                    headers={
                        "Accept": accept,
                        "Content-Type": accept,
                        "tsec": tsec,
                    },
                )
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                status_code = self._status_code_of(exc)
                logger.error(
                    "ASO request failed url=%s status=%s elapsed_ms=%s error=%s",
                    url,
                    status_code,
                    elapsed_ms,
                    exc,
                )
                schedule_trace_event(
                    event_type="aso",
                    operation="request_aso",
                    outcome="error",
                    status_code=status_code,
                    elapsed_ms=elapsed_ms,
                    target=url,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    tags=["aso"],
                )
                raise DataSourceError(
                    "ASO request failed.",
                    details={
                        "url": url,
                        "accept": accept,
                        "error": str(exc),
                    },
                ) from exc

            content_type = response.headers.get("content-type", "")
            body_bytes = len(response.content)
            try:
                if "application/json" in content_type.lower():
                    result = response.json()
                else:
                    result = response.content
            except json.JSONDecodeError as exc:
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                logger.error(
                    "ASO returned invalid JSON url=%s status=%s elapsed_ms=%s",
                    url,
                    response.status_code,
                    elapsed_ms,
                )
                schedule_trace_event(
                    event_type="aso",
                    operation="request_aso",
                    outcome="error",
                    status_code=response.status_code,
                    elapsed_ms=elapsed_ms,
                    target=url,
                    error_type="JSONDecodeError",
                    error_message=str(exc),
                    tags=["aso"],
                )
                raise DataSourceError(
                    "ASO returned invalid JSON.",
                    details={"url": url, "accept": accept},
                ) from exc

        logger.info(
            "ASO request OK url=%s status=%s elapsed_ms=%s bytes=%s content_type=%s",
            url,
            response.status_code,
            elapsed_ms,
            body_bytes,
            content_type,
        )
        schedule_trace_event(
            event_type="aso",
            operation="request_aso",
            outcome="ok",
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            target=url,
            response_summary={"bytes": body_bytes, "content_type": content_type},
            tags=["aso"],
        )
        _emit_aso_debug(
            operation="request_aso",
            status_code=response.status_code,
            url=url,
            request_summary={"accept": accept, "bytes": body_bytes},
            response=response,
        )
        return result

    def _request_tsec(self, client: httpx.Client) -> str:
        start = time.perf_counter()
        try:
            response = client.post(
                self.settings.ticket_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
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
                    "backendUserRequest": {
                        "userId": "",
                        "accessCode": "",
                        "dialogId": "",
                    },
                },
            )
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            status_code = self._status_code_of(exc)
            logger.error(
                "ASO tsec request failed url=%s status=%s elapsed_ms=%s error=%s",
                self.settings.ticket_url,
                status_code,
                elapsed_ms,
                exc,
            )
            schedule_trace_event(
                event_type="aso",
                operation="tsec",
                outcome="error",
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                target=self.settings.ticket_url,
                error_type=type(exc).__name__,
                error_message=str(exc),
                tags=["aso", "tsec"],
            )
            raise DataSourceError(
                "Commercial info ticket request failed.",
                details={"ticket_url": self.settings.ticket_url, "error": str(exc)},
            ) from exc

        # NOTE: the tsec value is a secret; never log it or include it in traces.
        tsec = response.headers.get("tsec", "").strip() or response.text.strip()

        if not tsec:
            logger.error(
                "ASO tsec response did not include tsec url=%s status=%s elapsed_ms=%s",
                self.settings.ticket_url,
                response.status_code,
                elapsed_ms,
            )
            schedule_trace_event(
                event_type="aso",
                operation="tsec",
                outcome="error",
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
                target=self.settings.ticket_url,
                error_type="MissingTsec",
                error_message="ticket response did not include tsec",
                tags=["aso", "tsec"],
            )
            raise DataSourceError(
                "Commercial info ticket response did not include tsec.",
                details={"ticket_url": self.settings.ticket_url},
            )

        logger.info(
            "ASO tsec obtained url=%s status=%s elapsed_ms=%s",
            self.settings.ticket_url,
            response.status_code,
            elapsed_ms,
        )
        schedule_trace_event(
            event_type="aso",
            operation="tsec",
            outcome="ok",
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            target=self.settings.ticket_url,
            response_summary={"has_tsec": True},
            tags=["aso", "tsec"],
        )
        return tsec

    @staticmethod
    def _status_code_of(exc: Exception) -> int | None:
        response = getattr(exc, "response", None)
        return getattr(response, "status_code", None)

    @staticmethod
    def _mask_document(document_number: str) -> str:
        value = (document_number or "").strip()
        if len(value) <= 4:
            return "***"
        return f"****{value[-4:]}"

    @staticmethod
    def _summarize_commercial_info(
        response: httpx.Response,
        payload: Any,
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {"bytes": len(response.content)}
        if isinstance(payload, dict):
            summary["keys"] = list(payload.keys())
            data = payload.get("data", {}) or {}
            history = data.get("history", {}) or {}
            obligations = history.get("obligations", []) or []
            summary["obligations"] = len(obligations)
            third_party = data.get("thirdPartyResponse", {}) or {}
            # Non-PII status of the external consult (e.g. "CONSULTA EXITOSA").
            summary["third_party_status"] = third_party.get("name")
        return summary

    def _map_document_type(self, personal_type: str) -> str:
        personal_type_id = personal_type.strip()
        document_type_by_id = {
            "1": "C.C",
            "2": "C.E"

        }

        return document_type_by_id.get(personal_type_id, personal_type_id)

    def _extract_last_name(
        self,
        value: str,
        *,
        from_full_name: bool = False,
    ) -> str:
        text = (value or "").strip()
        if not text:
            return ""

        if from_full_name:
            name_parts = text.split()
            if len(name_parts) >= 2:
                return name_parts[-2]

        return text

    def _validate_api_settings(self) -> None:
        missing_settings = [
            key
            for key, value in {
                "COMMERCIAL_INFO_TICKET_URL": self.settings.ticket_url,
                "COMMERCIAL_INFO_OVERVIEW_URL": self.settings.overview_url,
                "COMMERCIAL_INFO_API_USER_ID": self.settings.api_user_id,
                "COMMERCIAL_INFO_API_CONSUMER_ID": self.settings.api_consumer_id,
                "COMMERCIAL_INFO_API_PASSWORD": self.settings.api_password,
            }.items()
            if not value
        ]

        if missing_settings:
            raise DataSourceError(
                "Commercial info API settings are incomplete.",
                details={"missing_settings": missing_settings},
            )

    def _build_mock_path(self, personal_id: str) -> Path:
        return self.settings.commercial_info_mock_dir / (
            f"{self.settings.commercial_info_file_prefix}{personal_id}.json"
        )

    def _find_mock_path(self, personal_id: str) -> Path:
        json_path = self._build_mock_path(personal_id)

        if json_path.exists() or not personal_id.isdigit():
            return json_path

        padded_json_path = self._build_mock_path(personal_id.zfill(15))

        if padded_json_path.exists():
            return padded_json_path

        return json_path
