"""Lectura diagnostica de referencias AK -> C, sin reparar #REF!."""
import re
from pathlib import Path
from openpyxl import load_workbook

PATRON = re.compile(r'^=\s*CONCATENATE\(\s*"17 "\s*[,;]\s*\$?C\$?(\d+)\s*\)$', re.I)


def auditar_ak(ruta):
    libro = load_workbook(Path(ruta), read_only=True, data_only=False, keep_links=False)
    try:
        hoja = libro['PLANTILLA (2)']
        resultado = []
        for fila in range(1, hoja.max_row + 1):
            formula = hoja[f'AK{fila}'].value
            if not isinstance(formula, str) or not formula.startswith('='):
                continue
            registro = {'celda': f'AK{fila}', 'formula_original': formula,
                        'referencia_c': None, 'etiqueta': None}
            coincidencia = PATRON.fullmatch(formula.strip())
            if '#REF!' in formula.upper():
                registro['estado'] = 'REFERENCIA_ROTA_EXCLUIDA'
            elif coincidencia:
                origen = int(coincidencia.group(1))
                contenido = hoja[f'C{origen}'].value
                registro['referencia_c'] = f'C{origen}'
                if isinstance(contenido, str) and contenido.strip():
                    registro['estado'] = 'REFERENCIA_VALIDA'
                    registro['etiqueta'] = '17 ' + contenido
                else:
                    registro['estado'] = 'ORIGEN_C_NO_RESUELTO'
            else:
                registro['estado'] = 'FORMULA_NO_ADMITIDA'
            resultado.append(registro)
        return {'incremento': 'INC021', 'columna': 'AK', 'referencias': resultado,
                'certificado': False, 'conciliado_host': False,
                'homologado_contablemente': False}
    finally:
        libro.close()
