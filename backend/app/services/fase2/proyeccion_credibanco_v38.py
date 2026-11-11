"""Proyeccion monetaria de CAET/CANT por concepto, no homologada ni certificada.

Nunca equipara un concepto con una cuenta sin regla monetaria aprobada.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

CAMPOS = ('vl_total', 'vl_descue', 'vl_interc', 'comision_op_exitosas')

def decimal_seguro(valor):
    if valor is None:
        return None
    try:
        n = Decimal(str(valor))
    except (ValueError, InvalidOperation, TypeError):
        return None
    return n if n.is_finite() else None

def proyectar(filas):
    agrupados = defaultdict(list)
    for fila in filas:
        clave = (str(fila['tipo_archivo']), str(fila.get('cuenta') or '').strip())
        agrupados[clave].append(fila)
    salida = []
    for (tipo, concepto), registros in sorted(agrupados.items()):
        totales = {}
        for campo in CAMPOS:
            valores = [decimal_seguro(r.get(campo)) for r in registros]
            totales[campo] = str(sum(valores, Decimal(0))) if all(v is not None for v in valores) else None
        salida.append({
            'insumo': tipo, 'concepto': concepto, 'registros': len(registros),
            'id_archivos': sorted({r['id_archivo'] for r in registros}),
            'lineas_origen': [r['linea_origen'] for r in registros],
            'totales_candidatos': totales,
            'valor_franquicia': None, 'cuenta_contable': None, 'diferencia': None,
            'estado': 'PENDIENTE_FORMULA_CONCEPTO_CUENTA', 'certificado': False,
        })
    return salida

def consultar(cur, jornada):
    cur.execute('''SELECT a.tipo_archivo,d.id_archivo,d.linea_origen,d.cuenta,
                          d.vl_total,d.vl_descue,d.vl_interc,d.comision_op_exitosas
                   FROM public.con_canje_detalle d
                   JOIN public.con_insumo_esperado i ON i.id_archivo=d.id_archivo
                   JOIN public.con_archivo_carga a ON a.id_archivo=d.id_archivo
                   WHERE i.id_jornada=%s AND a.tipo_archivo IN ('CAET','CANT')
                   ORDER BY a.tipo_archivo,d.id_archivo,d.linea_origen''',(jornada,))
    nombres=[c.name for c in cur.description]
    return proyectar([dict(zip(nombres, fila)) for fila in cur.fetchall()])
