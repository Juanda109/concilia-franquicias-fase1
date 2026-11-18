import csv
from pathlib import Path

MATRIZ = (
    Path(__file__).resolve().parents[2]
    / "catalogos"
    / "correspondencia_franquicias_host.csv"
)

def cargar_homologaciones():
    with MATRIZ.open(encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))

    resultado = {fila["cuenta_contable"]: fila for fila in filas}

    if len(filas) != 29 or len(resultado) != 29:
        raise ValueError("Matriz de homologacion incompatible")

    return resultado
