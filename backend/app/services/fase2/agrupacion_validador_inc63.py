"""INC63: agrupacion diagnostica de ESTRUCTURA Redeban."""

from collections import defaultdict
from decimal import Decimal, InvalidOperation


def normalizar_nivel(valor):
    if valor is None:
        return None

    texto = str(valor).strip()
    return texto if texto else None


def decimal_exacto(valor):
    if valor is None:
        return Decimal("0")

    if isinstance(valor, bool):
        raise ValueError("Importe booleano invalido")

    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Importe monetario invalido") from exc

    if not numero.is_finite():
        raise ValueError("Importe monetario no finito")

    return numero


def agrupar_estructura(registros, version_catalogo):
    """Agrupa importes actuales sin homologacion contable."""

    if not version_catalogo:
        raise ValueError("Version de catalogo requerida")

    grupos = defaultdict(
        lambda: {
            "debito": Decimal("0"),
            "credito": Decimal("0"),
            "neto": Decimal("0"),
            "cantidad_filas": 0,
            "filas_origen": [],
        }
    )

    sin_nivel = []
    filas_vistas = set()

    for fila in registros:
        numero = fila["fila_excel"]

        if not isinstance(numero, int) or isinstance(numero, bool):
            raise ValueError("Fila Excel invalida")

        # Rango real de Tabla dinamica1: E3:U3245.
        if numero < 4 or numero > 3245:
            continue

        if numero in filas_vistas:
            raise ValueError(
                f"Fila ESTRUCTURA duplicada: {numero}"
            )

        filas_vistas.add(numero)

        nivel = normalizar_nivel(fila.get("nivel_1"))

        if nivel is None:
            sin_nivel.append({
                "fila_excel": numero,
                "codigo_operacion": fila.get("codigo_operacion"),
                "debito_original": (
                    None if fila.get("debito") is None
                    else str(decimal_exacto(fila["debito"]))
                ),
                "credito_original": (
                    None if fila.get("credito") is None
                    else str(decimal_exacto(fila["credito"]))
                ),
                "neto_original": (
                    None if fila.get("neto") is None
                    else str(decimal_exacto(fila["neto"]))
                ),
                "estado": "SIN_NIVEL",
                "certificado": False,
            })
            continue

        grupo = grupos[nivel]

        grupo["debito"] += decimal_exacto(fila.get("debito"))
        grupo["credito"] += decimal_exacto(fila.get("credito"))
        grupo["neto"] += decimal_exacto(fila.get("neto"))

        grupo["cantidad_filas"] += 1
        grupo["filas_origen"].append(numero)

    resultados = []

    for nivel in sorted(grupos):
        grupo = grupos[nivel]

        diferencia_integridad = (
            grupo["neto"]
            - grupo["debito"]
            - grupo["credito"]
        )

        resultados.append({
            "nivel": nivel,
            "debito_estructura_actual": str(grupo["debito"]),
            "credito_estructura_actual": str(grupo["credito"]),
            "neto_estructura_actual": str(grupo["neto"]),
            "cantidad_filas": grupo["cantidad_filas"],
            "diferencia_integridad": str(diferencia_integridad),
            "estado_integridad": (
                "INTEGRIDAD_CORRECTA"
                if diferencia_integridad == 0
                else "DIFERENCIA_INTEGRIDAD"
            ),
            "filas_origen": grupo["filas_origen"],
            "version_catalogo": version_catalogo,
            "estado": "AGRUPACION_DIAGNOSTICA",
            "certificado": False,
        })

    return {
        "version_catalogo": version_catalogo,
        "cantidad_niveles": len(resultados),
        "niveles": resultados,
        "sin_nivel": sin_nivel,
        "cantidad_sin_nivel": len(sin_nivel),
        "estado": "DIAGNOSTICO_NO_HOMOLOGADO",
        "certificado": False,
    }
