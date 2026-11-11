"""Incremento 40: agrupacion diagnostica Credibanco, sin homologacion ni escritura.

No se interpreta un concepto 017-... como cuenta contable. El documento
CREDIBANCO_Parametros_Tecnicos.xlsx solo sirve como referencia de cuentas;
no se lee ni se requiere para ejecutar este modulo.
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import re

PUC = re.compile(r"^[0-9]{9,12}$")
CAMPOS = ('vl_total', 'vl_interc', 'comision_op_exitosas', 'tii_recibida_emisor_visa_op_rever_ventas')


def _decimal(value, field):
    if value is None or str(value).strip() == '':
        return None
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'{field}: importe no numerico') from exc
    if not n.is_finite():
        raise ValueError(f'{field}: importe no finito')
    return n


def _cuenta(fila, asignaciones):
    """Solo acepta asignaciones explicitamente suministradas y validadas.

    asignaciones: mapping (id_archivo,linea_origen) -> cuenta contable acreditada.
    El origen de cada asignacion debe validarse fuera de este modulo.
    """
    key = (fila['id_archivo'], fila['linea_origen'])
    cuenta = asignaciones.get(key)
    if cuenta is None:
        return None
    cuenta = str(cuenta).strip()
    if not PUC.fullmatch(cuenta):
        raise ValueError(f'Cuenta contable invalida para {key}')
    return cuenta


def agrupar(filas, asignaciones=None):
    """Agrupa por jornada, archivo, cuenta y concepto literal.

    Preserva nulos y los identificadores de filas; no calcula Total Host ni Diferencia.
    La agrupacion por archivo impide sumar poblaciones distintas accidentalmente.
    """
    asignaciones = asignaciones or {}
    grupos = {}
    pendientes = []
    vistos = set()
    conteos = {'entrada': 0, 'detalle': 0, 'control': 0, 'sin_cuenta': 0}
    for f in filas:
        conteos['entrada'] += 1
        for campo in ('id_jornada','id_archivo','linea_origen','tipo_archivo'):
            if f.get(campo) is None:
                raise ValueError(f'Falta {campo}')
        identidad = (f['id_archivo'], f['linea_origen'])
        if identidad in vistos:
            raise ValueError(f'Fila duplicada {identidad}')
        vistos.add(identidad)
        if f['tipo_archivo'] not in ('CAET','CANT'):
            raise ValueError('Solo CAET/CANT en este adaptador')
        tx = str(f.get('tx') or '').strip()
        if not tx or tx.casefold() == 'totales':
            conteos['control'] += 1
            continue
        conteos['detalle'] += 1
        cuenta = _cuenta(f, asignaciones)
        concepto = str(f.get('cuenta') or '').strip()  # clasificacion funcional, no PUC
        if cuenta is None:
            conteos['sin_cuenta'] += 1
            pendientes.append({'id_archivo': f['id_archivo'], 'linea_origen': f['linea_origen'],
                               'concepto': concepto, 'estado': 'PENDIENTE_ASIGNACION_CONTABLE'})
            continue
        key = (f['id_jornada'], f['id_archivo'], f['tipo_archivo'], cuenta, concepto)
        if key not in grupos:
            grupos[key] = {'id_jornada': f['id_jornada'], 'id_archivo': f['id_archivo'],
                           'franquicia': 'CREDIBANCO', 'insumo': f['tipo_archivo'],
                           'cuenta': cuenta, 'concepto': concepto, 'cantidad': 0,
                           'sumas': {k: Decimal(0) for k in CAMPOS},
                           'nulos': {k: 0 for k in CAMPOS}, 'lineas_origen': [],
                           'estado': 'CALCULADO_NO_HOMOLOGADO', 'certificado': False,
                           'ha22': None, 'ha26': None, 'ha32': None,
                           'total_host': None, 'diferencia': None}
        g = grupos[key]
        g['cantidad'] += 1
        g['lineas_origen'].append(f['linea_origen'])
        for campo in CAMPOS:
            v = _decimal(f.get(campo), campo)
            if v is None:
                g['nulos'][campo] += 1
            else:
                g['sumas'][campo] += v
    return {'conteos': conteos, 'grupos': list(grupos.values()), 'pendientes': pendientes,
            'certificado': False, 'advertencias': [
                'La cuenta contable requiere correspondencia funcional acreditada.',
                'El documento de parametros tecnicos no es un insumo operativo.',
                'No se ejecutan reglas de Simetrik CE01, CE02, CE03 o CA04.',
                'Los importes se agrupan por archivo; no se mezclan jornadas.',
                'No se generan conciliaciones ni diferencias.']}


def leer_canje_pg(id_jornada, conectar=None):
    """Obtiene CAET/CANT PROCESADOS, por jornada y archivo, en solo lectura."""
    if type(id_jornada) is not int or id_jornada <= 0:
        raise ValueError('Jornada invalida')
    if conectar is None:
        from app.repositories.database import connection
        conectar = connection
    from psycopg.rows import dict_row
    with conectar() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('''SELECT d.id_archivo, i.id_jornada, a.tipo_archivo,
                                  d.linea_origen, d.tx, d.cuenta, d.vl_total, d.vl_interc,
                                  d.comision_op_exitosas,
                                  d.tii_recibida_emisor_visa_op_rever_ventas
                           FROM public.con_insumo_esperado i
                           JOIN public.con_archivo_carga a ON a.id_archivo=i.id_archivo
                           JOIN public.con_canje_detalle d ON d.id_archivo=a.id_archivo
                           JOIN public.con_jornada j ON j.id_jornada=i.id_jornada
                           WHERE i.id_jornada=%s AND a.tipo_archivo IN ('CAET','CANT')
                             AND a.estado='PROCESADO'
                             AND a.fecha_contable=j.fecha_contable
                             AND d.fecha_contable=j.fecha_contable
                           ORDER BY d.id_archivo,d.linea_origen''', (id_jornada,))
            return cur.fetchall()
