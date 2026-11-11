"""Auditoria V26 persistida. No usa fixtures ni altera datos."""
from collections import defaultdict
from decimal import Decimal
from psycopg.rows import dict_row
from app.repositories.database import connection
from app.services.fase2.motor_v26 import evaluar

CLASIFICACIONES=(
 ('299095301','cuenta','CANJE RECIBIDO TARJETA DEBITO','vl_total'),
 ('299095300','cuentas_comisiones','COMISIONES EXIT','comision_op_exitosas'),
 ('299095880','cuenta_880','REGALO',None),
)

def diagnosticar_v26(id_jornada):
    if id_jornada<=0:raise ValueError('Jornada invalida')
    with connection() as conn:
      with conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute('SELECT fecha_contable FROM public.con_jornada WHERE id_jornada=%s',(id_jornada,))
        jornada=cur.fetchone()
        if jornada is None:return None
        cur.execute('''SELECT i.tipo_insumo,i.id_archivo FROM public.con_insumo_esperado i
                       WHERE i.id_jornada=%s AND i.estado='PROCESADO' AND i.id_archivo IS NOT NULL''',(id_jornada,))
        archivos=cur.fetchall()
        host_ids=[r['id_archivo'] for r in archivos if r['tipo_insumo'] in ('HA22','HA26','HA32')]
        canje_ids=[r['id_archivo'] for r in archivos if r['tipo_insumo'] in ('CAET','CANT')]
        cur.execute('''SELECT id_host_resultado,id_archivo,tx_host,cuenta,centro,fecha_contable,valor_debe,valor_haber
                       FROM public.con_host_resultado WHERE id_archivo=ANY(%s)''',(host_ids,))
        host=cur.fetchall()
        cur.execute('''SELECT id_canje_detalle,id_archivo,tipo_archivo,linea_origen,correlation_id,
                       cuenta,cuentas_comisiones,cuenta_880,vl_total,comision_op_exitosas
                       FROM public.con_canje_detalle WHERE id_archivo=ANY(%s)''',(canje_ids,))
        canje=cur.fetchall()
    salida=[]
    for cuenta,familia,texto,campo in CLASIFICACIONES:
        elegidos=[]
        for r in canje:
            if texto in str(r.get(familia) or '').upper():
                elegidos.append({**r,'familia':familia})
        contrapartidas=[h for h in host if str(h.get('cuenta') or '').strip()==cuenta]
        diagnostico=evaluar(cuenta,elegidos,contrapartidas)  # NO regla aprobada; nunca certifica.
        candidato=None
        if campo and elegidos and all(r.get(campo) is not None for r in elegidos):
            candidato=str(sum((Decimal(str(r[campo])) for r in elegidos),Decimal('0')))
        diagnostico.update({'familia':familia,'concepto_patron':texto,'campo_candidato':campo,
            'registros_canje':len(elegidos),'movimientos_host':len(contrapartidas),
            'fuentes_host_observadas':sorted({str(h['tx_host']) for h in contrapartidas}),
            'importe_candidato_no_homologado':candidato,
            'archivos_canje':sorted({r['id_archivo'] for r in elegidos}),
            'archivos_host':sorted({h['id_archivo'] for h in contrapartidas}),
            'advertencia':'Sin regla aprobada de fuente, signo, naturaleza y fecha; no se calcula diferencia.'})
        salida.append(diagnostico)
    return {'id_jornada':id_jornada,'fecha_contable':str(jornada['fecha_contable']),
        'modo':'MOTOR_V26_PERSISTIDO_NO_CERTIFICADO','certificado':False,
        'total_host':len(host),'total_canje':len(canje),'resultados':salida,
        'cruces_certificados':[],
        'advertencia':'Candidatos documentales. La ausencia de Host impide conciliar; no se fabrican contrapartidas.'}
