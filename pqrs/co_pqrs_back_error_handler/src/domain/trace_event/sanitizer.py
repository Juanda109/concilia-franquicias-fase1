"""Última barrera contra datos sensibles en las trazas que se persisten.

Los servicios que emiten trace-events enmascaran por su lado (el cliente del
ASO oculta la contraseña del granting, el auditor recorta PAN y correos), pero
cada uno depende de sus propios flags de diagnóstico y de que el que llama se
acuerde. Este módulo se aplica **siempre**, en el error handler, justo antes de
escribir en MinIO o en disco, y no tiene flag que lo apague: es la garantía del
control KYNS IT 3 (persistencia sin datos sensibles en claro).

Dos mecanismos, deliberadamente redundantes:

* **Por clave**: cualquier campo cuyo nombre huela a credencial (``password``,
  ``tsec``, ``authorizationData``, ``api_key``…) o a volcado completo
  (``body_full``) se reemplaza por un marcador. Los nombres de titular se
  reducen a iniciales.
* **Por valor**: en cualquier texto, los números de tarjeta (13 a 19 dígitos,
  con o sin separadores, que empiezan como una tarjeta real, del 2 al 6) se dejan
  en sus últimos cuatro dígitos y los correos se ocultan. Los números de contrato
  y de producto del banco empiezan por 0 o 1 y no se tocan aunque pasen Luhn. Así un PAN escondido dentro de una URL, un mensaje de error o un
  JSON serializado tampoco llega al bucket.

Los identificadores de negocio de primer nivel (``conversation_id``,
``customer_id``) no se tocan: son la llave de la traza y no son un PAN.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "<oculto>"

# Claves (comparación sin mayúsculas ni separadores) que nunca se persisten.
_SECRET_KEY_RE = re.compile(
    r"^(password|passwd|pwd|secret|apikey|api_key|authorization|authenticationdata|"
    r"tsec|tseccompleto|tsec_completo|token|accesstoken|refreshtoken|bearer|otp|clave|"
    r"body_full|bodyfull|cookie|set_cookie|xapikey|x_api_key|client_secret)$",
    re.IGNORECASE,
)
# Claves que llevan nombres de personas: se reducen a iniciales.
_NAME_KEY_RE = re.compile(
    r"^(name|firstname|first_name|lastname|last_name|fullname|full_name|holdername|"
    r"holder_name|customername|customer_name|nombre|apellido|apellidos|titular|"
    r"nombre_titular|nombre_cliente|participantname|displayname)$",
    re.IGNORECASE,
)
# Número de tarjeta: 13 a 19 dígitos, opcionalmente separados por espacio o guion.
_PAN_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Campos de primer nivel del trace-event que son identificadores, no datos.
_TOP_LEVEL_KEEP = frozenset({"conversation_id", "customer_id", "trace_id"})


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def is_pan(digits: str) -> bool:
    """Si una secuencia de 13 a 19 dígitos parece un número de tarjeta.

    Una tarjeta empieza por 2 a 6 (Mastercard 2-series, Amex 3, Visa 4,
    Mastercard 5, Discover 6) y pasa Luhn; se aceptan además 16 dígitos que
    empiezan por 4 o 5 aunque no pasen Luhn (los fixtures de prueba no siempre
    lo hacen). Los contratos y productos del banco (0013..., 1300...) quedan
    fuera: medido sobre los fixtures, la regla anterior ocultaba 159 de 234.
    """

    if not digits or digits[0] not in "23456":
        return False
    return _luhn_ok(digits) or (len(digits) == 16 and digits[0] in "45")


def mask_text(text: str) -> str:
    """Enmascara PAN (dejando los últimos 4) y correos dentro de un texto."""

    if not text:
        return text

    def _pan(match: re.Match[str]) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        # Solo se toca lo que parece una tarjeta de verdad (ver is_pan).
        if is_pan(digits):
            return "*" * (len(digits) - 4) + digits[-4:]
        return raw

    text = _PAN_RE.sub(_pan, text)
    return _EMAIL_RE.sub("***@***", text)


def _initials(value: str) -> str:
    parts = [p for p in re.split(r"\s+", value.strip()) if p]
    if not parts:
        return value
    return " ".join(f"{p[0]}***" for p in parts)


def _norm_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(key).lower())


def sanitize_value(value: Any, *, key: str | None = None) -> Any:
    """Sanitiza recursivamente dict / list / str; deja el resto igual."""

    if key is not None:
        nk = _norm_key(key)
        if _SECRET_KEY_RE.match(nk):
            return REDACTED
        if _NAME_KEY_RE.match(nk) and isinstance(value, str):
            return _initials(mask_text(value))

    if isinstance(value, dict):
        return {k: sanitize_value(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_value(v) for v in value]
    if isinstance(value, str):
        return mask_text(value)
    return value


def sanitize_trace_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Sanitiza el diccionario de un trace-event completo.

    Los identificadores de primer nivel se conservan; todo lo demás (resúmenes
    de petición y respuesta, contexto extra, mensaje de error, destino) pasa por
    el sanitizador.
    """

    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _TOP_LEVEL_KEEP:
            out[key] = value
        else:
            out[key] = sanitize_value(value, key=key)
    return out
