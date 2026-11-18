"""INC60: lectura diagnostica del catalogo ESTRUCTURA."""

from collections import Counter
from hashlib import sha256
from pathlib import Path

from openpyxl import load_workbook


def leer_catalogo(ruta):
    archivo = Path(ruta)

    if not archivo.is_file():
        raise ValueError("Plantilla inexistente")

    if archivo.suffix.lower() not in (".xlsx", ".xlsm"):
        raise ValueError("Formato de plantilla invalido")

    version = sha256(archivo.read_bytes()).hexdigest()

    libro = load_workbook(
        archivo,
        read_only=True,
        data_only=False,
        keep_links=False,
    )

    try:
        if "ESTRUCTURA" not in libro.sheetnames:
            raise ValueError("Hoja ESTRUCTURA inexistente")

        hoja = libro["ESTRUCTURA"]
        registros = []

        for numero, valores in enumerate(
            hoja.iter_rows(
                min_row=4,
                max_row=3251,
                min_col=3,
                max_col=18,
                values_only=True,
            ),
            start=4,
        ):
            codigo = valores[3]

            if codigo is None or not str(codigo).strip():
                continue

            tipo = str(valores[2] or "").strip()
            categoria = tipo[:1]

            if categoria not in ("A", "B", "C"):
                raise ValueError(
                    f"Tipo economico invalido fila {numero}"
                )

            registros.append({
                "version_catalogo": version,
                "fila_excel": numero,
                "centro_costos": valores[0],
                "cuenta_contable": valores[1],
                "tipo_operacion": tipo,
                "categoria": categoria,
                "codigo_operacion": str(codigo).strip(),
                "movimiento": valores[6],
                "emisor_adquirente": valores[7],
                "nombre_operacion": valores[8],
                "referencia_contable_formula": valores[10],
                "debito_formula": valores[11],
                "credito_formula": valores[12],
                "neto_formula": valores[13],
                "cantidad_debito_formula": valores[14],
                "cantidad_credito_formula": valores[15],
            })

        codigos = Counter(
            fila["codigo_operacion"]
            for fila in registros
        )

        return {
            "version_catalogo": version,
            "archivo_origen": archivo.name,
            "cantidad_registros": len(registros),
            "codigos_distintos": len(codigos),
            "codigos_repetidos": sum(
                cantidad > 1
                for cantidad in codigos.values()
            ),
            "registros": registros,
            "certificado": False,
        }

    finally:
        libro.close()
