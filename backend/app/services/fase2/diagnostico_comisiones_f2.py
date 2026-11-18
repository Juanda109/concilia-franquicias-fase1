"""Diagnostico F2 CAET/CANT: comisiones, TII y cuenta 880. Solo lectura."""
import argparse
import csv
import json
import os
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

C_DEBITO = '017-COMISIONES EXIT. TARJETA DEBITO ONLINE'
C_CREDITO = '017-CJE REC VISA NAL VR COM EXIT TC BATC'
C_TII = '017-TII RECIBIDA EMISOR VISA OP REVER VENTAS'
C_REGALO = '017-CANJE RECIBIDO TARJETA DEBITO REGALO'


def dec(v):
    if v is None or str(v).strip() == '':
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def evaluar(row):
    def val(k):
        return str(row.get(k) or '').strip().upper()
    tx, tipo, canal, bin_dest = (val(k) for k in ('tx', 'tipo', 'espacios', 'bin_dest'))
    # Contrato tomado de las formulas conocidas de PARTE. No altera la fuente.
    comision = Decimal('7450') if tx == '02' and bin_dest != '439467' else None
    total, interc = dec(row.get('vl_total')), dec(row.get('vl_interc'))
    tii = total - interc if tipo == 'CREDITO' and tx == '26' and total is not None and interc is not None else None
    cuenta_comision = ''
    if tipo == 'DEBITO' and canal != 'CNB' and tx == '02' and comision == 7450:
        cuenta_comision = C_DEBITO
    elif tipo == 'CREDITO' and canal == 'ELECTRONICO' and tx == '02' and comision == 7450:
        cuenta_comision = C_CREDITO
    elif tipo == 'CREDITO' and tx == '26' and tii not in (None, Decimal('0')):
        cuenta_comision = C_TII
    cuenta_880 = C_REGALO if bin_dest in ('462550','417704') and tipo == 'DEBITO' and canal != 'CNB' and tx in ('02','06') else ''
    checks = {}
    for nombre, actual, esperado in (
        ('comision', dec(row.get('comision_op_exitosas')), comision),
        ('tii', dec(row.get('tii_recibida_emisor_visa_op_rever_ventas')), tii),
        ('cuenta_comision', val('cuentas_comisiones'), cuenta_comision),
        ('cuenta_880', val('cuenta_880'), cuenta_880),
    ):
        checks[nombre] = 'COINCIDE' if actual == esperado else 'DIFIERE'
    return {'id_archivo': row.get('id_archivo'), 'linea_origen': row.get('linea_origen'), 'tx': tx,
            'tipo': tipo, 'canal': canal, 'bin_dest': bin_dest,
            'comision_bd': str(row.get('comision_op_exitosas')) if row.get('comision_op_exitosas') is not None else '',
            'comision_f2': str(comision) if comision is not None else '',
            'tii_bd': str(row.get('tii_recibida_emisor_visa_op_rever_ventas')) if row.get('tii_recibida_emisor_visa_op_rever_ventas') is not None else '',
            'tii_f2': str(tii) if tii is not None else '',
            'cuenta_comision_bd': val('cuentas_comisiones'), 'cuenta_comision_f2': cuenta_comision,
            'cuenta_880_bd': val('cuenta_880'), 'cuenta_880_f2': cuenta_880,
            **{'estado_'+k: v for k,v in checks.items()}}


def cargar(ids):
    import psycopg
    from psycopg.rows import dict_row
    if os.getenv('DB_NAME') != 'concilia_test':
        raise RuntimeError('Base no autorizada: se exige concilia_test')
    cfg = dict(host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']),
               dbname='concilia_test', user=os.environ['DB_USER'],
               password=os.environ['DB_PASSWORD'], connect_timeout=5, row_factory=dict_row)
    with psycopg.connect(**cfg) as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('''SELECT a.id_archivo, a.tipo_archivo, a.estado, i.estado AS estado_insumo,
                                  i.id_jornada, j.fecha_contable
                           FROM con_archivo_carga a JOIN con_insumo_esperado i ON i.id_archivo=a.id_archivo
                           JOIN con_jornada j ON j.id_jornada=i.id_jornada
                           WHERE a.id_archivo = ANY(%s)''', (ids,))
            archivos = cur.fetchall()
            if len(archivos) != len(set(ids)) or {x['tipo_archivo'] for x in archivos} != {'CAET','CANT'}:
                raise ValueError('Se requiere un CAET y un CANT existentes')
            if len({(x['id_jornada'],x['fecha_contable']) for x in archivos}) != 1:
                raise ValueError('Archivos de jornadas distintas')
            if any(x['estado'] != 'PROCESADO' or x['estado_insumo'] != 'PROCESADO' for x in archivos):
                raise ValueError('Archivos no procesados')
            cur.execute('''SELECT id_archivo, linea_origen, tx, tipo, espacios, bin_dest,
                                  vl_total, vl_interc, comision_op_exitosas,
                                  tii_recibida_emisor_visa_op_rever_ventas,
                                  cuentas_comisiones, cuenta_880
                           FROM con_canje_detalle WHERE id_archivo = ANY(%s)
                           ORDER BY id_archivo, linea_origen''', (ids,))
            rows = cur.fetchall()
    return archivos, rows


def run(ids, salida):
    if len(ids) != 2 or len(set(ids)) != 2:
        raise ValueError('Indique exactamente dos IDs distintos')
    out = Path(salida)
    if out.exists():
        raise FileExistsError('Salida existente; no sobrescribir')
    archivos, rows = cargar(ids)
    resultados = [evaluar(r) for r in rows]
    conteos = {k: dict(Counter(r[k] for r in resultados)) for k in ('estado_comision','estado_tii','estado_cuenta_comision','estado_cuenta_880')}
    resumen = {'estado':'DIAGNOSTICO_F2_COMISIONES_NO_CERTIFICADO', 'ids_archivos':ids,
               'jornada':archivos[0]['id_jornada'], 'fecha':str(archivos[0]['fecha_contable']),
               'filas':len(rows), 'conteos':conteos,
               'advertencias':['La coincidencia con valores F1 no certifica equivalencia Excel.',
                               'Se conserva escala numerica almacenada; falta cotejo de unidades.',
                               'Se evalua cuenta de comision y cuenta 880 por separado de cuenta principal.']}
    out.mkdir(parents=True, exist_ok=False)
    with (out/'movimientos_comisiones.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(resultados[0]) if resultados else ['id_archivo','linea_origen'], delimiter=';')
        writer.writeheader(); writer.writerows(resultados)
    (out/'informe.json').write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding='utf-8')
    return resumen


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ids', nargs=2, type=int, required=True)
    p.add_argument('--salida', required=True)
    a = p.parse_args()
    print(json.dumps(run(a.ids, a.salida), indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
