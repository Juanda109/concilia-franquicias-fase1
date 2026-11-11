"""Conexion de formulas V43 con movimientos CAET/CANT persistidos.
Solo lectura; no certifica diferencias ni presupone homologacion.
"""
from collections import defaultdict
from decimal import Decimal
from app.services.fase2.formulas_v43 import evaluar

def construir_entradas(detalles):
    """A/B/C/D: TOTALES, B cantidad, C intercambio, D total.
    E/F: comisiones agrupadas por concepto, F suma comision_op_exitosas.
    No mezclar las familias; faltantes permanecen nulos.
    """
    grupos=defaultdict(lambda:{'cantidad':0,'interc':Decimal(0),'n_interc':0,'total':Decimal(0),'n_total':0,'archivos':set()})
    comisiones=defaultdict(lambda:{'valor':Decimal(0),'n':0,'archivos':set()})
    vistos=set()
    for d in detalles:
        identidad=(d['id_archivo'],d['linea_origen'])
        if identidad in vistos: raise ValueError('Linea duplicada')
        vistos.add(identidad)
        nombre=(d.get('cuenta') or '').strip()
        if nombre:
            g=grupos[nombre]
            if d.get('tipo') is not None and str(d['tipo']).strip():g['cantidad']+=1
            for campo,total,n in (('vl_interc','interc','n_interc'),('vl_total','total','n_total')):
                v=d.get(campo)
                if v is not None:
                    val=Decimal(str(v))
                    if not val.is_finite():raise ValueError('Importe no finito')
                    g[total]+=val;g[n]+=1
            g['archivos'].add(d['id_archivo'])
        com=(d.get('cuentas_comisiones') or '').strip()
        if com and d.get('comision_op_exitosas') is not None:
            val=Decimal(str(d['comision_op_exitosas']))
            if not val.is_finite():raise ValueError('Comision no finita')
            c=comisiones[com];c['valor']+=val;c['n']+=1;c['archivos'].add(d['id_archivo'])
    filas=[{'A':k,'B':str(v['cantidad']),'C':str(v['interc']) if v['n_interc'] else None,
            'D':str(v['total']) if v['n_total'] else None,'archivos':sorted(v['archivos'])}
           for k,v in sorted(grupos.items())]
    filas += [{'E':k,'F':str(v['valor']),'archivos':sorted(v['archivos'])}
              for k,v in sorted(comisiones.items()) if v['n']]
    return filas

def ejecutar(cur,id_jornada):
    cur.execute("""
      SELECT d.id_archivo,d.linea_origen,d.tipo,d.cuenta,d.cuentas_comisiones,
             d.vl_interc,d.vl_total,d.comision_op_exitosas
      FROM public.con_canje_detalle d
      JOIN public.con_insumo_esperado i ON i.id_archivo=d.id_archivo
      JOIN public.con_archivo_carga a ON a.id_archivo=d.id_archivo
      WHERE i.id_jornada=%s AND a.tipo_archivo IN ('CAET','CANT')
      ORDER BY d.id_archivo,d.linea_origen
    """,(id_jornada,))
    columnas=[x.name if hasattr(x,'name') else x[0] for x in cur.description]
    datos=[dict(zip(columnas,f)) for f in cur.fetchall()]
    filas=construir_entradas(datos)
    calculo=evaluar(filas)
    for r in calculo['resultados']:
        if r.get('columna_importe')=='B' and r.get('valor_base') is not None:
            r['unidad']='CANTIDAD_NO_MONETARIA'
        elif r.get('valor_base') is not None:r['unidad']='IMPORTE_CANDIDATO_NO_HOMOLOGADO'
    return {'id_jornada':id_jornada,'registros':len(datos),'filas_totales':len(filas),
            'calculo':calculo,'certificado':False,
            'advertencia':'Columnas B son conteos; las formulas no se cruzan con Host sin conversion y reglas aprobadas.'}
