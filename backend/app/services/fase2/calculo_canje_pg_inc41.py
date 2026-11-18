"""Inc41: CAET/CANT PostgreSQL -> agregados reales por concepto, no conciliados.

El campo `cuenta` de con_canje_detalle es una etiqueta funcional 017-...;
no es una cuenta Host. Ninguna asignacion contable se infiere aqui.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from app.services.fase2.consolidacion_totales_canje import consolidar

CAMPOS_PG = ('id_archivo','id_jornada','tipo_archivo','linea_origen','tx','tipo',
             'cuenta','cuentas_comisiones','cuenta_880','vl_total','vl_interc',
             'comision_op_exitosas','tii_recibida_emisor_visa_op_rever_ventas')


def adaptar(fila):
    """Traduce columnas PG a las 22-columnas usadas por consolidar (Inc30)."""
    return {
        'TX': fila.get('tx'), 'TIPO': fila.get('tipo'),
        'cuenta': fila.get('cuenta'), 'cuentas comisiones': fila.get('cuentas_comisiones'),
        'cuenta 880': fila.get('cuenta_880'), 'VL TOTAL': fila.get('vl_total'),
        'VL INTERC': fila.get('vl_interc'),
        'COMISION OP EXITOSAS': fila.get('comision_op_exitosas'),
        'TII RECIBIDA EMISOR VISA OP REVER VENTAS': fila.get('tii_recibida_emisor_visa_op_rever_ventas')
    }


def procesar(filas, id_jornada, archivos=None):
    if type(id_jornada) is not int or id_jornada <= 0:
        raise ValueError('id_jornada invalido')
    archivos = archivos or []
    grupos = {}
    vistos = set()
    conteos = {'entrada': 0, 'detalle': 0, 'control': 0}
    for fila in filas:
        for campo in ('id_jornada','id_archivo','linea_origen','tipo_archivo'):
            if fila.get(campo) is None: raise ValueError(f'Falta {campo}')
        if fila['id_jornada'] != id_jornada: raise ValueError('Jornada cruzada')
        if fila['tipo_archivo'] not in ('CAET','CANT'): raise ValueError('Insumo no permitido')
        identidad = (fila['id_archivo'], fila['linea_origen'])
        if identidad in vistos: raise ValueError(f'Duplicado {identidad}')
        vistos.add(identidad)
        tx = str(fila.get('tx') or '').strip()
        conteos['entrada'] += 1
        if not tx or tx.casefold() == 'totales':
            conteos['control'] += 1
        else:
            conteos['detalle'] += 1
        grupos.setdefault((fila['id_archivo'], fila['tipo_archivo']), []).append(fila)
    resultados = []
    for (archivo, tipo), registros in sorted(grupos.items()):
        r = consolidar(adaptar(f) for f in registros)
        trazas = {}
        for f in registros:
            tx = str(f.get('tx') or '').strip()
            if not tx or tx.casefold() == 'totales': continue
            etiqueta = str(f.get('cuenta') or '').strip()
            trazas.setdefault(etiqueta, []).append(f['linea_origen'])
        for familia, campo in (('principal','cuenta'), ('comisiones','cuentas_comisiones'), ('cuenta_880','cuenta_880')):
            for etiqueta, valores in sorted(r[familia].items()):
                if not etiqueta.strip():
                    # No inventar cuenta ni concepto a partir de clave vacia.
                    estado = 'PENDIENTE_CLASIFICACION'
                else:
                    estado = 'CALCULADO_POR_CONCEPTO_NO_HOMOLOGADO'
                lineas = [f['linea_origen'] for f in registros if
                          str(f.get('tx') or '').strip().casefold() not in ('','totales') and
                          str(f.get(campo) or '') == etiqueta]
                resultados.append({'id_jornada':id_jornada,'id_archivo':archivo,
                    'franquicia':'CREDIBANCO','insumo':tipo,'familia':familia,
                    'concepto_literal':etiqueta,'cuenta_host':None,
                    'importes':valores,'nulos_familia':r['nulos'], 'lineas_origen':lineas,'estado':estado,
                    'certificado':False})
    resumen_archivos = []
    for a in archivos:
        if a['tipo_archivo'] not in ('CAET','CANT'): continue
        n = sum(len(v) for (aid,_),v in grupos.items() if aid == a['id_archivo'])
        if a['estado'] == 'PROCESADO' and n != a['total_registros']:
            raise ValueError(f'Conteo inconsistente archivo {a["id_archivo"]}: {n}/{a["total_registros"]}')
        resumen_archivos.append({'id_archivo':a['id_archivo'],'tipo_archivo':a['tipo_archivo'],
            'estado':a['estado'],'declarados':a['total_registros'],'leidos':n,
            'checksum_sha256':a.get('checksum_sha256')})
    return {'id_jornada':id_jornada,'origen':'POSTGRESQL_SOLO_LECTURA',
        'estado':'CALCULO_DIAGNOSTICO_SIN_CORRESPONDENCIA_HOST',
        'conteos':conteos,'archivos':resumen_archivos,'resultados':resultados,
        'certificado':False,'advertencias':[
            'Los importes son sumas por concepto de los campos persistidos; no son cruces Host.',
            'No se asignan cuentas PUC desde etiquetas 017- ni se calcula diferencia.',
            'CAET y CANT se mantienen separados por archivo para evitar doble conteo.',
            'No se acredita equivalencia completa con pivots Excel ni fecha de poblacion de la plantilla.']}


def leer_pg(id_jornada, conectar=None):
    if type(id_jornada) is not int or id_jornada <= 0: raise ValueError('id_jornada invalido')
    if conectar is None:
        from app.repositories.database import connection
        conectar = connection
    from psycopg.rows import dict_row
    with conectar() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('''SELECT a.id_archivo, a.tipo_archivo, a.estado, a.total_registros,
                                  a.checksum_sha256
                           FROM public.con_insumo_esperado i
                           JOIN public.con_archivo_carga a ON a.id_archivo=i.id_archivo
                           JOIN public.con_jornada j ON j.id_jornada=i.id_jornada
                           WHERE i.id_jornada=%s AND a.tipo_archivo IN ('CAET','CANT')
                             AND a.fecha_contable=j.fecha_contable
                           ORDER BY a.id_archivo''', (id_jornada,))
            archivos = [dict(a) for a in cur.fetchall()]
            cur.execute('''SELECT i.id_jornada,d.id_archivo,a.tipo_archivo,d.linea_origen,
                                  d.tx,d.tipo,d.cuenta,d.cuentas_comisiones,d.cuenta_880,
                                  d.vl_total,d.vl_interc,d.comision_op_exitosas,
                                  d.tii_recibida_emisor_visa_op_rever_ventas
                           FROM public.con_insumo_esperado i
                           JOIN public.con_archivo_carga a ON a.id_archivo=i.id_archivo
                           JOIN public.con_jornada j ON j.id_jornada=i.id_jornada
                           JOIN public.con_canje_detalle d ON d.id_archivo=a.id_archivo
                           WHERE i.id_jornada=%s AND a.tipo_archivo IN ('CAET','CANT')
                             AND a.estado='PROCESADO'
                             AND a.fecha_contable=j.fecha_contable
                             AND d.fecha_contable=j.fecha_contable
                           ORDER BY d.id_archivo,d.linea_origen''', (id_jornada,))
            filas = [dict(f) for f in cur.fetchall()]
    return procesar(filas, id_jornada, archivos)


def _serializar(v):
    if isinstance(v, Decimal): return str(v)
    raise TypeError(type(v).__name__)


def main():
    p=argparse.ArgumentParser(description='Inc41: calculo CAET/CANT por concepto desde PostgreSQL (solo lectura)')
    p.add_argument('--jornada',required=True,type=int)
    p.add_argument('--salida',required=True,type=Path)
    a=p.parse_args()
    if a.salida.exists(): p.error('La salida ya existe; no se sobrescribe')
    informe=leer_pg(a.jornada)
    texto=json.dumps(informe,ensure_ascii=False,indent=2,default=_serializar)
    a.salida.mkdir(parents=True,exist_ok=False)
    (a.salida/'informe.json').write_text(texto,encoding='utf-8')
    (a.salida/'sha256_informe.txt').write_text(hashlib.sha256(texto.encode()).hexdigest()+'\n',encoding='utf-8')
    print(json.dumps({'estado':informe['estado'],'conteos':informe['conteos'],
                      'grupos':len(informe['resultados']),'certificado':False},indent=2))

if __name__=='__main__': main()
