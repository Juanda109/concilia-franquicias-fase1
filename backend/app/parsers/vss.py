# Autor: Gustavo Andres Camargo Duque
# Identificador: C805925
# Proyecto: Conciliacion Franquicias

"""Parser F1 VSS texto: secciones VSS-110, 115 y 120 de muestra real.
Guarda las filas monetarias con su reporte, pagina, monedas y valores originales.
NO suma secciones entre si ni infiere asiento contable; son vistas del mismo cierre.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from app.parsers.base import Parser
from app.ingestion.result import IngestionResult, RecordError

REPORT=re.compile(r'^\s*REPORT ID:\s*(VSS-\d+)\b.*?PAGE:\s*(\d+)',re.I)
CURRENCY=re.compile(r'^\s*(SETTLEMENT|CLEARING) CURRENCY:\s*([A-Z]{3})',re.I)
REPORT_DATE=re.compile(r'\bREPORT DATE:\s*(\d{2}[A-Z]{3}\d{2})',re.I)
NUMBER=re.compile(r'(?<![\w.])-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?(?:CR|DB)?\b|(?<![\w.])-?\d+(?:\.\d{2})?(?:CR|DB)?\b')
MONEY=re.compile(r'^-?\d[\d,]*(?:\.\d{2})?(?:CR|DB)?$')


def _amount(token):
    sign=None
    if token.endswith(('CR','DB')):
        sign=token[-2:];token=token[:-2]
    try: value=Decimal(token.replace(',',''))
    except InvalidOperation as exc: raise ValueError(f'Importe invalido: {token}') from exc
    return value,sign

class VSSParser(Parser):
    tipo_insumo='VSS'
    def parse(self,source:Path):
        source=Path(source)
        result=IngestionResult(self.tipo_insumo)
        report=None; page=None; settlement=None;clearing=None; report_date=None
        try:
            with source.open('r',encoding='utf-8-sig',errors='strict') as handle:
                for n,raw in enumerate(handle,1):
                    line=raw.replace('\f','').rstrip('\r\n')
                    m=REPORT.search(line)
                    if m:
                        report,page=m.group(1).upper(),int(m.group(2))
                        settlement=None;clearing=None;report_date=None
                        continue
                    if not report:continue
                    m=CURRENCY.search(line)
                    if m:
                        if m.group(1).upper()=='SETTLEMENT': settlement=m.group(2)
                        else:clearing=m.group(2)
                        continue
                    m=REPORT_DATE.search(line)
                    if m:report_date=m.group(1).upper()
                    stripped=line.strip()
                    if not stripped or 'END OF VSS-' in stripped or set(stripped)<=set('- *'):continue
                    # Registros con importes al final: conservamos tokens crudos para
                    # evitar interpretar incorrectamente columnas variables entre VSS 110/115/120.
                    matches=list(NUMBER.finditer(stripped))
                    tail=[]
                    for match in reversed(matches):
                        suffix=stripped[match.end():].strip()
                        if not tail and suffix:continue
                        if tail and suffix and match.end() != tail[-1][0]:
                            # el texto entre numeros solo puede ser espacio
                            if stripped[match.end():tail[-1][0]].strip():break
                        tail.append((match.start(),match.group()))
                    tail.reverse()
                    if not tail:continue
                    label=stripped[:tail[0][0]].strip()
                    if not label or not re.search(r'[A-Za-z]',label):continue
                    if label.upper().startswith(('REPORTING FOR','ROLLUP TO','FUNDS XFER','PAGE:','TOTAL AMOUNT')):continue
                    tokens=[t for _,t in tail]
                    if not all(MONEY.fullmatch(t) for t in tokens):continue
                    valores=[];signos=[]
                    for tok in tokens:
                        dec,sign=_amount(tok);valores.append(dec);signos.append(sign)
                    result.records.append({
                        'numero_linea':n,'REPORTE':report,'PAGINA':page,
                        'MONEDA_LIQUIDACION':settlement,'MONEDA_COMPENSACION':clearing,
                        'FECHA_REPORTE':report_date,'CONCEPTO':label,
                        'VALORES':valores,'SIGNOS':signos,'TEXTO_ORIGINAL':stripped,
                        'ES_CONTROL':label.upper().startswith(('TOTAL','NET ')) or 'NET SETTLEMENT AMOUNT' in label.upper(),
                    })
        except (OSError,UnicodeDecodeError) as exc:
            result.errors.append(RecordError(None,None,'ARCHIVO_INVALIDO',str(exc)))
        if not result.records:
            result.errors.append(RecordError(None,None,'SIN_REGISTROS','Sin lineas monetarias reconocidas en el reporte VSS'))
        result.controls.append({'codigo':'TOTAL_REGISTROS','obtenido':len(result.records)})
        result.controls.append({'codigo':'REPORTES','obtenido':sorted(set(r['REPORTE'] for r in result.records))})
        return result
