import re
from datetime import date
from pathlib import Path
from pypdf import PdfReader
from app.parsers.base import Parser
from app.ingestion.result import IngestionResult, RecordError

_MESES = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
          'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}

_GRUPO_RE = re.compile(r'^(\d+)\s*\((.+)\)$')
_FILA_RE = re.compile(
    r'^\s*(\d+)\s{2,}(.+?)\s{2,}([A-Z]{3})\s{2,}([\d,]+\.\d{2})\s{2,}(CR|DB)\s{2,}'
    r'(\d{2}\s[A-Za-z]{3}\s\d{4})\s{2,}(\d{2}\s[A-Za-z]{3}\s\d{4})\s*$'
)
_OMITIR_PREFIJOS = ("Processing Date", "Value Date", "FTSRE", "Code", "Report generated on")


def _fecha(v):
    """"03 Jul 2026" -> "2026-07-03"; None si no calza."""
    m = re.match(r"^(\d{2})\s+([A-Za-z]{3})\s+(\d{4})$", (v or "").strip())
    if not m:
        return None
    mes = _MESES.get(m.group(2).upper())
    if not mes:
        return None
    try:
        return date(int(m.group(3)), mes, int(m.group(1))).isoformat()
    except ValueError:
        return None


class ISSParser(Parser):
    """International Settlement Service: detalle de transferencia de fondos
    (FTSRE) de la liquidacion de VISA - el MONTO_NETO coincide con el NET
    SETTLEMENT AMOUNT del archivo VSS del mismo proceso, pero es un insumo
    independiente (reporte distinto, en PDF)."""
    tipo_insumo = "ISS"

    def parse(self, source: Path):
        r = IngestionResult(self.tipo_insumo)
        try:
            reader = PdfReader(source)
        except Exception as exc:
            r.errors.append(RecordError(None, None, "PDF_INVALIDO", str(exc)))
            return r

        entidad_codigo = None
        entidad_nombre = None
        registro_actual = None
        numero_linea = 0
        for pagina in reader.pages:
            texto = pagina.extract_text(extraction_mode="layout") or ""
            for linea in texto.split("\n"):
                numero_linea += 1
                vacia = not linea.strip()
                if vacia or linea.strip().startswith(_OMITIR_PREFIJOS):
                    continue

                m = _GRUPO_RE.match(linea.strip())
                if m:
                    entidad_codigo, entidad_nombre = m.group(1), m.group(2).strip()
                    registro_actual = None
                    continue

                m = _FILA_RE.match(linea.rstrip())
                if m:
                    registro_actual = {
                        "numero_linea": numero_linea,
                        "ENTIDAD_CODIGO": entidad_codigo,
                        "ENTIDAD_NOMBRE": entidad_nombre,
                        "FTSRE": m.group(1),
                        "NOMBRE": m.group(2).strip(),
                        "MONEDA": m.group(3),
                        "MONTO_NETO": float(m.group(4).replace(",", "")),
                        "NATURALEZA": m.group(5),
                        "FECHA_VALOR": _fecha(m.group(6)),
                        "FECHA_PROCESAMIENTO": _fecha(m.group(7)),
                    }
                    r.records.append(registro_actual)
                    continue

                # El nombre de la entidad se parte en 2 lineas cuando es largo
                # (ej. "Banco Bilbao Vizcaya Argentaria" + "Colombia").
                if registro_actual is not None:
                    registro_actual["NOMBRE"] = f'{registro_actual["NOMBRE"]} {linea.strip()}'.strip()

        r.controls.append({"codigo": "TOTAL_REGISTROS", "obtenido": len(r.records)})
        return r
