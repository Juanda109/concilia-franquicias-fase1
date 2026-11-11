"""Diagnostico F2 de procedencia Host, estrictamente de solo lectura."""
import argparse
import csv
import json
import os
from collections import Counter
from pathlib import Path

from app.services.fase2.control_procedencia_host import evaluar_procedencia

IDS = {'HA22': 1136, 'HA26': 1141, 'HA32': 1142}
FECHA = '2026-10-21'
JORNADA = 1377
CAMPOS = ('id_archivo','id_host_resultado','tx_host','cuenta','centro','fecha_contable','empresa','valor_debe','valor_haber','concepto','estado','motivo','certificable_por_procedencia')


def diagnosticar(filas):
    if len({r['id_host_resultado'] for r in filas}) != len(filas):
        raise ValueError('Identificadores Host duplicados')
    for r in filas:
        if r['id_archivo'] not in IDS.values() or IDS.get(r['tx_host']) != r['id_archivo']:
            raise ValueError('Archivo o fuente Host inesperados')
        if str(r['fecha_contable']) != FECHA:
            raise ValueError('Fecha contable inesperada')
    # Se exige empresa desde metadatos tipados verificables; no se infiere
    # de la cuenta. Si falta, no se puede establecer correlacion fuerte.
    evaluados = evaluar_procedencia(filas)
    detalles = []
    for r, e in zip(filas, evaluados['registros']):
        detalles.append({**{k: r.get(k) for k in CAMPOS},
                         'estado': e['estado'], 'motivo': e['motivo'],
                         'certificable_por_procedencia': e['certificable_por_procedencia']})
    return {'estado': 'DIAGNOSTICO_SIN_CONCILIACION_CERTIFICADA',
            'jornada': JORNADA, 'fecha': FECHA, 'filas': len(filas),
            'conteos': dict(Counter(d['estado'] for d in detalles)),
            'cruces_certificados': 0,
            'advertencias': ['No se acredita origen externo de archivos Host',
                             'Correlacion HA32 no prueba procedencia',
                             'No se activan reglas contables'],
            'detalles': detalles}


def ejecutar(salida):
    if os.environ.get('DB_NAME') != 'concilia_test':
        raise RuntimeError('Solo se permite concilia_test')
    destino = Path(salida)
    if destino.exists():
        raise FileExistsError('La carpeta de salida ya existe')
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']),
                         dbname='concilia_test', user=os.environ['DB_USER'],
                         password=os.environ['DB_PASSWORD'], connect_timeout=5) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('''SELECT id_archivo, id_host_resultado, tx_host, cuenta, centro,
                           fecha_contable, concepto, valor_debe, valor_haber
                           FROM public.con_host_resultado
                           WHERE id_archivo = ANY(%s)
                           ORDER BY id_archivo, id_host_resultado''', (list(IDS.values()),))
            filas = cur.fetchall()
            cur.execute('''SELECT a.id_archivo, a.tipo_archivo, a.estado,
                           i.id_jornada, i.estado AS estado_insumo
                           FROM public.con_archivo_carga a
                           JOIN public.con_insumo_esperado i ON i.id_archivo=a.id_archivo
                           WHERE a.id_archivo = ANY(%s)''', (list(IDS.values()),))
            metadata = cur.fetchall()
    if len(metadata) != 3 or {r['id_archivo'] for r in metadata} != set(IDS.values()):
        raise RuntimeError('Metadatos Host incompletos')
    if any(r['tipo_archivo'] != next(k for k,v in IDS.items() if v == r['id_archivo'])
           or r['id_jornada'] != JORNADA or r['estado'] != 'PROCESADO'
           or r['estado_insumo'] != 'PROCESADO' for r in metadata):
        raise RuntimeError('Jornada, tipo o estado Host inesperados')
    resultado = diagnosticar(filas)
    destino.mkdir(parents=True, exist_ok=False)
    with (destino / 'movimientos_host.csv').open('w', newline='', encoding='utf-8-sig') as fh:
        writer = csv.DictWriter(fh, fieldnames=CAMPOS, delimiter=';', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(resultado['detalles'])
    resumen = {k:v for k,v in resultado.items() if k != 'detalles'}
    (destino / 'informe.json').write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding='utf-8')
    return resumen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--salida', required=True)
    args = parser.parse_args()
    print(json.dumps(ejecutar(args.salida), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
