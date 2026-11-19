"""RECON_F2_017: validacion documental de TRM Visa.

Servicio puro, sin consultas externas ni persistencia.
No certifica conciliacion ni asigna importes a cuentas.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class ErrorTRMVisa(ValueError):
    pass


CENTAVO = Decimal("0.01")
PASO_TRM = Decimal("0.0001")


def decimal_seguro(valor, *, decimales):
    if isinstance(valor, bool) or not isinstance(
        valor, (str, Decimal)
    ):
        raise ErrorTRMVisa("Importe o tasa invalida")

    try:
        numero = Decimal(valor)
    except (InvalidOperation, ValueError) as exc:
        raise ErrorTRMVisa("Decimal invalido") from exc

    if not numero.is_finite():
        raise ErrorTRMVisa("Valor no finito")

    paso = Decimal(1).scaleb(-decimales)

    if numero != numero.quantize(paso):
        raise ErrorTRMVisa("Precision decimal no permitida")

    return numero.quantize(paso)


def validar_trm(valor):
    numero = decimal_seguro(valor, decimales=4)

    if numero <= 0:
        raise ErrorTRMVisa("La TRM debe ser positiva")

    if numero >= Decimal("100000000000000"):
        raise ErrorTRMVisa("TRM fuera de rango")

    return numero


@dataclass(frozen=True)
class ConfirmacionTRM:
    id_jornada: int
    fecha_contable: date
    fecha_referencia: date
    trm_oficial: Decimal | None
    trm_aplicada: Decimal
    fuente: str
    modificada_manualmente: bool
    justificacion: str | None
    usuario_confirmacion: str
    version: int
    confirmada: bool = True

    def __post_init__(self):
        if type(self.id_jornada) is not int or self.id_jornada <= 0:
            raise ErrorTRMVisa("Jornada invalida")

        if type(self.version) is not int or self.version <= 0:
            raise ErrorTRMVisa("Version invalida")

        if (
            type(self.fecha_contable) is not date
            or type(self.fecha_referencia) is not date
            or self.fecha_contable != self.fecha_referencia
        ):
            raise ErrorTRMVisa(
                "La fecha TRM debe coincidir con la fecha contable"
            )

        if self.confirmada is not True:
            raise ErrorTRMVisa("TRM no confirmada")

        aplicada = validar_trm(self.trm_aplicada)

        oficial = (
            validar_trm(self.trm_oficial)
            if self.trm_oficial is not None else None
        )

        if not isinstance(self.fuente, str) or not self.fuente.strip():
            raise ErrorTRMVisa("Fuente obligatoria")

        if (
            not isinstance(self.usuario_confirmacion, str)
            or not self.usuario_confirmacion.strip()
        ):
            raise ErrorTRMVisa("Usuario autenticado obligatorio")

        if type(self.modificada_manualmente) is not bool:
            raise ErrorTRMVisa("Indicador manual invalido")

        if self.modificada_manualmente:
            if (
                not isinstance(self.justificacion, str)
                or not self.justificacion.strip()
            ):
                raise ErrorTRMVisa(
                    "Cambio manual requiere justificacion"
                )
        elif oficial is None or aplicada != oficial:
            raise ErrorTRMVisa(
                "Confirmacion oficial requiere tasa coincidente"
            )


def convertir_usd_cop(
    importe_usd: str | Decimal,
    confirmacion: ConfirmacionTRM,
) -> dict:
    if not isinstance(confirmacion, ConfirmacionTRM):
        raise ErrorTRMVisa("Confirmacion TRM requerida")

    # Se valida nuevamente para impedir uso de datos inconsistentes.
    confirmacion.__post_init__()

    usd = decimal_seguro(importe_usd, decimales=2)
    trm = validar_trm(confirmacion.trm_aplicada)

    cop = (usd * trm).quantize(
        CENTAVO, rounding=ROUND_HALF_UP
    )

    return {
        "id_jornada": confirmacion.id_jornada,
        "fecha_referencia": confirmacion.fecha_referencia.isoformat(),
        "version_trm": confirmacion.version,
        "importe_usd": str(usd),
        "trm_aplicada": str(trm),
        "importe_cop": str(cop),
        "moneda_origen": "USD",
        "moneda_destino": "COP",
        "modo": "CONVERSION_DOCUMENTAL",
        "certificado": False,
        "conciliado_host": False,
    }
