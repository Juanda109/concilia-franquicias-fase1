"""Filtro contable de Concilia V1.

Solo aplica a la seleccion para conciliacion.
No altera ingesta, persistencia ni registros originales.
"""

from app.services.catalogo_cuentas_host import (
    cargar_cuentas_host,
    cuenta_autorizada,
    obtener_regla_cuenta,
)


def seleccionar_movimientos_host(movimientos):
    """Selecciona movimientos de las 29 cuentas autorizadas."""
    autorizadas = cargar_cuentas_host()
    resultado = []

    for movimiento in movimientos:
        cuenta = str(movimiento.get("cuenta") or "").strip()
        centro = str(movimiento.get("centro") or "").strip()

        if cuenta not in autorizadas:
            continue

        if centro not in ("0017", "17"):
            continue

        resultado.append(movimiento)

    return resultado


def clasificar_cuenta_host(cuenta):
    """Devuelve la configuracion contable o None."""
    return obtener_regla_cuenta(cuenta)


def validar_cuenta_correspondencia(cuenta, centro):
    """Valida cuenta y centro antes de evaluar correspondencias."""
    return (
        cuenta_autorizada(str(cuenta).strip())
        and str(centro).strip() in ("0017", "17")
    )
