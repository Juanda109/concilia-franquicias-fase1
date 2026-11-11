from pathlib import Path
import csv

CATALOGO = (
    Path(__file__).resolve().parents[1]
    / "catalogos"
    / "cuentas_contables_franquicias.csv"
)

def cargar_cuentas_host():
    with CATALOGO.open(encoding="utf-8-sig", newline="") as archivo:
        filas = list(csv.DictReader(archivo))

    cuentas = {fila["cuenta_contable"]: fila for fila in filas}

    if len(filas) != 29 or len(cuentas) != 29:
        raise ValueError("Catalogo contable incompatible")

    if any(fila["centro"] != "0017" for fila in filas):
        raise ValueError("Centro contable incompatible")

    return cuentas

def cuenta_autorizada(cuenta):
    return str(cuenta) in cargar_cuentas_host()

def obtener_regla_cuenta(cuenta):
    return cargar_cuentas_host().get(str(cuenta))
