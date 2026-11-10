"""Diagnostico F2 Host vs CAET/CANT, sin cruces contables automaticos."""
import argparse
import csv
import json
import os
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

HOST_IDS = (1136, 1141, 1142)
CANJE_IDS = (1253, 1254)


def es_sintetico(concepto):
    return 'PRUEBA SINTETICA' in (concepto or '').upper()


def consolidar_host(rows):
    grupos = defaultdict(lambda: {'cantidad': 0, 'debe': Decimal(0), 'haber': Decimal(0), 'normalizado': Decimal(0), 'sinteticos': 0})
    for r in rows:
        k = (r['id_archivo'], r['tx_host'], r['cuenta'], r['centro'], r['concepto'])
        g = grupos[k]
        g['cantidad'] += 1
        g['sinteticos'] += int(es_sintetico(r['concepto']))
        for field, source in [('debe','valor_debe'), ('haber','valor_haber'), ('normalizado','valor_normalizado')]:
            if r[source] is not None:
                g[field] += Decimal(str(r[source]))
    return [dict(zip(('id_archivo','tx_host','cuenta','centro','concepto'), k), **v,
                 estado='DATOS_SINTETICOS' if v['sinteticos'] else 'SIN_MAPEO') for k,v in sorted(grupos.items(), key=lambda kv: tuple(str(x) for x in kv[0]))]


def consolidar_canje(rows):
    grupos = defaultdict(lambda: {'cantidad': 0, 'valor': Decimal(0), 'intercambio': Decimal(0)})
    for r in rows:
        k = (r['id_archivo'], r['cuenta'])
        g = grupos[k]
        g['cantidad'] += 1
        for target, source in [('valor','vl_total'),('intercambio','vl_interc')]:
            if r[source] is not None:
                g[target] += Decimal(str(r[source]))
    return [dict(id_archivo=k[0], cuenta=k[1], **v, estado='SIN_MAPEO') for k,v in sorted(grupos.items(), key=lambda kv: tuple(str(x) for x in kv[0]))]


def _query(conn, sql, ids):
    from psycopg.rows import dict_row
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (list(ids),))
        return cur.fetchall()


def ejecutar(salida, host_ids=HOST_IDS, canje_ids=CANJE_IDS):
    if os.environ.get('DB_NAME') != 'concilia_test':
        raise ValueError('Solo se autoriza la base de diagnostico concilia_test')
    out = Path(salida)
    if out.exists():
        raise FileExistsError('Salida existente: no sobrescribir')
    if len(set(host_ids)) != 3 or len(set(canje_ids)) != 2 or set(host_ids) & set(canje_ids):
        raise ValueError('IDs de archivos invalidos')
    import psycopg
    with psycopg.connect(host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']),
                         dbname=os.environ['DB_NAME'], user=os.environ['DB_USER'],
                         password=os.environ['DB_PASSWORD'], connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
        # Verificar jornada y tipo de todos los archivos antes de consultar movimientos
        info = _query(conn, '''SELECT a.id_archivo, a.tipo_archivo, a.estado, i.id_jornada, j.fecha_contable
                FROM con_archivo_carga a JOIN con_insumo_esperado i ON i.id_archivo=a.id_archivo
                JOIN con_jornada j ON j.id_jornada=i.id_jornada
                WHERE a.id_archivo = ANY(%s)''', (*host_ids,*canje_ids))
        expected = dict(zip(host_ids, ('HA22','HA26','HA32'))) | dict(zip(canje_ids, ('CAET','CANT')))
        if len(info) != 5 or any(r['tipo_archivo'] != expected.get(r['id_archivo']) or r['estado'] != 'PROCESADO' for r in info):
            raise ValueError('Archivos no corresponden a los tipos o estados esperados')
        if len({(r['id_jornada'], str(r['fecha_contable'])) for r in info}) != 1:
            raise ValueError('Los archivos no pertenecen a la misma jornada y fecha')
        host = _query(conn, '''SELECT id_archivo, tx_host, cuenta, centro, concepto,
                        valor_debe, valor_haber, valor_normalizado
                        FROM con_host_resultado WHERE id_archivo = ANY(%s)''', host_ids)
        canje = _query(conn, '''SELECT id_archivo, cuenta, vl_total, vl_interc
                        FROM con_canje_detalle WHERE id_archivo = ANY(%s)''', canje_ids)
    hg = consolidar_host(host)
    cg = consolidar_canje(canje)
    synthetic = sum(int(es_sintetico(r['concepto'])) for r in host)
    informe = {'estado': 'DIAGNOSTICO_SIN_CONCILIACION_CERTIFICADA',
               'jornada': info[0]['id_jornada'], 'fecha': str(info[0]['fecha_contable']),
               'ids_host': list(host_ids), 'ids_canje': list(canje_ids),
               'filas_host': len(host), 'filas_canje': len(canje),
               'host_sinteticos': synthetic, 'grupos_host': len(hg), 'grupos_canje': len(cg),
               'cruces_aprobados': 0,
               'advertencias': ['No existe matriz de correspondencia contable aprobada.',
                                'HA22, HA26 y HA32 no se suman entre si.',
                                'Datos sinteticos no se concilian.',
                                'No se modificaron tablas ni estados.']}
    out.mkdir(parents=True, exist_ok=False)
    for name, data, fields in [
        ('host_grupos.csv',hg,['id_archivo','tx_host','cuenta','centro','concepto','cantidad','debe','haber','normalizado','sinteticos','estado']),
        ('canje_grupos.csv',cg,['id_archivo','cuenta','cantidad','valor','intercambio','estado'])]:
        with (out/name).open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields, delimiter=';')
            w.writeheader()
            for row in data:
                w.writerow(row)
    (out/'informe.json').write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')
    return informe


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--salida', required=True)
    args=p.parse_args()
    print(json.dumps(ejecutar(args.salida), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
