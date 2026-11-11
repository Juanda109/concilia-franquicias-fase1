"""Incremento 28: control conservador de equivalencia de poblaciones CAET/CANT.
No recalcula Excel ni declara certificacion. No accede a PostgreSQL.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

CAMPOS = ('vl_total', 'vl_interc', 'comision_op_exitosas', 'tii_recibida_emisor_visa_op_rever_ventas')
CLAVES = ('tipo_archivo', 'tx', 'tipo', 'cuenta')


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b''):
            h.update(bloque)
    return h.hexdigest()


def leer_csv(path):
    with Path(path).open('r', encoding='utf-8-sig', newline='') as f:
        lector = csv.DictReader(f)
        if not lector.fieldnames:
            raise ValueError('CSV sin encabezados')
        if len(set(lector.fieldnames)) != len(lector.fieldnames):
            raise ValueError('Encabezados duplicados')
        return list(lector), set(lector.fieldnames)


def decimal_valor(valor):
    if valor is None or str(valor).strip() == '':
        return None
    try:
        d = Decimal(str(valor).strip())
    except InvalidOperation as exc:
        raise ValueError('Importe invalido') from exc
    if not d.is_finite():
        raise ValueError('Importe no finito')
    return d


def agrupar(filas):
    grupos = {}
    for fila in filas:
        clave = tuple(str(fila[k]).strip() for k in CLAVES)
        g = grupos.setdefault(clave, {'cantidad': 0, 'sumas': {k: Decimal('0') for k in CAMPOS}, 'nulos': Counter()})
        g['cantidad'] += 1
        for campo in CAMPOS:
            valor = decimal_valor(fila[campo])
            if valor is None:
                g['nulos'][campo] += 1
            else:
                g['sumas'][campo] += valor
    return grupos


def inspeccionar_plantilla(path):
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=False)
    try:
        nombres = wb.sheetnames
        return {'hojas': nombres, 'hojas_requeridas': {h: h.lower() in {n.lower() for n in nombres} for h in ('plano','parte','BINES')}, 'sha256': sha256(path)}
    finally:
        wb.close()


def ejecutar(canje_csv, excel_csv, plantilla, salida, manifiesto=None):
    salida = Path(salida)
    if salida.exists():
        raise FileExistsError('Carpeta de salida existente; no sobrescribir')
    rutas = [Path(canje_csv), Path(excel_csv), Path(plantilla)]
    for ruta in rutas:
        if not ruta.is_file():
            raise FileNotFoundError(str(ruta))
    origen, campos_o = leer_csv(canje_csv)
    referencia, campos_r = leer_csv(excel_csv)
    requeridos = set(CLAVES + CAMPOS + ('fecha_contable',))
    ausentes = {'canje': sorted(requeridos - campos_o), 'excel': sorted(requeridos - campos_r)}
    plantilla_info = inspeccionar_plantilla(plantilla)
    condiciones = []
    if any(ausentes.values()):
        condiciones.append('COLUMNAS_INSUFICIENTES')
    if not all(plantilla_info['hojas_requeridas'].values()):
        condiciones.append('HOJAS_PLANTILLA_INCOMPLETAS')
    metadata = None
    if manifiesto is None:
        condiciones.append('MANIFIESTO_POBLACION_AUSENTE')
    else:
        metadata = json.loads(Path(manifiesto).read_text(encoding='utf-8-sig'))
        for nombre in ('fecha_contable', 'filtros', 'escala_monetaria', 'poblacion_equivalente_aprobada', 'responsable_aprobacion'):
            if nombre not in metadata:
                condiciones.append('MANIFIESTO_INCOMPLETO_' + nombre.upper())
        if metadata.get('poblacion_equivalente_aprobada') is not True:
            condiciones.append('POBLACION_NO_APROBADA')
        if metadata.get('sha256_canje') != sha256(canje_csv) or metadata.get('sha256_excel') != sha256(excel_csv):
            condiciones.append('HUELLAS_MANIFIESTO_NO_COINCIDEN')
        if metadata.get('sha256_plantilla') != plantilla_info['sha256']:
            condiciones.append('HUELLA_PLANTILLA_NO_COINCIDE')
    fechas = {'canje': sorted({str(r.get('fecha_contable','')).strip() for r in origen}), 'excel': sorted({str(r.get('fecha_contable','')).strip() for r in referencia})}
    if fechas['canje'] != fechas['excel'] or len(fechas['canje']) != 1:
        condiciones.append('FECHAS_NO_EQUIVALENTES')
    if metadata and (fechas['canje'] != [str(metadata.get('fecha_contable'))]):
        condiciones.append('FECHA_MANIFIESTO_NO_COINCIDE')
    diferencias = []
    if not any(ausentes.values()):
        go, gr = agrupar(origen), agrupar(referencia)
        for clave in sorted(set(go) | set(gr)):
            a, b = go.get(clave), gr.get(clave)
            diferencias.append({'clave': dict(zip(CLAVES, clave)), 'cantidad_canje': a['cantidad'] if a else 0, 'cantidad_excel': b['cantidad'] if b else 0,
                'importes': {k: {'canje': str(a['sumas'][k]) if a else None, 'excel': str(b['sumas'][k]) if b else None, 'nulos_canje': a['nulos'][k] if a else None, 'nulos_excel': b['nulos'][k] if b else None} for k in CAMPOS}})
    informe = {'estado': 'COMPARACION_DIAGNOSTICA_NO_CERTIFICADA', 'certificado': False,
        'filas_canje': len(origen), 'filas_excel': len(referencia), 'fechas': fechas,
        'plantilla': plantilla_info, 'columnas_ausentes': ausentes, 'bloqueos': sorted(set(condiciones)),
        'grupos_diagnosticos': diferencias,
        'advertencias': ['CSV Excel debe ser una extraccion trazable y homologada de hoja parte, no una interpretacion automatica de formulas.',
                        'La igualdad numerica no demuestra equivalencia de poblacion, filtros, escala o aprobacion contable.',
                        'No se modifican datos de Fase 1, matrices ni PostgreSQL.']}
    salida.mkdir(parents=True, exist_ok=False)
    (salida / 'informe.json').write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')
    return informe


def main():
    p = argparse.ArgumentParser(description='Comparacion diagnostica CAET/CANT contra extraccion Excel homologada')
    p.add_argument('--canje-csv', required=True)
    p.add_argument('--excel-csv', required=True)
    p.add_argument('--plantilla', required=True)
    p.add_argument('--manifiesto')
    p.add_argument('--salida', required=True)
    a = p.parse_args()
    print(json.dumps(ejecutar(a.canje_csv, a.excel_csv, a.plantilla, a.salida, a.manifiesto), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
