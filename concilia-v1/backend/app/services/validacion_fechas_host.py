from datetime import date, datetime


CAMPOS_FECHA_HOST = {
    "HA22": "FECON",
    "HA26": "FECON",
    "HA32": "FECONT",
}


class FechaInternaHostInvalida(ValueError):
    def __init__(self, errores):
        self.errores = errores
        super().__init__(
            "El archivo contiene fechas contables incompatibles"
        )

    def detalle(self):
        return {
            "codigo": "FECHA_INTERNA_NO_CORRESPONDE",
            "mensaje": str(self),
            "errores": self.errores,
        }


def interpretar_fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()

    if isinstance(valor, date):
        return valor

    if valor is None:
        return None

    try:
        return date.fromisoformat(str(valor).strip())
    except ValueError:
        return None


def validar_fechas_host(
    *,
    tipo_insumo,
    fecha_contable,
    resultado,
):
    if tipo_insumo not in CAMPOS_FECHA_HOST:
        return resultado

    fecha_jornada = interpretar_fecha(fecha_contable)

    if fecha_jornada is None:
        raise ValueError("Fecha contable de jornada invalida")

    campo = CAMPOS_FECHA_HOST[tipo_insumo]
    errores = []

    for registro in resultado.records:
        linea = registro.get("numero_linea")
        valor = registro.get(campo)
        fecha = interpretar_fecha(valor)

        if fecha != fecha_jornada:
            errores.append({
                "linea": linea,
                "codigo": "FECHA_REGISTRO_INVALIDA",
                "descripcion": (
                    f"{campo}={valor!r}; "
                    f"fecha contable esperada={fecha_jornada.isoformat()}"
                ),
            })

    if errores:
        raise FechaInternaHostInvalida(errores)

    return resultado
