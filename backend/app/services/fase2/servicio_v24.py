"""Auditoria monetaria por jornada: solo lectura, sin homologacion inventada."""
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
import csv
from psycopg.rows import dict_row
from app.repositories.database import connection

CAMPOS = {
    ('299095301', 'cuenta'): ('CANJE RECIBIDO TARJETA DEBITO', 'vl_total'),
    ('299095300', 'cuentas_comisiones'): ('COMISIONES EXIT', 'comision_op_exitosas'),
    ('299095880', 'cuenta_880'): ('REGALO', None),
}

def diagnosticar(id_jornada: int):
    if id_jornada <= 0:
        raise ValueError('Jornada invalida')
    with connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('SELECT id_jornada,fecha_contable FROM public.con_jornada WHERE id_jornada=%s', (id_jornada,))
            jornada = cur.fetchone()
            if jornada is None:
                return None
            cur.execute('''SELECT i.tipo_insumo, a.id_archivo FROM public.con_insumo_esperado i
                JOIN public.con_archivo_carga a ON a.id_archivo=i.id_archivo
                WHERE i.id_jornada=%s AND i.estado='PROCESADO' ''', (id_jornada,))
            archivos=cur.fetchall()
            host_ids=[r['id_archivo'] for r in archivos if r['tipo_insumo'] in ('HA22','HA26','HA32')]
            canje_ids=[r['id_archivo'] for r in archivos if r['tipo_insumo'] in ('CAET','CANT')]
            cur.execute('''SELECT id_archivo,tx_host,cuenta,centro,fecha_contable,
                valor_debe,valor_haber,valor_normalizado,correlation_id
                FROM public.con_host_resultado WHERE id_archivo=ANY(%s)''',(host_ids,))
            host=cur.fetchall()
            cur.execute('''SELECT id_archivo,tipo_archivo,linea_origen,correlation_id,
                cuenta,cuentas_comisiones,cuenta_880,vl_total,comision_op_exitosas
                FROM public.con_canje_detalle WHERE id_archivo=ANY(%s)''',(canje_ids,))
            canje=cur.fetchall()
    salida=[]
    for (cuenta,familia),(texto,campo) in CAMPOS.items():
        seleccion=[r for r in canje if texto in str(r.get(familia) or '').upper()]
        contrapartidas=[r for r in host if str(r.get('cuenta') or '').strip()==cuenta]
        fuentes=sorted({str(r['tx_host']) for r in contrapartidas})
        # Sumas candidatas: nunca equivalen a importe homologado
        valores=[Decimal(str(r[campo])) for r in seleccion if campo and r.get(campo) is not None] if campo else []
        candidato=sum(valores,Decimal('0')) if campo and valores else None
        if not seleccion: estado='SIN_CONCEPTO'
        elif not contrapartidas: estado='SIN_HOST'
        elif len(fuentes)>1: estado='FUENTE_HOST_AMBIGUA'
        else: estado='PENDIENTE_REGLA_MONETARIA'
        salida.append({'cuenta':cuenta,'familia':familia,'concepto_patron':texto,
            'campo_candidato':campo,'registros_canje':len(seleccion),
            'ids_canje':sorted({r['id_archivo'] for r in seleccion}),
            'movimientos_host':len(contrapartidas),'ids_host':sorted({r['id_archivo'] for r in contrapartidas}),
            'fuentes_host_observadas':fuentes,'importe_candidato_no_homologado':str(candidato) if candidato is not None else None,
            'importe_host_homologado':None,'diferencia':None,'estado':estado,'certificado':False,
            'advertencia':'Fuente, fecha, signo y naturaleza requieren regla aprobada; no sumar familias superpuestas.'})
    return {'id_jornada':id_jornada,'fecha_contable':str(jornada['fecha_contable']),
        'modo':'AUDITORIA_MONETARIA_PERSISTIDA_NO_CERTIFICADA','certificado':False,
        'total_host':len(host),'total_canje':len(canje),'resultados':salida,
        'cruces_certificados':[], 'advertencia':'Importes candidatos provienen de PostgreSQL, no de fixtures; no son diferencias contables homologadas.'}
