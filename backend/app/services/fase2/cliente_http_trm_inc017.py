"""RECON_F2_017 Lote 5: cliente HTTP TRM.

Consulta un dominio fijo de Datos Abiertos Colombia.
No confirma tasas, no escribe BD y no certifica conciliaciones.
"""

import json
import os
import ssl

from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import (
    Request,
    build_opener,
    HTTPSHandler,
    HTTPRedirectHandler,
)

from app.services.fase2.fuente_trm_oficial_inc017 import (
    validar_respuesta_oficial,
    ErrorFuenteTRM,
)

URL = "https://www.datos.gov.co/resource/32sa-8pi3.json"


class ErrorConsultaTRM(RuntimeError):
    pass


class SinRedirecciones(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def consultar_trm_http(fecha_contable: date) -> dict:
    if type(fecha_contable) is not date:
        raise ErrorConsultaTRM("Fecha contable invalida")

    if os.getenv("CONCILIA_TRM_HTTP_HABILITADO") != "1":
        raise ErrorConsultaTRM(
            "Consulta HTTP TRM no habilitada"
        )

    fecha = fecha_contable.isoformat()

    filtros = {
        "$where": (
            f"vigenciadesde <= '{fecha}T23:59:59' "
            f"AND vigenciahasta >= '{fecha}T00:00:00'"
        ),
        "$limit": "10",
    }

    url = URL + "?" + urlencode(filtros)

    solicitud = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Concilia-TRM-INC017/1.0",
        },
        method="GET",
    )

    opener = build_opener(
        HTTPSHandler(context=ssl.create_default_context()),
        SinRedirecciones(),
    )

    try:
        with opener.open(solicitud, timeout=10) as respuesta:
            if respuesta.status != 200:
                raise ErrorConsultaTRM(
                    "Respuesta HTTP TRM no exitosa"
                )

            tipo = respuesta.headers.get(
                "Content-Type", ""
            ).lower()

            if "application/json" not in tipo:
                raise ErrorConsultaTRM(
                    "Respuesta TRM no es JSON"
                )

            contenido = respuesta.read(262145)

            if len(contenido) > 262144:
                raise ErrorConsultaTRM(
                    "Respuesta TRM demasiado grande"
                )

    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ErrorConsultaTRM(
            "Fuente TRM no disponible"
        ) from exc

    try:
        registros = json.loads(contenido.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ErrorConsultaTRM(
            "Respuesta TRM invalida"
        ) from exc

    if not isinstance(registros, list):
        raise ErrorConsultaTRM(
            "Estructura TRM inesperada"
        )

    try:
        return validar_respuesta_oficial(
            fecha_contable=fecha_contable,
            registros=registros,
            procedencia_verificada=True,
        )
    except (ErrorFuenteTRM, ValueError) as exc:
        raise ErrorConsultaTRM(
            "Datos TRM incompatibles"
        ) from exc
