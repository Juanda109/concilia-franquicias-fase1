"""INC56-F: auditoria literal de formulas DEPO, sin homologacion monetaria.

Lee exclusivamente hojas XML pequenas del XLSX original, evitando cargar la hoja
masiva 'Revision campos'. No transforma importes DEPO ni produce diferencias.
"""
from __future__ import annotations
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import hashlib
import re

NS = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
HOJAS = {'datos contabilidad': 'xl/worksheets/sheet3.xml',
         'td cuadre': 'xl/worksheets/sheet4.xml',
         'criterios': 'xl/worksheets/sheet5.xml',
         'bines amex': 'xl/worksheets/sheet7.xml'}
CUENTAS = ('196095001838', '196095001839')

def auditar_plantilla(ruta):
    ruta = Path(ruta)
    formulas, criterios, bines = [], {}, []
    with ZipFile(ruta) as z:
        for hoja, xml in HOJAS.items():
            root = ET.fromstring(z.read(xml))
            for celda in root.findall('.//x:sheetData/x:row/x:c', NS):
                ref = celda.attrib['r']
                f, v = celda.find('x:f', NS), celda.find('x:v', NS)
                if f is not None:
                    formula = f.text or ''
                    formulas.append({'hoja': hoja, 'celda': ref, 'formula': '='+formula,
                                     'valor_cache': None if v is None else v.text,
                                     'tipo': 'SUMIFS_HOST' if hoja == 'datos contabilidad' else 'FORMULA_PIVOT_O_CRUCE',
                                     'estado': 'REFERENCIA_IDENTIFICADA_NO_CERTIFICADA'})
                elif hoja == 'criterios' and v is not None:
                    criterios[ref] = v.text
                elif hoja == 'bines amex' and ref.startswith('A') and v is not None:
                    bines.append(v.text)
    d = {(f['hoja'], f['celda']): f['formula'] for f in formulas}
    esperado = {'D2':('196095001838','D'),'D3':('196095001838','H'),
                'D4':('196095001839','D'),'D5':('196095001839','H')}
    for celda,(cuenta,nat) in esperado.items():
        literal = d.get(('datos contabilidad', celda), '')
        if not re.search(r'SUMIFS\(H:H,F:F,"'+cuenta+r'",G:G,"'+nat+r'"\)', literal, re.I):
            raise ValueError('Formula contable inesperada: '+celda)
    conceptos = sorted(set(re.findall(r'017-[^"\n]+', '\n'.join(f['formula'] for f in formulas if f['hoja']=='td cuadre'))))
    return {'plantilla': ruta.name, 'sha256': hashlib.sha256(ruta.read_bytes()).hexdigest(),
            'formulas': formulas, 'criterios_literales': criterios,
            'bines_amex_literales': bines, 'conceptos_literales_en_formulas': conceptos,
            'certificado_monetario': False,
            'pendientes': ['Escala monetaria DEPO', 'Origen y filtros de tablas dinamicas',
                           'Clasificacion CNB/AMEX por registro', 'Comparacion de importes Excel/Python',
                           'Seleccion no duplicada de fuente Host', 'Referencias auxiliares F4/F5']}

def inspeccionar_depo(ruta):
    ruta = Path(ruta)
    lineas = ruta.read_text(encoding='utf-8',errors='replace').splitlines()
    tipos = {}
    for n, linea in enumerate(lineas, 1):
        if len(linea) != 280:
            raise ValueError(f'Longitud inesperada linea {n}: {len(linea)}')
        tipo=linea[:2]
        tipos[tipo]=tipos.get(tipo,0)+1
    return {'archivo':ruta.name, 'sha256':hashlib.sha256(ruta.read_bytes()).hexdigest(),
            'registros':len(lineas), 'tipos':tipos,
            'certificado_monetario':False}
