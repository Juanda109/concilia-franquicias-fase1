from decimal import Decimal, InvalidOperation

TIPOS_HOST = frozenset(("HA22", "HA26", "HA32"))


class NormalizacionHostError(ValueError):
    pass


def importe(valor, campo, linea):
    if valor is None or str(valor).strip() == "":
        raise NormalizacionHostError(
            f"Linea {linea}: importe obligatorio {campo} ausente"
        )

    try:
        numero = Decimal(str(valor).strip())
    except InvalidOperation as exc:
        raise NormalizacionHostError(
            f"Linea {linea}: {campo} no es numerico"
        ) from exc

    if not numero.is_finite():
        raise NormalizacionHostError(
            f"Linea {linea}: {campo} no es finito"
        )

    if numero.as_tuple().exponent < -2:
        raise NormalizacionHostError(
            f"Linea {linea}: {campo} supera dos decimales"
        )

    return numero


def obligatorio(registro, campo, linea):
    valor = registro.get(campo)

    if valor is None or not str(valor).strip():
        raise NormalizacionHostError(
            f"Linea {linea}: falta {campo}"
        )

    return str(valor).strip()


def opcional(registro, campo):
    valor = registro.get(campo)
    return str(valor).strip() if valor is not None and str(valor).strip() else None


def normalizar_host(tipo, registros, fecha_contable, id_archivo, correlation_id):
    if tipo not in TIPOS_HOST:
        raise NormalizacionHostError(
            f"Tipo Host no soportado: {tipo}"
        )

    resultado = []

    for registro in registros:
        linea = registro.get("numero_linea")

        tx = obligatorio(registro, "TX_ORIGEN", linea)

        if tx != tipo:
            raise NormalizacionHostError(
                f"Linea {linea}: TX_ORIGEN {tx} no corresponde a {tipo}"
            )

        cuenta = obligatorio(registro, "NUCTA", linea)

        debe = importe(registro.get("DEBE"), "DEBE", linea)
        haber = importe(registro.get("HABER"), "HABER", linea)

        saldo = None

        if tipo == "HA32":
            saldo = importe(
                registro.get("SALDO_INICIAL"),
                "SALDO_INICIAL",
                linea
            )

        fecha_campo = "FECONT" if tipo == "HA32" else "FECON"
        fecha_registro = obligatorio(registro, fecha_campo, linea)

        from datetime import date

        try:
            fecha_interpretada = date.fromisoformat(fecha_registro)
        except ValueError as exc:
            raise NormalizacionHostError(
                f"Linea {linea}: fecha contable invalida"
            ) from exc

        if fecha_interpretada != fecha_contable:
            raise NormalizacionHostError(
                f"Linea {linea}: fecha del registro distinta a la jornada"
            )

        resultado.append({
            "id_archivo": id_archivo,
            "fecha_contable": fecha_contable,
            "tx_host": tx,
            "cuenta": cuenta,
            "centro": opcional(registro, "CEDESTIN"),
            "referencia": (
                opcional(registro, "NUMDO")
                if tipo != "HA32" else None
            ),
            "concepto": (
                opcional(registro, "DESCON")
                if tipo != "HA32" else None
            ),
            "valor_debe": debe,
            "valor_haber": haber,
            "valor_saldo": saldo,
            "valor_normalizado": debe - haber,
            "linea_origen": linea,
            "correlation_id": correlation_id,
        })

    return resultado
