"""Inc39: lectura de evidencias F2 en PostgreSQL, sin escritura ni cruces."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
try:
    from psycopg.rows import dict_row
except ModuleNotFoundError:
    dict_row = None  # Las pruebas unitarias utilizan un cursor simulado.

TIPOS = ('CAET','CANT','CARTA_COMPENSACION')
TABLAS = {'CAET':'con_canje_detalle','CANT':'con_canje_detalle','CARTA_COMPENSACION':'con_carta_compensacion_detalle'}

def _fecha(v):
    return v.isoformat() if isinstance(v,date) else str(v)

def leer_jornada(id_jornada:int, conectar=None, limite_detalle:int=100000):
    if type(id_jornada) is not int or id_jornada<=0: raise ValueError('id_jornada invalido')
    if type(limite_detalle) is not int or not 1<=limite_detalle<=100000: raise ValueError('limite_detalle invalido')
    if conectar is None:
        from app.repositories.database import connection
        conectar=connection
    with conectar() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('SELECT id_jornada,fecha_contable,estado FROM public.con_jornada WHERE id_jornada=%s',(id_jornada,))
            j=cur.fetchone()
            if j is None: raise ValueError('Jornada no encontrada')
            cur.execute("""SELECT DISTINCT a.id_archivo,a.tipo_archivo,a.estado,a.fecha_contable,
                             a.checksum_sha256,a.correlation_id
                             FROM public.con_insumo_esperado i
                             JOIN public.con_archivo_carga a ON a.id_archivo=i.id_archivo
                             WHERE i.id_jornada=%s AND a.tipo_archivo=ANY(%s)
                             ORDER BY a.id_archivo""",(id_jornada,list(TIPOS)))
            archivos=cur.fetchall()
            salida=[]
            for a in archivos:
                tipo=a['tipo_archivo']; tabla=TABLAS[tipo]
                if _fecha(a['fecha_contable'])!=_fecha(j['fecha_contable']):
                    estado='FECHA_INCONSISTENTE'
                elif a['estado']!='PROCESADO': estado='ARCHIVO_NO_PROCESADO'
                else: estado='DETALLE_DISPONIBLE_NO_HOMOLOGADO'
                # Solo conteos: no se exponen PAN, lineas crudas ni importes sin regla acreditada.
                cur.execute(f'SELECT COUNT(*) AS n FROM public.{tabla} WHERE id_archivo=%s',(a['id_archivo'],))
                n=cur.fetchone()['n']
                if n>limite_detalle: estado='LIMITE_DETALLE_EXCEDIDO'
                if n==0 and estado=='DETALLE_DISPONIBLE_NO_HOMOLOGADO': estado='SIN_DETALLE'
                salida.append({'id_jornada':id_jornada,'id_archivo':a['id_archivo'],
                    'tipo_insumo':tipo,'franquicia':'CREDIBANCO',
                    'fecha_contable':_fecha(a['fecha_contable']),
                    'correlation_id':a['correlation_id'],
                    'checksum_sha256':str(a['checksum_sha256']).strip() if a['checksum_sha256'] else None,
                    'registros_detalle':n,'estado':estado,
                    'valor':None,'cuenta':None,'regla':None,'certificado':False})
    return {'id_jornada':id_jornada,'fecha_contable':_fecha(j['fecha_contable']),
        'estado_jornada':j['estado'],'origen':'POSTGRESQL_SOLO_LECTURA',
        'certificado':False,'archivos':salida,'resultados_calculados':[],
        'cruces':[],'indicadores':{'cruces':0,'conciliados':0,'diferencias':0,'incorporados_maestro':0},
        'advertencias':['Los conteos acreditan presencia de detalle, no calculo F2.',
          'Las reglas 37/38 requieren celdas de origen y CARTA con correspondencia demostrada.',
          'No se convierten registros de detalle en importes sin mapeo funcional.',
          'No se modifica el UX/UI ni se generan conciliaciones.']}
