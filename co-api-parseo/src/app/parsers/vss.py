import re
from datetime import date
from pathlib import Path
from app.parsers.base import Parser
from app.ingestion.result import IngestionResult, RecordError

_MESES = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
          'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}


def _fecha(v):
    """"03JUL26" -> "2026-07-03"; None si no calza (formato DDMMMAA)."""
    if not v or len(v) != 7:
        return None
    mes = _MESES.get(v[2:5].upper())
    if not mes:
        return None
    try:
        return date(2000 + int(v[5:7]), mes, int(v[0:2])).isoformat()
    except ValueError:
        return None


def _monto(token):
    """"370,449.13CR" -> (370449.13,'CR'); "" -> (None,None)."""
    token = (token or "").strip()
    if not token:
        return None, None
    m = re.match(r"^([\d,]+\.\d{2})(CR|DB)?$", token)
    if not m:
        return None, None
    return float(m.group(1).replace(",", "")), m.group(2)


def _entero(token):
    token = (token or "").strip().replace(",", "")
    if not token or not token.isdigit():
        return None
    return int(token)


def _campo(patron, texto):
    m = re.search(patron, texto)
    return m.group(1).strip() if m else None


_SECCIONES = {"ACQUIRER TRANSACTIONS", "ISSUER TRANSACTIONS", "OTHER TRANSACTIONS"}
# Columnas de VSS-115: CONCEPTO | COUNT cr | AMOUNT cr | COUNT db | AMOUNT db | COUNT total | AMOUNT total(+CR/DB)
_BOUNDS_115 = [0, 33, 38, 57, 73, 92, 108, 135]
# Columnas de VSS-120: CONCEPTO | RATE TABLE ID | COUNT | CLEARING AMOUNT(+CR/DB) | INTERCHANGE VALUE CREDITS | INTERCHANGE VALUE DEBITS
_BOUNDS_120 = [0, 40, 55, 70, 95, 115, 135]


class VSSParser(Parser):
    tipo_insumo = "VSS"

    def parse(self, source: Path):
        r = IngestionResult(self.tipo_insumo)
        text = source.read_text(encoding="utf-8", errors="replace")
        paginas = [p for p in text.split("\f") if p.strip()]
        if not paginas:
            r.errors.append(RecordError(None, None, "ARCHIVO_VACIO", "El archivo no tiene contenido"))
            return r

        reportes = {}
        orden = []
        base_linea = 1
        for pagina in paginas:
            lineas = pagina.split("\n")
            report_id = _campo(r"REPORT ID:\s*(VSS-\d+)", pagina)
            if not report_id:
                r.errors.append(RecordError(base_linea, None, "REPORT_ID_AUSENTE", "Página sin REPORT ID"))
                base_linea += pagina.count("\n")
                continue
            numero_pagina = _entero(_campo(r"PAGE:\s*(\d+)", pagina))
            if report_id not in reportes:
                reportes[report_id] = {
                    "_key": report_id,
                    "numero_linea": base_linea,
                    "REPORT_ID": report_id,
                    "REPORTING_FOR": _campo(r"REPORTING FOR:\s*(\S.*?)\s{2,}", pagina),
                    "ROLLUP_TO": _campo(r"ROLLUP TO:\s*(\S.*?)\s{2,}", pagina),
                    "FUNDS_XFER_ENTITY": _campo(r"FUNDS XFER ENTITY:\s*(\S.*?)\s{2,}", pagina),
                    "PROC_DATE": _fecha(_campo(r"PROC DATE:\s*(\d{2}[A-Z]{3}\d{2})", pagina)),
                    "REPORT_DATE": _fecha(_campo(r"REPORT DATE:\s*(\d{2}[A-Z]{3}\d{2})", pagina)),
                    "SETTLEMENT_CURRENCY": _campo(r"SETTLEMENT CURRENCY:\s*([A-Z]{3})", pagina),
                }
                orden.append(report_id)

            if report_id == "VSS-110":
                pass  # solo control de cuadre (ver mas abajo), no genera detalle
            elif report_id == "VSS-115":
                self._detalle_115(lineas, report_id, numero_pagina, base_linea, r)
            elif report_id == "VSS-120":
                clearing_currency = _campo(r"CLEARING CURRENCY:\s*([A-Z]{3})", pagina)
                self._detalle_120(lineas, report_id, numero_pagina, clearing_currency, base_linea, r)
            base_linea += pagina.count("\n")

        for report_id in orden:
            r.reportes.append(reportes[report_id])

        # Cuadre: el NET SETTLEMENT AMOUNT de VSS-110 debe coincidir con el
        # FINAL SETTLEMENT NET AMOUNT de VSS-115 (mismo neto, dos reportes).
        a = re.search(r"NET SETTLEMENT AMOUNT\s+[\d,]+\.\d{2}\s+[\d,]+\.\d{2}\s+([\d,]+\.\d{2})(CR|DB)", text)
        b = re.search(r"FINAL SETTLEMENT NET AMOUNT\s+([\d,]+\.\d{2})(CR|DB)", text)
        if a and b:
            r.controls.append({
                "codigo": "VSS_110_115_NET",
                "estado": "OK" if a.groups() == b.groups() else "ERROR",
                "vss110": "".join(a.groups()), "vss115": "".join(b.groups()),
            })
        r.controls.append({"codigo": "TOTAL_REGISTROS", "obtenido": len(r.records)})
        return r

    def _detalle_115(self, lineas, report_id, numero_pagina, base_linea, r):
        seccion = None
        for i, texto in enumerate(lineas):
            etiqueta = texto.strip()
            if etiqueta in _SECCIONES:
                seccion = etiqueta
                continue
            if not etiqueta or etiqueta.startswith("***") or etiqueta.startswith("FINAL SETTLEMENT") or seccion is None:
                continue
            partes = [texto[_BOUNDS_115[k]:_BOUNDS_115[k + 1]] for k in range(len(_BOUNDS_115) - 1)]
            concepto = partes[0].strip()
            if not concepto or concepto.startswith("TOTAL"):
                continue
            count_total = _entero(partes[5])
            monto_total, naturaleza = _monto(partes[6])
            monto_credito, _ = _monto(partes[2])
            monto_debito, _ = _monto(partes[4])
            r.records.append({
                "numero_linea": base_linea + i,
                "_report_key": report_id,
                "NUMERO_PAGINA": numero_pagina,
                "SECCION": seccion,
                "CONCEPTO": concepto,
                "COUNT": count_total,
                "CREDIT_AMOUNT": monto_credito,
                "DEBIT_AMOUNT": monto_debito,
                "TOTAL_AMOUNT": monto_total,
                "NATURALEZA": naturaleza,
            })

    def _detalle_120(self, lineas, report_id, numero_pagina, clearing_currency, base_linea, r):
        seccion = None
        subtipo = None
        concepto_actual = None
        for i, texto in enumerate(lineas):
            etiqueta = texto.strip()
            if etiqueta in _SECCIONES:
                seccion, subtipo, concepto_actual = etiqueta, None, None
                continue
            if not etiqueta or etiqueta.startswith("***") or seccion is None:
                continue
            partes = [texto[_BOUNDS_120[k]:_BOUNDS_120[k + 1]] for k in range(len(_BOUNDS_120) - 1)]
            concepto = partes[0].strip()
            rate_table_id = partes[1].strip() or None
            count = _entero(partes[2])
            monto_clearing, naturaleza = _monto(partes[3])
            monto_credito, _ = _monto(partes[4])
            monto_debito, _ = _monto(partes[5])

            sin_valores = count is None and monto_clearing is None and monto_credito is None and monto_debito is None
            if sin_valores:
                # Sub-encabezado (ej. "PURCHASE") que agrupa las lineas de
                # detalle siguientes; no se persiste.
                if concepto and not concepto.startswith("TOTAL") and not concepto.startswith("NET"):
                    subtipo, concepto_actual = concepto, None
                continue
            if concepto.startswith("TOTAL") or concepto.startswith("NET"):
                continue  # subtotal/neto: se puede recalcular, no se persiste

            if concepto:
                concepto_actual = concepto
            if not concepto_actual or seccion is None:
                continue

            r.records.append({
                "numero_linea": base_linea + i,
                "_report_key": report_id,
                "NUMERO_PAGINA": numero_pagina,
                "CLEARING_CURRENCY": clearing_currency,
                "SECCION": seccion,
                "CONCEPTO": concepto_actual,
                "SUBTIPO": subtipo,
                "RATE_TABLE_ID": rate_table_id,
                "COUNT": count,
                "CLEARING_AMOUNT": monto_clearing,
                "CREDIT_AMOUNT": monto_credito,
                "DEBIT_AMOUNT": monto_debito,
                "NATURALEZA": naturaleza,
            })
