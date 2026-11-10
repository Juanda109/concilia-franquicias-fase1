"""Normalizacion funcional Credibanco Fase 1."""

from datetime import date
from decimal import Decimal, InvalidOperation


CUENTA_REPRESENTACION = (
    "017-REPRESENTACION  VENTA NAL (CENTRO 730)"
)


class NormalizacionCredibancoError(ValueError):
    pass


def normalizar_cant(
    *,
    registros,
    fecha_contable,
    id_archivo,
    correlation_id,
):
    """Normaliza CANT para la cuenta de representacion."""

    if not isinstance(fecha_contable, date):
        fecha_contable = date.fromisoformat(
            str(fecha_contable)
        )

    filas = []
    lineas = set()

    for registro in registros:
        cuenta = registro.get("CUENTA", "")
        linea = registro.get("numero_linea")

        if cuenta != CUENTA_REPRESENTACION:
            raise NormalizacionCredibancoError(
                "Cuenta CANT sin regla de valor aprobada"
            )

        if not isinstance(linea, int) or linea <= 0:
            raise NormalizacionCredibancoError(
                "Linea de origen CANT invalida"
            )

        if linea in lineas:
            raise NormalizacionCredibancoError(
                "Linea de origen CANT duplicada"
            )

        lineas.add(linea)

        try:
            valor = Decimal(str(registro["VL_TOTAL"]))
        except (
            KeyError,
            TypeError,
            InvalidOperation,
        ) as exc:
            raise NormalizacionCredibancoError(
                "VL_TOTAL CANT invalido"
            ) from exc

        if not valor.is_finite():
            raise NormalizacionCredibancoError(
                "VL_TOTAL CANT no finito"
            )

        tx = str(registro.get("TX", ""))
        bin_dest = str(registro.get("BIN_DEST", ""))

        if not tx or not bin_dest:
            raise NormalizacionCredibancoError(
                "Identificadores CANT incompletos"
            )

        filas.append({
            "id_archivo": id_archivo,
            "fecha_contable": fecha_contable,
            "proceso_origen": "CREDIBANCO",
            "reporte_origen": "CANT",
            "franquicia": "CREDIBANCO",
            "cuenta": cuenta,
            "concepto": "VL_TOTAL",
            "referencia": (
                f"TX={tx};BIN={bin_dest};LINEA={linea}"
            ),
            "moneda": None,
            "valor": valor,
            "linea_origen": linea,
            "correlation_id": correlation_id,
        })

    return filas
