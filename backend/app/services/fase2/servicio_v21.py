"""Vista de diagnostico V21: correspondencias documentales; NO conciliacion certificada."""
from collections import defaultdict
from decimal import Decimal
from psycopg.rows import dict_row
from app.repositories.database import connection

MAPAS = (
    ('299095301', 'cuenta', '017-CANJE RECIBIDO TARJETA DEBITO', 'vl_total'),
    ('299095300', 'cuentas_comisiones', '017-COMISIONES EXIT. TARJETA DEBITO ONLINE', 'comision_op_exitosas'),
    ('299095880', 'cuenta_880', '017-CANJE RECIBIDO TARJETA DEBITO REGALO', None),
)

def evaluar_registros(host, canje):
    cuentas = defaultdict(list)
    for h in host:
        cuentas[str(h['cuenta'])].append(h)
    salida = []
    for cuenta, campo, literal, importe in MAPAS:
        filas = [r for r in canje if str(r.get(campo) or '').strip() == literal]
        hosts = cuentas.get(cuenta, [])
        fuentes = sorted({str(h['tx_host']) for h in hosts})
        # Las fuentes multiples nunca se suman sin regla aprobada.
        estado = ('SIN_CONCEPTO' if not filas else 'SIN_HOST' if not hosts
                  else 'PENDIENTE_REGLA_MONETARIA')
        salida.append({'cuenta': cuenta, 'concepto': literal, 'familia': campo,
                       'campo_monetario_candidato': importe, 'registros_canje': len(filas),
                       'movimientos_host': len(hosts), 'fuentes_host_observadas': fuentes,
                       'estado': estado, 'valor_franquicia_homologado': None,
                       'diferencia_certificada': None, 'certificado': False,
                       'advertencia': 'Concepto-cuenta documentado; fuente Host, signo, fecha y uso monetario requieren validacion.'})
    return salida

def diagnosticar_jornada(jornada):
    with connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('SELECT id_jornada, fecha_contable FROM public.con_jornada WHERE id_jornada=%s', (jornada,))
            meta = cur.fetchone()
            if not meta:
                return None
            cur.execute('''SELECT h.id_archivo,h.cuenta,h.centro,h.tx_host,h.fecha_contable,
                         h.valor_debe,h.valor_haber,h.valor_normalizado,h.linea_origen
                         FROM public.con_host_resultado h JOIN public.con_insumo_esperado i ON i.id_archivo=h.id_archivo
                         WHERE i.id_jornada=%s AND i.tipo_insumo IN ('HA22','HA26','HA32')''', (jornada,))
            host = cur.fetchall()
            cur.execute('''SELECT c.id_archivo,c.linea_origen,c.tipo_archivo,c.cuenta,c.cuentas_comisiones,
                         c.cuenta_880,c.vl_total,c.vl_interc,c.comision_op_exitosas
                         FROM public.con_canje_detalle c JOIN public.con_insumo_esperado i ON i.id_archivo=c.id_archivo
                         WHERE i.id_jornada=%s AND i.tipo_insumo IN ('CAET','CANT')''', (jornada,))
            canje = cur.fetchall()
    return {'id_jornada': jornada, 'fecha_contable': str(meta['fecha_contable']),
            'modo': 'DIAGNOSTICO_DOCUMENTAL_NO_CERTIFICADO', 'certificado': False,
            'total_host': len(host), 'total_canje': len(canje),
            'correspondencias': evaluar_registros(host, canje),
            'cruces_certificados': [],
            'nota': 'No se inventan fuente Host, signo ni campo de cuenta_880. No se suman familias superpuestas.'}
