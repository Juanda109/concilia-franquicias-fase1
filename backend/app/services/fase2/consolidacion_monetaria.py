"""Diagnostico monetario F2 CAET/CANT. Solo lectura, sin certificacion Excel."""
from __future__ import annotations
import argparse
import csv
import json
import os
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIELDS = ('vl_total', 'vl_interc', 'comision_op_exitosas', 'tii_recibida_emisor_visa_op_rever_ventas')
REFERENCE = {'cantidad': 57, 'vl_total': '6180135', 'vl_interc': '6179712', 'comision_op_exitosas': '22350'}

def money(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'Importe invalido: {value!r}') from exc
    if not result.is_finite():
        raise ValueError('Importe no finito')
    return result

def aggregate(rows):
    groups = {}
    totals = {'filas': 0, 'campos': {f: {'suma': Decimal(0), 'nulos': 0, 'ceros': 0, 'informados': 0} for f in FIELDS}}
    for row in rows:
        key = tuple(str(row.get(k) or '') for k in ('id_archivo','tipo_archivo','tx','bin_dest','cuenta'))
        if key not in groups:
            groups[key] = {'id_archivo': key[0], 'tipo_archivo': key[1], 'tx': key[2], 'bin_dest': key[3], 'cuenta': key[4], 'cantidad': 0, **{f: Decimal(0) for f in FIELDS}, **{f+'_nulos': 0 for f in FIELDS}}
        g = groups[key]
        g['cantidad'] += 1
        totals['filas'] += 1
        for f in FIELDS:
            val = money(row.get(f))
            if val is None:
                g[f+'_nulos'] += 1
                totals['campos'][f]['nulos'] += 1
            else:
                g[f] += val
                totals['campos'][f]['suma'] += val
                totals['campos'][f]['informados'] += 1
                if val == 0:
                    totals['campos'][f]['ceros'] += 1
    return [groups[k] for k in sorted(groups)], totals

def read_rows(ids, dbname):
    if dbname != 'concilia_test':
        raise ValueError('Base no autorizada')
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']), dbname=dbname, user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], connect_timeout=5) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('''SELECT a.id_archivo,a.tipo_archivo,i.id_jornada,a.fecha_contable,a.estado,i.estado AS estado_insumo
                           FROM con_archivo_carga a JOIN con_insumo_esperado i ON i.id_archivo=a.id_archivo
                           WHERE a.id_archivo=ANY(%s)''', (ids,))
            metadata = cur.fetchall()
            if len(metadata) != len(ids) or len({m['id_jornada'] for m in metadata}) != 1 or any(m['tipo_archivo'] not in ('CAET','CANT') or m['estado']!='PROCESADO' or m['estado_insumo']!='PROCESADO' for m in metadata):
                raise ValueError('Archivos no validos, no procesados o de jornadas distintas')
            cur.execute('''SELECT a.id_archivo,a.tipo_archivo,d.linea_origen,d.tx,d.bin_dest,d.cuenta,
                                  d.vl_total,d.vl_interc,d.comision_op_exitosas,d.tii_recibida_emisor_visa_op_rever_ventas
                           FROM con_canje_detalle d JOIN con_archivo_carga a ON a.id_archivo=d.id_archivo
                           WHERE d.id_archivo=ANY(%s) ORDER BY a.id_archivo,d.linea_origen''', (ids,))
            return metadata, cur.fetchall()

def run(ids, output, dbname):
    ids = list(dict.fromkeys(ids))
    if not ids or any(i <= 0 for i in ids):
        raise ValueError('IDs invalidos')
    if output.exists():
        raise FileExistsError('La carpeta de salida ya existe')
    metadata, rows = read_rows(ids, dbname)
    groups, totals = aggregate(rows)
    report = {'estado': 'DIAGNOSTICO_MONETARIO_NO_CERTIFICADO', 'ids': ids, 'jornada': metadata[0]['id_jornada'], 'filas': totals['filas'], 'campos': {k: {n: str(v) if isinstance(v, Decimal) else v for n,v in d.items()} for k,d in totals['campos'].items()}, 'referencia_excel_historica': REFERENCE, 'advertencias': ['No se acredita misma poblacion que Excel.', 'Sin conversion de escala monetaria: los importes son los persistidos.', 'Nulos y ceros se contabilizan por separado.', 'Agrupacion por cuenta historica; no implica recalculo de reglas F2.']}
    output.mkdir(parents=True, exist_ok=False)
    with (output/'agrupaciones.csv').open('w', newline='', encoding='utf-8-sig') as fh:
        columns = ['id_archivo','tipo_archivo','tx','bin_dest','cuenta','cantidad',*FIELDS,*(f+'_nulos' for f in FIELDS)]
        writer = csv.DictWriter(fh, fieldnames=columns, delimiter=';')
        writer.writeheader()
        for g in groups:
            writer.writerow({k: str(v) if isinstance(v, Decimal) else v for k,v in g.items()})
    (output/'informe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--ids', nargs='+', type=int, required=True)
    parser.add_argument('--salida', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.ids,args.salida,os.environ.get('DB_NAME')), ensure_ascii=False, indent=2, default=str))
