"""Parser independiente de Visa International SS Data (USD)."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from app.parsers.base import Parser
from app.ingestion.result import IngestionResult, RecordError

FECHA = r"\d{2}\s+[A-Za-z]{3}\s+\d{4}"
FILA = re.compile(rf"^\s*(?P<ftsre>\d{{10}})\s+(?P<nombre>.+?)\s+(?P<moneda>[A-Z]{{3}})\s+(?P<importe>[\d,]+\.\d{{2}})\s+(?P<tipo>CR|DB)\s+(?P<valor>{FECHA})\s+(?P<proceso>{FECHA})\s*$",re.I)
CABECERA = re.compile(rf"Processing Date\s+({FECHA})", re.I)
CANDIDATO = re.compile(r"^\s*\d{10}\s+")
NOMBRE_ARCHIVO = re.compile(r"^International\s+SS_Data_(\d{4}-\d{2}-\d{2})(?:\(\d+\))?\.pdf$", re.I)

def fecha_pdf(texto):
    return datetime.strptime(' '.join(texto.split()).title(), '%d %b %Y').date()

class VisaSSInternationalParser(Parser):
    tipo_insumo = 'VISA_SS_INTERNATIONAL'

    def parse(self, source: Path) -> IngestionResult:
        resultado = IngestionResult(self.tipo_insumo)
        try:
            import fitz
            with fitz.open(str(source)) as documento:
                if documento.page_count == 0:
                    raise ValueError('PDF sin paginas')
                for pagina, hoja in enumerate(documento, 1):
                    lineas = hoja.get_text(sort=True).splitlines()
                    cabecera = CABECERA.search('\n'.join(lineas))
                    if cabecera is None:
                        raise ValueError(f'Pagina {pagina}: falta Processing Date')
                    fecha_cabecera = fecha_pdf(cabecera.group(1))
                    for i, linea in enumerate(lineas):
                        if not CANDIDATO.match(linea):
                            continue
                        match = FILA.fullmatch(linea.strip())
                        if match is None:
                            raise ValueError(f'Pagina {pagina}, linea {i+1}: movimiento no interpretable')
                        campos = match.groupdict()
                        if campos['moneda'].upper() != 'USD':
                            raise ValueError('Moneda distinta de USD')
                        importe = Decimal(campos['importe'].replace(',', ''))
                        if importe <= 0:
                            raise ValueError('Importe no positivo')
                        fecha_proceso = fecha_pdf(campos['proceso'])
                        if fecha_proceso != fecha_cabecera:
                            raise ValueError('Fecha de procesamiento diferente a cabecera')
                        nombre = ' '.join(campos['nombre'].split())
                        # La celda de nombre puede continuar en la linea siguiente.
                        if i + 1 < len(lineas) and lineas[i+1].strip().lower() == 'colombia':
                            nombre += ' Colombia'
                        resultado.records.append({
                            'numero_linea': (pagina-1)*100000+i+1,
                            'PAGINA': pagina,
                            'FTSRE': campos['ftsre'],
                            'NOMBRE_ENTIDAD': nombre,
                            'MONEDA': 'USD',
                            'IMPORTE_NETO': importe,
                            'TIPO_MOVIMIENTO': campos['tipo'].upper(),
                            'FECHA_VALOR': fecha_pdf(campos['valor']),
                            'FECHA_PROCESAMIENTO': fecha_proceso,
                        })
        except (OSError, ValueError, InvalidOperation, RuntimeError) as exc:
            resultado.errors.append(RecordError(None,None,'PDF_INVALIDO',str(exc)))
            resultado.records.clear()
        if not resultado.records and not resultado.errors:
            resultado.errors.append(RecordError(None,None,'SIN_REGISTROS','No se encontraron movimientos Visa International SS'))
        resultado.controls.append({'codigo':'TOTAL_REGISTROS','obtenido':len(resultado.records)})
        for tipo in ('CR','DB'):
            resultado.controls.append({'codigo':f'SUMA_{tipo}_USD','obtenido':sum((r['IMPORTE_NETO'] for r in resultado.records if r['TIPO_MOVIMIENTO']==tipo),Decimal('0'))})
        return resultado
