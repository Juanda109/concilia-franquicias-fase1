"""Incremento 31: comparacion diagnostica del parser y pivots con cache Excel.
No recalcula Excel, no certifica equivalencia, no escribe en PostgreSQL.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.services.fase2 import parser_parte_canje, consolidacion_totales_canje


def numero(valor):
    if valor is None or str(valor).strip() == '':
        return None
    try:
        d = Decimal(str(valor))
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def extraer_cache(plantilla):
    from openpyxl import load_workbook
    wb = load_workbook(plantilla, read_only=False, data_only=True, keep_links=True)
    try:
        ws = wb['TOTALES']
        principal = {}
        for r in range(5, 11):
            cuenta = ws.cell(r, 1).value
            if cuenta is None or str(cuenta).strip().casefold() == 'total resultado':
                if cuenta is None and all(ws.cell(r,c).value is None for c in (2,3,4)):
                    continue
                if cuenta is not None:
                    continue
            key = '' if cuenta is None or str(cuenta) == '(vacío)' else str(cuenta)
            principal[key] = {'cantidad_tipo': numero(ws.cell(r,2).value), 'vl_interc': numero(ws.cell(r,3).value), 'vl_total': numero(ws.cell(r,4).value)}
        comisiones = {}
        for r in range(5, 8):
            cuenta = ws.cell(r,7).value
            if cuenta is None or str(cuenta).strip().casefold() == 'total resultado':
                continue
            key = '' if str(cuenta) == '(vacío)' else str(cuenta)
            comisiones[key] = {'comision': numero(ws.cell(r,8).value), 'tii': numero(ws.cell(r,9).value)}
        regalo = {}
        for r in range(20,22):
            cuenta = ws.cell(r,1).value
            if cuenta is not None and str(cuenta).strip().casefold() == 'total resultado':
                continue
            key = '' if cuenta is None or str(cuenta) == '(vacío)' else str(cuenta)
            regalo[key] = {'vl_interc': numero(ws.cell(r,2).value), 'vl_total': numero(ws.cell(r,3).value)}
        pivots = [{'nombre': p.name, 'destino': p.location.ref,
                   'origen': (p.cache.cacheSource.worksheetSource.ref if p.cache and p.cache.cacheSource and p.cache.cacheSource.worksheetSource else None)}
                  for p in ws._pivots]
        return {'principal': principal, 'comisiones': comisiones, 'cuenta_880': regalo,
                'L3_cache': numero(ws['L3'].value), 'L5_cache': numero(ws['L5'].value),
                'L6_cache': numero(ws['L6'].value), 'L8_cache': numero(ws['L8'].value),
                'pivots': pivots}
    finally:
        wb.close()


def comparar_grupos(actual, referencia, campos):
    diferencias = []
    for cuenta in sorted(set(actual) | set(referencia)):
        a, b = actual.get(cuenta), referencia.get(cuenta)
        if a is None or b is None:
            diferencias.append({'cuenta': cuenta, 'estado': 'SOLO_PYTHON' if b is None else 'SOLO_CACHE_EXCEL'})
            continue
        for campo in campos:
            av, bv = numero(a.get(campo)), numero(b.get(campo))
            if bv is None:
                diferencias.append({'cuenta': cuenta, 'campo': campo, 'estado': 'CACHE_SIN_VALOR', 'python': str(av) if av is not None else None})
            elif av != bv:
                diferencias.append({'cuenta': cuenta, 'campo': campo, 'estado': 'DIFERENCIA',
                                    'python': str(av) if av is not None else None, 'excel_cache': str(bv)})
    return diferencias


def comparar(consolidado, cache):
    especificaciones = {'principal': ('cantidad_tipo', 'vl_interc', 'vl_total'),
                        'comisiones': ('comision', 'tii'), 'cuenta_880': ('vl_interc', 'vl_total')}
    return {grupo: comparar_grupos(consolidado[grupo], cache[grupo], campos)
            for grupo, campos in especificaciones.items()}


def ejecutar(plantilla: Path, salida: Path):
    plantilla, salida = Path(plantilla), Path(salida)
    if not plantilla.is_file():
        raise FileNotFoundError(plantilla)
    if salida.exists():
        raise FileExistsError(f'No sobrescribir: {salida}')
    # Parseo y consolidacion sobre la MISMA extraccion, sin BD.
    salida.mkdir(parents=True, exist_ok=False)
    try:
        parte_dir = salida / 'parser'
        parte = parser_parte_canje.ejecutar(plantilla, parte_dir)
        totales_dir = salida / 'consolidacion'
        totales = consolidacion_totales_canje.ejecutar(parte_dir / 'parte_python.csv', totales_dir)
        cache = extraer_cache(plantilla)
        diferencias = comparar(totales, cache)
        cantidad = sum(len(v) for v in diferencias.values())
        informe = {
            'estado': 'DIAGNOSTICO_EQUIVALENCIA_NO_CERTIFICADA', 'certificado': False,
            'sha256_plantilla': hashlib.sha256(plantilla.read_bytes()).hexdigest(),
            'registros_plano': parte['registros_plano'], 'conteos_consolidacion': totales['conteos'],
            'pivots': cache['pivots'], 'diferencias_por_grupo': {k: len(v) for k,v in diferencias.items()},
            'diferencias_total': cantidad,
            'L3_python': str(totales['L3_comisiones_exitosas']),
            'L3_cache_excel': str(cache['L3_cache']) if cache['L3_cache'] is not None else None,
            'L5_carta_externa': 'PENDIENTE', 'L6_valor_electronico_red': 'PENDIENTE',
            'L8_cuota_red': 'NO_CALCULADA',
            'advertencias': [
                'Se comparan valores almacenados en cache, NO Excel recalculado.',
                'Un resultado sin diferencias NO acredita frescura de las caches ni equivalencia funcional.',
                'Los rangos de origen pivot difieren y pueden incluir filas historicas.',
                'No se acredita la fecha ni poblacion de la jornada 1377.',
                'La formula L5 depende de CARTA; no se certifican L5, L6 ni L8.',
                'Escala monetaria y correspondencias Host sin homologacion.'
            ]}
        (salida / 'informe.json').write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')
        (salida / 'diferencias.json').write_text(json.dumps(diferencias, ensure_ascii=False, indent=2), encoding='utf-8')
        with (salida / 'diferencias.csv').open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f, delimiter=';')
            w.writerow(['grupo','cuenta','campo','estado','python','excel_cache'])
            for grupo, lista in diferencias.items():
                for d in lista:
                    w.writerow([grupo, d.get('cuenta',''),d.get('campo',''),d['estado'],d.get('python',''),d.get('excel_cache','')])
        return informe
    except Exception:
        # Conservar carpeta para diagnostico; no crear informe de exito.
        raise


def main():
    p = argparse.ArgumentParser(description='Validacion diagnostica CAET/CANT plano-parte-TOTALES')
    p.add_argument('--plantilla', type=Path, required=True)
    p.add_argument('--salida', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(ejecutar(args.plantilla, args.salida), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
