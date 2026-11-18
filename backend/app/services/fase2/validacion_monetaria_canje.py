"""F2-26: contraste monetario CAET/CANT con formulas observadas en hoja 'parte'.
Diagnostico exclusivamente: no infiere escala ni certifica poblaciones.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

CAMPOS = ('vl_total', 'vl_interc', 'comision_op_exitosas', 'tii_recibida_emisor_visa_op_rever_ventas')

def decimal_o_nulo(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Importe invalido') from exc
    if not value.is_finite():
        raise ValueError('Importe no finito')
    return value

def evaluar(row):
    """Reproduce Q2 y T2 de Excel; I2 depende de TX 22 + EFIPAGO.
    No calcula Q cuando falta BIN; no confunde blanco con cero.
    """
    tx = str(row.get('tx') or '').strip().zfill(2)
    tipo = str(row.get('tipo') or '').strip().upper()
    bin_dest = str(row.get('bin_dest') or '').strip()
    if bin_dest.endswith('.0'):
        bin_dest = bin_dest[:-2]
    total = decimal_o_nulo(row.get('vl_total'))
    intercambio = decimal_o_nulo(row.get('vl_interc'))
    almacenada_comision = decimal_o_nulo(row.get('comision_op_exitosas'))
    almacenada_tii = decimal_o_nulo(row.get('tii_recibida_emisor_visa_op_rever_ventas'))
    comision = Decimal('7450') if tx == '02' and bin_dest and bin_dest != '439467' else None
    tii = (total - intercambio) if tx == '26' and tipo == 'CREDITO' and total is not None and intercambio is not None else None
    # Formula I2 invierte signo del valor bruto de origen para 22 EFIPAGO;
    # sin el campo bruto, no se puede verificar el signo original.
    signo = 'REQUIERE_IMPORTE_BRUTO' if tx == '22' and tipo == 'EFIPAGO' else 'NO_APLICA'
    def cotejo(esperado, observado):
        if esperado is None:
            return 'NO_APLICA' if observado is None else 'SIN_REGLA_PARA_VALOR_ALMACENADO'
        if observado is None:
            return 'NO_EVALUABLE_VALOR_ALMACENADO_NULO'
        return 'COINCIDE_NUMERICO_SIN_ESCALA_CERTIFICADA' if esperado == observado else 'DIFIERE_NUMERICAMENTE_SIN_ESCALA_CERTIFICADA'
    return {
        'id_archivo': row.get('id_archivo'), 'linea_origen': row.get('linea_origen'),
        'tipo_archivo': row.get('tipo_archivo'), 'tx': tx, 'tipo': tipo, 'bin_dest': bin_dest,
        'vl_total': str(total) if total is not None else '',
        'vl_interc': str(intercambio) if intercambio is not None else '',
        'comision_esperada': str(comision) if comision is not None else '',
        'comision_almacenada': str(almacenada_comision) if almacenada_comision is not None else '',
        'estado_comision': cotejo(comision, almacenada_comision),
        'tii_esperada': str(tii) if tii is not None else '',
        'tii_almacenada': str(almacenada_tii) if almacenada_tii is not None else '',
        'estado_tii': cotejo(tii, almacenada_tii), 'control_signo': signo,
    }

def consultar(ids, dbname):
    if dbname != 'concilia_test':
        raise ValueError('Solo se permite concilia_test')
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']),
                         dbname=dbname, user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'],
                         connect_timeout=5) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('''SELECT a.id_archivo, a.tipo_archivo, i.id_jornada, a.estado,
                                  i.estado AS estado_insumo, j.fecha_contable
                           FROM con_archivo_carga a
                           JOIN con_insumo_esperado i ON i.id_archivo = a.id_archivo
                           JOIN con_jornada j ON j.id_jornada = i.id_jornada
                           WHERE a.id_archivo = ANY(%s)''', (ids,))
            metadata = cur.fetchall()
            if (len(metadata) != len(ids) or len({m['id_jornada'] for m in metadata}) != 1
                or {m['tipo_archivo'] for m in metadata} != {'CAET','CANT'}
                or any(m['estado'] != 'PROCESADO' or m['estado_insumo'] != 'PROCESADO' for m in metadata)):
                raise ValueError('Se requieren CAET y CANT procesados de la misma jornada')
            cur.execute('''SELECT a.id_archivo,a.tipo_archivo,d.linea_origen,d.tx,d.tipo,d.bin_dest,
                                  d.vl_total,d.vl_interc,d.comision_op_exitosas,
                                  d.tii_recibida_emisor_visa_op_rever_ventas
                           FROM con_canje_detalle d JOIN con_archivo_carga a ON a.id_archivo=d.id_archivo
                           WHERE d.id_archivo = ANY(%s)
                           ORDER BY a.id_archivo,d.linea_origen''', (ids,))
            return metadata, cur.fetchall()

def ejecutar(ids, salida, dbname):
    ids = list(dict.fromkeys(ids))
    if len(ids) != 2 or any(i <= 0 for i in ids):
        raise ValueError('Se requieren dos IDs distintos')
    salida = Path(salida)
    if salida.exists():
        raise FileExistsError('Salida existente: no sobrescribir')
    metadata, registros = consultar(ids, dbname)
    resultados = [evaluar(r) for r in registros]
    informe = {'estado':'DIAGNOSTICO_MONETARIO_F2_NO_CERTIFICADO',
               'jornada':metadata[0]['id_jornada'], 'fecha':str(metadata[0]['fecha_contable']),
               'ids_archivos':ids, 'filas':len(resultados),
               'estados_comision':dict(Counter(r['estado_comision'] for r in resultados)),
               'estados_tii':dict(Counter(r['estado_tii'] for r in resultados)),
               'control_signo':dict(Counter(r['control_signo'] for r in resultados)),
               'certificado':False,
               'advertencias':['Excel historico y jornada seleccionada no acreditan misma poblacion.',
                               'Escala monetaria sin certificar; 7450 es literal de formula Excel Q2.',
                               'Los nulos no se convierten a cero.',
                               'No se verifica inversion de signo TX22 EFIPAGO sin importe bruto.',
                               'No se modifican datos ni reglas Fase 1.']}
    salida.mkdir(parents=True, exist_ok=False)
    with (salida/'movimientos_monetarios.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(evaluar({}).keys()),delimiter=';')
        writer.writeheader();writer.writerows(resultados)
    (salida/'informe.json').write_text(json.dumps(informe,ensure_ascii=False,indent=2),encoding='utf-8')
    return informe

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--ids',type=int,nargs=2,required=True)
    p.add_argument('--salida',type=Path,required=True)
    a=p.parse_args();print(json.dumps(ejecutar(a.ids,a.salida,os.environ.get('DB_NAME')),ensure_ascii=False,indent=2))
