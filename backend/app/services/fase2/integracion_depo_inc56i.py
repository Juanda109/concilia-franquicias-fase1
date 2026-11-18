"""INC56-I: evidencia DEPO por jornada y sumatorias Host separadas, sin Excel."""

# Referencia autorizada: ESTRUCTURA DEPOSITOS_CREDIBANCO_OK.xlsx,
# hoja 'datos contabilidad', D2:D5. Las formulas SUMIFS definen
# cuenta/naturaleza, NO escala DEPO, signo ni equivalencia monetaria.
from app.services.fase2.proyeccion_monetaria_depo import proyectar_depo

CUENTAS_DEPO_APROBADAS = {
    'DEPOSITO_NACIONAL': '196095001838',
    'DEPOSITO_INTERNACIONAL': '196095001839',
}
NATURALEZAS_DEPO = ('D', 'H')
FUENTES_HOST = ('HA22', 'HA26', 'HA32')


def normalizar_sumifs_host(filas):
    """Reproduce D2:D5 por fuente; nunca suma HA22, HA26 y HA32 entre si.

    Filas: (tx_host, cuenta, debe, haber). Valores ya contables.
    """
    from decimal import Decimal
    totales = {}
    for fuente, cuenta, debe, haber in filas:
        fuente, cuenta = str(fuente).strip(), str(cuenta).strip()
        if fuente not in FUENTES_HOST or cuenta not in CUENTAS_DEPO_APROBADAS.values():
            raise ValueError('Fuente/cuenta Host no autorizada')
        for naturaleza, importe in (('D', debe), ('H', haber)):
            if importe is None:
                continue
            if isinstance(importe, (float, bool)):
                raise ValueError('Importe Host debe ser decimal exacto')
            numero = Decimal(str(importe))
            if not numero.is_finite():
                raise ValueError('Importe Host no finito')
            clave = (fuente, cuenta, naturaleza)
            totales[clave] = totales.get(clave, Decimal('0')) + numero
    celdas = {('196095001838', 'D'): 'D2',
              ('196095001838', 'H'): 'D3',
              ('196095001839', 'D'): 'D4',
              ('196095001839', 'H'): 'D5'}
    return [dict(fuente_host=fuente, cuenta=cuenta, naturaleza=naturaleza,
                 celda_referencia=celdas[(cuenta, naturaleza)],
                 importe_contable=str(total),
                 estado='EVIDENCIA_HOST_NO_CONCILIADA')
            for (fuente, cuenta, naturaleza), total in sorted(totales.items())]


def seleccionar_sumatorias_host(sumatorias, fuente_host):
    """Seleccion explicita: nunca sumar tres fuentes Host entre si."""
    if fuente_host not in FUENTES_HOST:
        raise ValueError('fuente_host debe ser HA22, HA26 o HA32')
    seleccionadas = [dict(fila) for fila in sumatorias
                    if fila['fuente_host'] == fuente_host]
    claves = [(fila['cuenta'], fila['naturaleza']) for fila in seleccionadas]
    if len(claves) != len(set(claves)):
        raise ValueError('Sumatoria Host duplicada para cuenta/naturaleza')
    return {'fuente_host_seleccionada': fuente_host,
            'sumatorias_host_seleccionadas': seleccionadas,
            'certificado_monetario': False,
            'estado': 'EVIDENCIA_HOST_SIN_CRUCE_DEPO'}


def construir_evidencia_contable(sumatorias, fuente_host):
    """Proyecta D2:D5 para una sola fuente; no produce neto ni diferencia DEPO."""
    if fuente_host is None:
        return []
    seleccion = seleccionar_sumatorias_host(sumatorias, fuente_host)
    index = {(r['cuenta'], r['naturaleza']): r for r in seleccion['sumatorias_host_seleccionadas']}
    resultado = []
    for concepto, cuenta in CUENTAS_DEPO_APROBADAS.items():
        debe = index.get((cuenta, 'D'))
        haber = index.get((cuenta, 'H'))
        resultado.append({
            'concepto': concepto,
            'cuenta': cuenta,
            'fuente_host': fuente_host,
            'debe_host': debe['importe_contable'] if debe else None,
            'haber_host': haber['importe_contable'] if haber else None,
            'referencia_debe': 'D2' if concepto == 'DEPOSITO_NACIONAL' else 'D4',
            'referencia_haber': 'D3' if concepto == 'DEPOSITO_NACIONAL' else 'D5',
            'valor_franquicia': None, 'neto_host': None, 'diferencia': None,
            'estado': 'EVIDENCIA_HOST_SIN_HOMOLOGACION_MONETARIA',
            'certificado_monetario': False,
        })
    return resultado


def consultar_depo_jornada(id_jornada, conectar=None, *, fuente_host=None):
    if type(id_jornada) is not int or id_jornada <= 0:
        raise ValueError('Jornada invalida')
    usar_bd_real = conectar is None
    if conectar is None:
        from app.repositories.database import connection
        conectar = connection
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('''SELECT a.id_archivo, a.estado, a.fecha_contable, a.checksum_sha256
                FROM public.con_insumo_esperado i
                JOIN public.con_archivo_carga a ON a.id_archivo=i.id_archivo
                WHERE i.id_jornada=%s AND a.tipo_archivo='DEPO'
                ORDER BY a.id_archivo''', (id_jornada,))
            archivos = cur.fetchall()
            # Control de cobertura: no suma importes crudos ni deduce escala.
            ids = [fila[0] for fila in archivos]
            detalles = {}
            evidencia_host = []
            if ids and usar_bd_real:
                cur.execute('''SELECT id_archivo, COUNT(*)
                    FROM public.con_depo_detalle
                    WHERE id_archivo = ANY(%s)
                    GROUP BY id_archivo''', (ids,))
                detalles = dict(cur.fetchall())
                # CIERRE_DEPO_INTEGRAL_V1: clasificacion por jornada, solo lectura.
                cur.execute('''SELECT id_archivo, linea_origen, tipo_movimiento,
                        cod_oficina, indicador_cash_back, amex_nacional, valor_total
                    FROM public.con_depo_detalle
                    WHERE id_archivo = ANY(%s)
                    ORDER BY id_archivo, linea_origen''', (ids,))
                from app.services.fase2.clasificacion_depo_integral import agrupar
                diagnostico_integral = agrupar(cur.fetchall())
                # INC57_CNB_DIAGNOSTICO: lectura de valores crudos, sin escala ni homologacion.
                cur.execute('''SELECT id_archivo, linea_origen, tipo_movimiento,
                           indicador_cash_back, valor_total
                    FROM public.con_depo_detalle
                    WHERE id_archivo = ANY(%s)
                    ORDER BY id_archivo, linea_origen''', (ids,))
                from app.services.fase2.diagnostico_cnb_depo_inc57 import resumir_cnb
                diagnostico_cnb = resumir_cnb(cur.fetchall())
                # Consulta solo lectura y acotada a la jornada. EXISTS evita
                # multiplicar filas Host por relaciones repetidas de insumos.
                cur.execute('''SELECT h.tx_host, TRIM(h.cuenta),
                           SUM(h.valor_debe), SUM(h.valor_haber)
                    FROM public.con_host_resultado h
                    WHERE h.tx_host IN ('HA22','HA26','HA32')
                      AND TRIM(h.cuenta) IN ('196095001838','196095001839')
                      AND EXISTS (
                          SELECT 1 FROM public.con_insumo_esperado i
                          WHERE i.id_archivo=h.id_archivo AND i.id_jornada=%s
                      )
                    GROUP BY h.tx_host, TRIM(h.cuenta)
                    ORDER BY h.tx_host, TRIM(h.cuenta)''', (id_jornada,))
                evidencia_host = normalizar_sumifs_host(cur.fetchall())
    if not (ids and usar_bd_real):
        from app.services.fase2.diagnostico_cnb_depo_inc57 import resumir_cnb
        diagnostico_cnb = resumir_cnb([])
    if not (ids and usar_bd_real):
        diagnostico_integral = []
    filas = []
    for id_archivo, estado, fecha, checksum in archivos:
        filas.append({'id_archivo': id_archivo, 'tipo_insumo':'DEPO',
            'concepto':'DEPO - archivo de jornada', 'cuenta':None,
            'valor_franquicia':None, 'debe_host':None, 'haber_host':None,
            'neto_host':None, 'diferencia':None,
            'estado':'PENDIENTE_HOMOLOGACION_MONETARIA',
            'estado_archivo':estado, 'fecha_contable':str(fecha),
            'checksum_sha256':str(checksum).strip() if checksum else None,
            'movimientos_persistidos': int(detalles.get(id_archivo, 0)),
            'certificado_monetario':False})

    filas_cuentas_depo = []
    for id_archivo, estado, fecha, checksum in archivos:
        for concepto, cuenta in CUENTAS_DEPO_APROBADAS.items():
            filas_cuentas_depo.append({
                'id_archivo': id_archivo,
                'tipo_insumo': 'DEPO',
                'concepto': concepto,
                'cuenta': cuenta,
                'valor_franquicia': None,
                'debe_host': None,
                'haber_host': None,
                'neto_host': None,
                'diferencia': None,
                'estado': 'PENDIENTE_HOMOLOGACION_MONETARIA',
                'certificado_monetario': False,
            })
    seleccion = (seleccionar_sumatorias_host(evidencia_host, fuente_host)
                 if fuente_host is not None else {
                     'fuente_host_seleccionada': None,
                     'sumatorias_host_seleccionadas': [],
                     'certificado_monetario': False})
    return {'fuente':'DEPO', 'estado':'PENDIENTE_HOMOLOGACION_MONETARIA' if filas else 'SIN_ARCHIVO_DEPO',
        'certificado_monetario':False, 'filas':filas, 'filas_cuentas_depo':filas_cuentas_depo,
        'diagnostico_cnb_inc57': diagnostico_cnb,
        'diagnostico_integral_depo': diagnostico_integral,
        # DEPO_MOTOR_PYTHON_SIN_EXCEL_V1
        'proyeccion_monetaria_depo': proyectar_depo(diagnostico_integral, evidencia_host),
        'cuentas_referencia':dict(CUENTAS_DEPO_APROBADAS),
        'sumatorias_host_por_fuente':evidencia_host,
        'evidencia_contable_seleccionada': construir_evidencia_contable(evidencia_host, fuente_host),
        **seleccion,
        'advertencia':'D2:D5: cuentas/naturalezas Host verificadas. Escala, clasificacion y cruce DEPO-Host no certificados.'}
