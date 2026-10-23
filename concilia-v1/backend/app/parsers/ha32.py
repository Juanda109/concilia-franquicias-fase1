import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.parsers.base import Parser
from app.ingestion.result import IngestionResult, RecordError


COLUMNAS = [
    "TX_ORIGEN",
    "TABLA_ORIGEN",
    "TABLA_ORIGEN1",
    "EMPRESA",
    "NUCTA",
    "CEDESTIN",
    "FECONT",
    "DEBE",
    "HABER",
    "SALDO_INICIAL",
]


class HA32Parser(Parser):
    tipo_insumo = "HA32"
    expected_columns = 10

    def parse(self, source: Path) -> IngestionResult:
        resultado = IngestionResult(self.tipo_insumo)

        with source.open(
            encoding="utf-8-sig",
            errors="strict",
            newline=""
        ) as archivo:
            reader = csv.reader(archivo, delimiter="|")
            encabezado = next(reader, None)

            if encabezado != COLUMNAS:
                resultado.errors.append(
                    RecordError(
                        1, None, "HEADER_INVALIDO",
                        "Encabezado HA32 no corresponde al contrato"
                    )
                )
                return resultado

            for numero, valores in enumerate(reader, start=2):
                if len(valores) != self.expected_columns:
                    resultado.errors.append(
                        RecordError(
                            numero, None, "COLUMNAS_INVALIDAS",
                            "Se esperaban 10 columnas"
                        )
                    )
                    continue

                fila = dict(zip(
                    COLUMNAS,
                    [valor.strip() for valor in valores]
                ))

                if (
                    fila["TX_ORIGEN"] != "HA32"
                    or fila["TABLA_ORIGEN"] != "HADV0030"
                    or fila["TABLA_ORIGEN1"] != "HADV0120"
                ):
                    resultado.errors.append(
                        RecordError(
                            numero, fila["NUCTA"],
                            "ORIGEN_INVALIDO",
                            "Origen HA32 no corresponde al contrato"
                        )
                    )
                    continue

                try:
                    date.fromisoformat(fila["FECONT"])

                    for campo in (
                        "DEBE", "HABER", "SALDO_INICIAL"
                    ):
                        valor = Decimal(fila[campo])

                        if not valor.is_finite():
                            raise InvalidOperation(
                                "Importe no finito"
                            )

                        fila[campo] = valor

                except (ValueError, InvalidOperation):
                    resultado.errors.append(
                        RecordError(
                            numero, fila["NUCTA"],
                            "VALOR_INVALIDO",
                            "Fecha o importe HA32 invalido"
                        )
                    )
                    continue

                resultado.records.append({
                    "numero_linea": numero,
                    **fila
                })

        resultado.controls.append({
            "codigo": "TOTAL_REGISTROS",
            "obtenido": len(resultado.records)
        })

        return resultado
