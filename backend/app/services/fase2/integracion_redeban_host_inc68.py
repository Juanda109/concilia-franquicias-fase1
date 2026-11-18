"""INC68: adaptador de lectura para diagnostico Redeban/Host; nunca certifica."""
from collections import Counter
from datetime import date
from app.services.catalogo_cuentas_host import cargar_cuentas_host
from app.services.fase2.homologacion_franquicias import cargar_homologaciones
from app.services.fase2.comparador_redeban_host_inc67 import comparar

HOST_TIPOS = ('HA22', 'HA26', 'HA32')


def leer_host_jornada(id_jornada, conexion=None):
    """Lee solamente archivos Host PROCESADO vinculados a esta jornada.

    No combina HA32 con movimientos; devuelve la fuente y sus filas separadas.
    """
    if type(id_jornada) is not int or id_jornada <= 0:
        raise ValueError('Jornada invalida')
    if conexion is None:
        from app.repositories.database import connection
        conexion = connection
    with conexion() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('SELECT fecha_contable FROM public.con_jornada WHERE id_jornada=%s', (id_jornada,))
            jornada = cur.fetchone()
            if jornada is None:
                raise ValueError('Jornada inexistente')
            fecha = jornada[0]
            cur.execute('''
                SELECT i.tipo_insumo, i.estado, i.id_archivo, a.estado
                FROM public.con_insumo_esperado i
                LEFT JOIN public.con_archivo_carga a ON a.id_archivo=i.id_archivo
                WHERE i.id_jornada=%s AND i.tipo_insumo IN ('HA22','HA26','HA32')
                ORDER BY i.tipo_insumo
            ''', (id_jornada,))
            asociados = cur.fetchall()
            if len(asociados) != 3 or {r[0] for r in asociados} != set(HOST_TIPOS):
                return fecha, [], 'HOST_PENDIENTE'
            if any(r[1] != 'PROCESADO' or r[2] is None or r[3] != 'PROCESADO' for r in asociados):
                return fecha, [], 'HOST_PENDIENTE'
            filas = []
            for tipo, _, id_archivo, _ in asociados:
                tabla = {'HA22':'con_ha22_detalle','HA26':'con_ha26_detalle','HA32':'con_ha32_detalle'}[tipo]
                cur.execute(f'''
                    SELECT id_archivo, linea_origen, nucta, cedestin,
                           fecha_contable, debe, haber, campos_origen
                    FROM public.{tabla} WHERE id_archivo=%s ORDER BY linea_origen
                ''', (id_archivo,))
                for archivo, linea, cuenta, centro, fecha_detalle, debe, haber, origen in cur.fetchall():
                    filas.append({'fuente':tipo, 'id_archivo':archivo, 'linea':linea,
                                  'cuenta':cuenta, 'centro':centro,
                                  'fecha_contable':str(fecha_detalle), 'debe':debe,
                                  'haber':haber, 'campos_origen':origen})
            return fecha, filas, 'HOST_DISPONIBLE' if filas else 'HOST_SIN_DETALLE'


def diagnosticar_jornada(id_jornada, *, consultar_reporte=None, leer_host=None,
                         catalogo=None, homologaciones=None,
                         reglas_fecha_validadas=None, signo_host=None):
    """Orquesta INC66 e INC67; bloquea diferencias cuando falta Host."""
    if consultar_reporte is None:
        from app.services.fase2.reporte_pmd_inc59 import consultar as consultar_reporte
    if leer_host is None:
        leer_host = leer_host_jornada
    catalogo = cargar_cuentas_host() if catalogo is None else catalogo
    homologaciones = cargar_homologaciones() if homologaciones is None else homologaciones
    reporte = consultar_reporte(id_jornada)
    if reporte.get('certificado') is not False:
        raise ValueError('Reporte certificado no permitido')
    diag = reporte.get('diagnostico_redeban_inc64')
    if not isinstance(diag, dict) or diag.get('certificado') is not False:
        raise ValueError('Diagnostico Redeban INC64 ausente o certificado')
    filas = diag['detalle']
    if len(filas) != diag['cantidad_filas']:
        raise ValueError('Detalle Redeban inconsistente')
    fecha, host, estado_host = leer_host(id_jornada)
    if estado_host != 'HOST_DISPONIBLE':
        return {'id_jornada':id_jornada, 'fecha_contable':str(fecha),
                'estado':estado_host, 'certificado':False,
                'total_filas_redeban':len(filas),
                'estados_redeban':dict(Counter(f['estado'] for f in filas)),
                'cuentas':[], 'diferencias_calculadas':0,
                'advertencia':'Sin Host completo asociado; no se calcula diferencia monetaria.'}
    # HA32 es una fuente de saldo; sin una regla aprobada no se combina con HA22/HA26.
    host_movimientos = [f for f in host if f['fuente'] in ('HA22','HA26')]
    resultado = comparar(catalogo, homologaciones, filas, host_movimientos, fecha,
                        reglas_fecha_validadas=reglas_fecha_validadas,
                        signo_host=signo_host)
    resultado.update(id_jornada=id_jornada, fecha_contable=str(fecha),
                     host_ha32_excluido_de_suma=sum(f['fuente']=='HA32' for f in host),
                     certificado=False)
    return resultado
