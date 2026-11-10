"""Fabricas de archivos para pruebas de integracion."""

import csv
import io
from datetime import date


COLUMNAS_HA22 = (
    "TX_ORIGEN", "TABLA_ORIGEN", "EMPRESA", "NUCTA",
    "CEORIGEN", "CEDESTIN", "FECON", "FEPROC",
    "NUMAS", "NUMAP", "DEBE", "HABER",
    "CLACON", "DESCON", "TIPAPUN", "NUMDO",
    "OBSERV", "OBSERV2", "CODUSU", "HORATR",
)


def generar_ha22_valido(fecha_contable: date) -> bytes:
    if not isinstance(fecha_contable, date):
        raise TypeError("fecha_contable debe ser date")

    registro = {
        "TX_ORIGEN": "HA22",
        "TABLA_ORIGEN": "PRUEBA",
        "EMPRESA": "13",
        "NUCTA": "299095302",
        "CEORIGEN": "17",
        "CEDESTIN": "17",
        "FECON": fecha_contable.isoformat(),
        "FEPROC": fecha_contable.isoformat(),
        "NUMAS": "1",
        "NUMAP": "1",
        "DEBE": "100.00",
        "HABER": "0.00",
        "CLACON": "PRUEBA",
        "DESCON": "MOVIMIENTO DE PRUEBA",
        "TIPAPUN": "1",
        "NUMDO": "DOC-PRUEBA",
        "OBSERV": "",
        "OBSERV2": "",
        "CODUSU": "TEST",
        "HORATR": "12.00.00",
    }

    salida = io.StringIO(newline="")
    escritor = csv.DictWriter(
        salida,
        fieldnames=COLUMNAS_HA22,
        delimiter="|",
        lineterminator='\n',
    )

    escritor.writeheader()
    escritor.writerow(registro)

    return salida.getvalue().encode("utf-8")


COLUMNAS_HA26 = (
    "TX_ORIGEN", "TABLA_ORIGEN", "EMPRESA", "NUCTA",
    "CEORIGEN", "CEDESTIN", "FECON", "FEPROC",
    "NUMAS", "NUMAP", "DEBE", "HABER",
    "CLACON", "DESCON", "TIPAPUN", "HAYNUMDO",
    "NUMDO", "OBSERV", "OBSERV2", "CODUSU", "HORATR",
)

COLUMNAS_HA32 = (
    "TX_ORIGEN", "TABLA_ORIGEN", "TABLA_ORIGEN1",
    "EMPRESA", "NUCTA", "CEDESTIN", "FECONT",
    "DEBE", "HABER", "SALDO_INICIAL",
)


def generar_ha26_valido(fecha_contable: date) -> bytes:
    registro = {
        "TX_ORIGEN": "HA26",
        "TABLA_ORIGEN": "PRUEBA",
        "EMPRESA": "13",
        "NUCTA": "299095302",
        "CEORIGEN": "17",
        "CEDESTIN": "17",
        "FECON": fecha_contable.isoformat(),
        "FEPROC": fecha_contable.isoformat(),
        "NUMAS": "1",
        "NUMAP": "1",
        "DEBE": "250.00",
        "HABER": "50.00",
        "CLACON": "PRUEBA",
        "DESCON": "MOVIMIENTO HA26",
        "TIPAPUN": "1",
        "HAYNUMDO": "S",
        "NUMDO": "DOC-HA26",
        "OBSERV": "",
        "OBSERV2": "",
        "CODUSU": "TEST",
        "HORATR": "12.00.00",
    }

    salida = io.StringIO(newline="")
    escritor = csv.DictWriter(
        salida,
        fieldnames=COLUMNAS_HA26,
        delimiter="|",
        lineterminator='\n',
    )
    escritor.writeheader()
    escritor.writerow(registro)
    return salida.getvalue().encode("utf-8")


def generar_ha32_valido(fecha_contable: date) -> bytes:
    registro = {
        "TX_ORIGEN": "HA32",
        "TABLA_ORIGEN": "HADV0030",
        "TABLA_ORIGEN1": "HADV0120",
        "EMPRESA": "13",
        "NUCTA": "299095302",
        "CEDESTIN": "17",
        "FECONT": fecha_contable.isoformat(),
        "DEBE": "300.00",
        "HABER": "100.00",
        "SALDO_INICIAL": "1500.00",
    }

    salida = io.StringIO(newline="")
    escritor = csv.DictWriter(
        salida,
        fieldnames=COLUMNAS_HA32,
        delimiter="|",
        lineterminator='\n',
    )
    escritor.writeheader()
    escritor.writerow(registro)
    return salida.getvalue().encode("utf-8")
