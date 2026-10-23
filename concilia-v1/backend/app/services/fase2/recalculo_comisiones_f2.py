"""Diagnostico F2 CAET/CANT, solo lectura. No altera datos F1."""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

RULE_COM = 'F2-COM-001'
RULE_TII = 'F2-TII-001'


def numeric(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def calculate(row):
    tx = str(row.get('tx') or '').strip().zfill(2)
    bin_dest = str(row.get('bin_dest') or '').strip()
    tipo = str(row.get('tipo') or '').strip().upper()
    total = numeric(row.get('vl_total'))
    interc = numeric(row.get('vl_interc'))
    com_aplica = tx == '02'
    if com_aplica and not bin_dest:
        com_estado, com_valor = 'DATOS_INSUFICIENTES', None
    elif com_aplica and bin_dest != '439467':
        com_estado, com_valor = 'CALCULADO', Decimal('7450')
    else:
        com_estado, com_valor = 'NO_APLICA', None
    tii_aplica = tx == '26' and tipo == 'CREDITO'
    if tii_aplica and (total is None or interc is None):
        tii_estado, tii_valor = 'DATOS_INSUFICIENTES', None
    elif tii_aplica:
        tii_estado, tii_valor = 'CALCULADO', total - interc
    else:
        tii_estado, tii_valor = 'NO_APLICA', None
    return {
        'id_archivo': row.get('id_archivo'), 'linea_origen': row.get('linea_origen'),
        'tx': tx, 'bin_dest': bin_dest, 'tipo': tipo,
        'regla_comision': RULE_COM, 'estado_comision': com_estado,
        'comision_f2': str(com_valor) if com_valor is not None else None,
        'comision_f1': str(row.get('comision_op_exitosas')) if row.get('comision_op_exitosas') is not None else None,
        'regla_tii': RULE_TII, 'estado_tii': tii_estado,
        'tii_f2': str(tii_valor) if tii_valor is not None else None,
        'tii_f1': str(row.get('tii_recibida_emisor_visa_op_rever_ventas')) if row.get('tii_recibida_emisor_visa_op_rever_ventas') is not None else None,
    }


def summarize(rows):
    calculated = [calculate(r) for r in rows]
    com = Counter(r['estado_comision'] for r in calculated)
    tii = Counter(r['estado_tii'] for r in calculated)
    return calculated, {
        'estado': 'RECALCULO_F2_NO_CERTIFICADO', 'filas': len(calculated),
        'estados_comision': dict(com), 'estados_tii': dict(tii),
        'total_comision_f2': str(sum((Decimal(r['comision_f2']) for r in calculated if r['comision_f2'] is not None), Decimal(0))),
        'total_tii_f2': str(sum((Decimal(r['tii_f2']) for r in calculated if r['tii_f2'] is not None), Decimal(0))),
        'referencia_excel_comisiones': '22350',
        'advertencias': ['No se acredita misma poblacion que Excel.', 'Importes sin conversion de escala.', 'NULL no equivale a cero.', 'No se modifica Fase 1.'],
    }


def read_db(ids):
    import os
    import psycopg
    if os.environ.get('DB_NAME') != 'concilia_test':
        raise RuntimeError('Base no autorizada para este diagnostico')
    if len(ids) != 2 or len(set(ids)) != 2 or any(i <= 0 for i in ids):
        raise ValueError('Indique dos IDs distintos y positivos')
    with psycopg.connect(host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']),
                         dbname=os.environ['DB_NAME'], user=os.environ['DB_USER'],
                         password=os.environ['DB_PASSWORD'], connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('''SELECT a.id_archivo,a.tipo_archivo,a.estado,i.estado,i.id_jornada
                           FROM con_archivo_carga a JOIN con_insumo_esperado i ON i.id_archivo=a.id_archivo
                           WHERE a.id_archivo = ANY(%s) ORDER BY a.tipo_archivo''', (ids,))
            meta = cur.fetchall()
            if len(meta) != 2 or {r[1] for r in meta} != {'CAET', 'CANT'} or any(r[2] != 'PROCESADO' or r[3] != 'PROCESADO' for r in meta) or len({r[4] for r in meta}) != 1:
                raise ValueError('Se requieren CAET y CANT procesados de la misma jornada')
            cur.execute('''SELECT id_archivo,linea_origen,tx,bin_dest,tipo,vl_total,vl_interc,
                                  comision_op_exitosas,tii_recibida_emisor_visa_op_rever_ventas
                           FROM con_canje_detalle WHERE id_archivo = ANY(%s)
                           ORDER BY id_archivo,linea_origen''', (ids,))
            names = [c.name for c in cur.description]
            rows = [dict(zip(names, row)) for row in cur.fetchall()]
    return rows, meta[0][4]


def run(ids, output):
    target = Path(output)
    if target.exists():
        raise FileExistsError('Carpeta existente; no sobrescribir')
    rows, jornada = read_db(ids)
    details, report = summarize(rows)
    report['ids_archivos'] = ids
    report['jornada'] = jornada
    target.mkdir(parents=True, exist_ok=False)
    (target / 'informe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with (target / 'movimientos_recalculados.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]) if details else ['id_archivo'], delimiter=';')
        writer.writeheader()
        writer.writerows(details)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ids', nargs=2, type=int, required=True)
    parser.add_argument('--salida', required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.ids, args.salida), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
