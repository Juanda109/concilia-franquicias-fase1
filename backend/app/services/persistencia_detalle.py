from app.services.bloqueo_jornada import verificar_jornada_modificable
from app.services.bloqueo_jornada import verificar_asociacion_jornada
from app.services.bloqueo_jornada import bloquear_jornada_por_archivo
"""Persistencia del detalle fuente, independiente de resultados contables existentes."""
import hashlib
from pathlib import Path
from decimal import Decimal
from psycopg import sql
from psycopg.types.json import Jsonb
from fastapi.encoders import jsonable_encoder
from app.repositories.database import connection
from app.ingestion.registry import obtener_parser
from app.services.interpretacion_archivos import interpretar_archivo

CAMPOS_CANJE = ('tx', 'bin_dest', 'tipo', 'fecha_canje', 'ofi', 'tarjeta', 'vl_total', 'vl_descue', 'vl_interc', 'plaz', 'mot_cob', 'iden_red', 'cod_error', 'mo_to', 'ind_cash', 'espacios', 'comision_op_exitosas', 'cuenta', 'cuentas_comisiones', 'tii_recibida_emisor_visa_op_rever_ventas', 'xx', 'cuenta_880')
NUMERICOS = frozenset(('vl_total', 'vl_descue', 'vl_interc', 'comision_op_exitosas', 'tii_recibida_emisor_visa_op_rever_ventas'))
# Campos de la hoja parte que el parser aun no extrae se almacenan NULL.
# Nunca se fabrican valores a partir de posiciones no verificadas.
MAPEO_CANJE = {campo: campo.upper() for campo in CAMPOS_CANJE}
HOST = {'HA22': 'con_ha22_detalle', 'HA26': 'con_ha26_detalle', 'HA32': 'con_ha32_detalle'}


CAMPOS_HOST_TIPADOS = {
    "HA22": (
        "tx_origen", "tabla_origen", "empresa", "nucta",
        "ceorigen", "cedestin", "fecon", "feproc",
        "numas", "numap", "debe", "haber", "clacon",
        "descon", "tipapun", "numdo", "observ",
        "observ2", "codusu", "horatr",
    ),
    "HA26": (
        "tx_origen", "tabla_origen", "empresa", "nucta",
        "ceorigen", "cedestin", "fecon", "feproc",
        "numas", "numap", "debe", "haber", "clacon",
        "descon", "tipapun", "haynumdo", "numdo",
        "observ", "observ2", "codusu", "horatr",
    ),
    "HA32": (
        "tx_origen", "tabla_origen", "tabla_origen1",
        "empresa", "nucta", "cedestin", "fecont",
        "debe", "haber", "saldo_inicial",
    ),
}

CAMPOS_HOST_NUMERICOS = {
    "debe", "haber", "saldo_inicial",
}

CAMPOS_HOST_FECHAS = {
    "fecon", "feproc", "fecont",
}

CAMPOS_DEPO = ('tipo_movimiento', 'bin_fuente', 'bin_destino', 'fecha_del_canje', 'numero_del_lote', 'numero_del_registro', 'bin_receptor', 'fecha_contabilizacion', 'numero_secuencia', 'digito_chequeo', 'cod_oficina', 'no_tarjeta', 'no_comprobante', 'fecha_comprobante', 'cod_comercio', 'porcentaje_descuento', 'cod_autorizacion', 'valor_compra', 'valor_propina', 'valor_total', 'valor_descuento', 'valor_intercambio', 'plazo', 'motivo_cobro', 'tx_anterior', 'captura', 'fecha_de_deposito', 'cuenta_de_deposito', 'numero_de_terminal', 'codigo_alterno', 'tipo_de_red', 'identificador_red_adquirente', 'cod_de_error', 'identificador_reg_inconsistente', 'valor_del_iva_vlor_transf', 'vlor_retencion_compra', 'vlor_retencion_iva', 'valor_deposito_neto', 'valor_ica', 'valor_intercambio_2', 'valor_iva_a_retornar', 'indicador_mo_to_o_comercio_electro', 'indicador_cash_back', 'espacios', 'tasa_de_intercambio', 'amex_nacional', 'cuenta', 'tii', 'comision_adq_atm_2888', 'tii_5130')

CAMPOS_CARTA = ('seccion', 'motivo_codigo', 'es_control', 'lado', 'concepto', 'valor_principal', 'valor_proceso', 'valor_financiacion', 'valor_fotocopias', 'valor_red', 'valor_depositos_electronicos', 'valor_total', 'valor_outgoing', 'valor_incoming', 'factor_compra', 'factor_venta', 'cinta', 'fecha_cinta')
NUMERICOS_CARTA = frozenset(('valor_principal', 'valor_proceso', 'valor_financiacion', 'valor_fotocopias', 'valor_red', 'valor_depositos_electronicos', 'valor_total', 'valor_outgoing', 'valor_incoming', 'factor_compra', 'factor_venta'))


CAMPOS_PMD = (
    'producto_servicio',
    'nivel',
    'es_control',
    'fecha_archivo',
    'debito_cantidad',
    'debito_valor',
    'debito_comision_intercambio',
    'debito_comision_administrativa',
    'debito_neto',
    'credito_cantidad',
    'credito_valor',
    'credito_comision_intercambio',
    'credito_comision_administrativa',
    'credito_neto',
    'total',
)


CAMPOS_MEP = ('centro_de_costo', 'cuenta', 'divisa', 'contrato', 'referencia_de_cruce', 'importe', 'descripcion', 'fecha', 'tipo_de_documento', 'numero_de_documento', 'digito_de_verificacion', 'tipo_de_perdida', 'clase_riesgo', 'tipo_de_movimiento', 'producto', 'proceso', 'linea_operativa', 'valor_base')
MAPEO_MEP = {'centro_de_costo': 'CENTRO DE COSTO', 'cuenta': 'CUENTA', 'divisa': 'DIVISA', 'contrato': 'CONTRATO', 'referencia_de_cruce': 'REFERENCIA DE CRUCE', 'importe': 'IMPORTE', 'descripcion': 'DESCRIPCION', 'fecha': 'FECHA', 'tipo_de_documento': 'TIPO DE DOCUMENTO', 'numero_de_documento': 'NUMERO DE DOCUMENTO', 'digito_de_verificacion': 'DIGITO DE VERIFICACION', 'tipo_de_perdida': 'TIPO DE PERDIDA', 'clase_riesgo': 'CLASE RIESGO', 'tipo_de_movimiento': 'TIPO DE MOVIMIENTO', 'producto': 'PRODUCTO', 'proceso': 'PROCESO', 'linea_operativa': 'LINEA OPERATIVA', 'valor_base': 'VALOR BASE'}
NUMERICOS_MEP = frozenset(('importe', 'valor_base'))


CAMPOS_VSS = ('reporte', 'pagina', 'moneda_liquidacion', 'moneda_compensacion', 'fecha_reporte', 'concepto', 'valores', 'signos', 'texto_original', 'es_control')
MAPEO_VSS = {'reporte': 'REPORTE', 'pagina': 'PAGINA', 'moneda_liquidacion': 'MONEDA_LIQUIDACION', 'moneda_compensacion': 'MONEDA_COMPENSACION', 'fecha_reporte': 'FECHA_REPORTE', 'concepto': 'CONCEPTO', 'valores': 'VALORES', 'signos': 'SIGNOS', 'texto_original': 'TEXTO_ORIGINAL', 'es_control': 'ES_CONTROL'}

class DetalleError(ValueError):
    pass

def _verificar_checksum(ruta, esperado):
    h = hashlib.sha256()
    with ruta.open('rb') as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b''):
            h.update(bloque)
    if not esperado or h.hexdigest().lower() != str(esperado).strip().lower():
        raise DetalleError('Checksum del archivo no coincide')

def persistir_detalle(id_archivo):
    """Persiste CAET/CANT y snapshots Host; no altera normalizados previos.

    CAET recibido cambia a PROCESADO al finalizar. CANT/Host procesados
    se enriquecen sin duplicar su evento ARCHIVO_PROCESADO.
    """
    with connection() as conn:
        with conn.cursor() as cur:
            id_jornada_bloqueada = bloquear_jornada_por_archivo(
                cur, id_archivo
            )

            verificar_asociacion_jornada(
                cur, id_archivo, id_jornada_bloqueada
            )

            verificar_jornada_modificable(
                cur, id_jornada_bloqueada
            )

            cur.execute("""
                SELECT a.tipo_archivo,a.ruta_archivo,a.nombre_archivo,
                       a.checksum_sha256,a.fecha_contable,a.correlation_id,
                       a.estado,i.id_insumo_esperado,i.estado,j.fecha_contable
                FROM con_archivo_carga a
                JOIN con_insumo_esperado i ON i.id_archivo=a.id_archivo
                JOIN con_jornada j ON j.id_jornada=i.id_jornada
                WHERE a.id_archivo=%s FOR UPDATE OF a,i
            """, (id_archivo,))
            fila=cur.fetchone()
            if fila is None:
                raise DetalleError('Archivo no asociado a jornada')
            tipo,ruta,nombre,checksum,fecha,corr,estado,insumo,estado_i,fecha_j=fila
            if tipo not in ('CAET','CANT','DEPO','CARTA_COMPENSACION','PMD','MEP','VSS','VISA_SS_INTERNATIONAL',*HOST):
                raise DetalleError('Tipo no habilitado para detalle')
            if fecha != fecha_j or estado != estado_i or estado not in ('RECIBIDO','PROCESADO'):
                raise DetalleError('Estados o fechas incompatibles')
            if tipo in HOST and estado != 'PROCESADO':
                raise DetalleError('Procesar Host con el loader existente primero')
            tablas = {
                'CAET': 'con_canje_detalle',
                'CANT': 'con_canje_detalle',
                'DEPO': 'con_depo_detalle',
                'CARTA_COMPENSACION': 'con_carta_compensacion_detalle',
                'PMD': 'con_pmd_detalle',
                'MEP': 'con_mep_detalle',
                'VSS': 'con_vss_detalle',
                'VISA_SS_INTERNATIONAL': 'con_visa_ss_international_detalle',
            }
            tabla = HOST[tipo] if tipo in HOST else tablas[tipo]
            cur.execute(sql.SQL('SELECT COUNT(*) FROM {} WHERE id_archivo=%s').format(sql.Identifier(tabla)),(id_archivo,))
            existentes=cur.fetchone()[0]
            fisico=Path(ruta)
            if not fisico.is_file():
                raise DetalleError('Archivo fisico no encontrado')
            _verificar_checksum(fisico,checksum)
            resultado=interpretar_archivo(tipo,fisico,nombre)
            if resultado.errors:
                raise DetalleError('Parser reporto errores')
            if tipo == 'DEPO':
                resultado.controls.append({'codigo': 'DERIVADOS_PENDIENTES', 'obtenido': 'AMEX_NACIONAL,CUENTA,TII,COMISION_ADQ_ATM_2888,TII_5130'})
            registros=resultado.records
            if not registros:
                raise DetalleError('Sin registros persistibles')
            lineas=[r['numero_linea'] for r in registros]
            if tipo == 'CARTA_COMPENSACION':
                claves = [
                    (r['seccion'], r['numero_linea'])
                    for r in registros
                ]
            else:
                claves = lineas

            if len(claves) != len(set(claves)):
                raise DetalleError('Lineas duplicadas')
            if existentes:
                if tipo == 'CARTA_COMPENSACION':
                    consulta = sql.SQL(
                        'SELECT seccion, linea_origen FROM {} '
                        'WHERE id_archivo=%s '
                        'ORDER BY seccion, linea_origen'
                    ).format(sql.Identifier(tabla))

                    cur.execute(consulta, (id_archivo,))
                    persistidas = [
                        (r[0], r[1])
                        for r in cur.fetchall()
                    ]

                    esperadas = sorted(claves)
                else:
                    consulta = sql.SQL(
                        'SELECT linea_origen FROM {} '
                        'WHERE id_archivo=%s '
                        'ORDER BY linea_origen'
                    ).format(sql.Identifier(tabla))

                    cur.execute(consulta, (id_archivo,))
                    persistidas = [
                        r[0]
                        for r in cur.fetchall()
                    ]

                    esperadas = sorted(lineas)

                if persistidas != esperadas:
                    raise DetalleError(
                        'Detalle parcial o inconsistente; '
                        'no se declara idempotente'
                    )
                if tipo == 'CARTA_COMPENSACION':
                    cur.execute(
                        'SELECT codigo, valor_obtenido, '
                        'valor_esperado, valor_obtenido_numerico, '
                        'estado_validacion '
                        'FROM con_detalle_control WHERE id_archivo=%s',
                        (id_archivo,)
                    )

                    guardados = {
                        fila[0]: fila[1:]
                        for fila in cur.fetchall()
                    }

                    esperados = {}

                    for control in resultado.controls:
                        esperado = control.get('esperado')
                        obtenido = control.get('obtenido')

                        if esperado is not None:
                            esperado = Decimal(str(esperado))

                        obtenido_num = (
                            Decimal(str(obtenido))
                            if control.get('codigo') == 'CUADRE_POSICION_NETA'
                            and obtenido is not None
                            else None
                        )

                        esperados[control['codigo']] = (
                            str(obtenido),
                            esperado,
                            obtenido_num,
                            control.get('estado'),
                        )

                    if guardados != esperados:
                        raise DetalleError(
                            'Controles Carta incompletos o inconsistentes'
                        )
                else:
                    cur.execute(
                        'SELECT codigo,valor_obtenido '
                        'FROM con_detalle_control WHERE id_archivo=%s',
                        (id_archivo,)
                    )
                    guardados = dict(cur.fetchall())
                    esperados = {
                        c['codigo']: str(c.get('obtenido'))
                        for c in resultado.controls
                    }

                    if guardados != esperados:
                        raise DetalleError(
                            'Controles incompletos o inconsistentes'
                        )
                return {'id_archivo':id_archivo,'tipo':tipo,'registros':existentes,'idempotente':True}
            if tipo in ('CAET','CANT'):
                columnas=['id_archivo','tipo_archivo','fecha_contable','linea_origen','correlation_id',*CAMPOS_CANJE]
                stmt=sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                    sql.Identifier(tabla),sql.SQL(',').join(map(sql.Identifier,columnas)),
                    sql.SQL(',').join(sql.Placeholder()*len(columnas)))
                for registro in registros:
                    valores=[id_archivo,tipo,fecha,registro['numero_linea'],corr]
                    for campo in CAMPOS_CANJE:
                        # Mapeo explicito del contrato de la hoja parte.
                        v=registro.get(MAPEO_CANJE[campo])
                        if campo in NUMERICOS and v not in (None,''):
                            v=Decimal(str(v))
                        if v=='': v=None
                        valores.append(v)
                    cur.execute(stmt,valores)
            elif tipo == 'VISA_SS_INTERNATIONAL':
                columnas = ('id_archivo','fecha_contable','linea_origen','correlation_id',
                            'pagina','ftsre','nombre_entidad','moneda','importe_neto',
                            'tipo_movimiento','fecha_valor','fecha_procesamiento')
                stmt = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                    sql.Identifier(tabla),
                    sql.SQL(',').join(map(sql.Identifier, columnas)),
                    sql.SQL(',').join(sql.Placeholder() for _ in columnas))
                for registro in registros:
                    cur.execute(stmt, (
                        id_archivo, fecha, registro['numero_linea'], corr,
                        registro['PAGINA'], registro['FTSRE'], registro['NOMBRE_ENTIDAD'],
                        registro['MONEDA'], registro['IMPORTE_NETO'],
                        registro['TIPO_MOVIMIENTO'], registro['FECHA_VALOR'],
                        registro['FECHA_PROCESAMIENTO']))
            elif tipo == 'VSS':
                from psycopg.types.json import Jsonb

                columnas = [
                    'id_archivo',
                    'fecha_contable',
                    'linea_origen',
                    'correlation_id',
                    *CAMPOS_VSS,
                ]

                stmt = sql.SQL(
                    'INSERT INTO {} ({}) VALUES ({})'
                ).format(
                    sql.Identifier(tabla),
                    sql.SQL(',').join(
                        map(sql.Identifier, columnas)
                    ),
                    sql.SQL(',').join(
                        sql.Placeholder() * len(columnas)
                    ),
                )

                for registro in registros:
                    valores = [
                        id_archivo,
                        fecha,
                        registro['numero_linea'],
                        corr,
                    ]

                    for campo in CAMPOS_VSS:
                        valor = registro.get(MAPEO_VSS[campo])

                        if campo == 'valores':
                            valor = Jsonb([
                                str(v) if v is not None else None
                                for v in valor
                            ])

                        elif campo == 'signos':
                            valor = Jsonb(list(valor))

                        valores.append(valor)

                    cur.execute(stmt, valores)

            elif tipo == 'MEP':
                from datetime import date

                columnas = [
                    'id_archivo', 'fecha_contable',
                    'linea_origen', 'correlation_id',
                    *CAMPOS_MEP,
                ]

                stmt = sql.SQL(
                    'INSERT INTO {} ({}) VALUES ({})'
                ).format(
                    sql.Identifier(tabla),
                    sql.SQL(',').join(map(sql.Identifier, columnas)),
                    sql.SQL(',').join(
                        sql.Placeholder() * len(columnas)
                    ),
                )

                for registro in registros:
                    valores = [
                        id_archivo,
                        fecha,
                        registro['numero_linea'],
                        corr,
                    ]

                    for campo in CAMPOS_MEP:
                        valor = registro.get(MAPEO_MEP[campo])

                        if valor == '':
                            valor = None

                        if campo == 'fecha' and valor is not None:
                            valor = date.fromisoformat(str(valor))

                        if campo in NUMERICOS_MEP and valor is not None:
                            valor = Decimal(str(valor))

                        valores.append(valor)

                    cur.execute(stmt, valores)

            elif tipo == 'PMD':
                campos = CAMPOS_PMD

                columnas = [
                    'id_archivo', 'fecha_contable',
                    'linea_origen', 'correlation_id', *campos,
                ]

                stmt = sql.SQL(
                    'INSERT INTO {} ({}) VALUES ({})'
                ).format(
                    sql.Identifier(tabla),
                    sql.SQL(',').join(map(sql.Identifier, columnas)),
                    sql.SQL(',').join(
                        sql.Placeholder() * len(columnas)
                    ),
                )

                for registro in registros:
                    valores = [
                        id_archivo, fecha,
                        registro['numero_linea'], corr,
                    ]

                    for campo in campos:
                        valor = registro.get(campo.upper())
                        valores.append(valor)

                    cur.execute(stmt, valores)

            elif tipo == 'CARTA_COMPENSACION':
                columnas = ['id_archivo','fecha_contable','linea_origen','correlation_id',*CAMPOS_CARTA]
                stmt = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                    sql.Identifier(tabla), sql.SQL(',').join(map(sql.Identifier,columnas)),
                    sql.SQL(',').join(sql.Placeholder()*len(columnas)))
                for registro in registros:
                    valores = [id_archivo,fecha,registro['numero_linea'],corr]
                    for campo in CAMPOS_CARTA:
                        valor = registro.get(campo)
                        if valor == '': valor = None
                        if campo in NUMERICOS_CARTA and valor is not None:
                            valor = Decimal(str(valor))
                        valores.append(valor)
                    cur.execute(stmt,valores)
            elif tipo == 'DEPO':
                columnas = ['id_archivo', 'fecha_contable', 'linea_origen', 'correlation_id', *CAMPOS_DEPO]
                stmt = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                    sql.Identifier(tabla),
                    sql.SQL(',').join(map(sql.Identifier, columnas)),
                    sql.SQL(',').join(sql.Placeholder() * len(columnas)),
                )
                for registro in registros:
                    valores = [id_archivo, fecha, registro['numero_linea'], corr]
                    for campo in CAMPOS_DEPO:
                        valor = registro.get(campo.upper())
                        if valor == '':
                            valor = None
                        if campo == 'tasa_de_intercambio' and valor is not None:
                            valor = Decimal(str(valor))
                        valores.append(valor)
                    cur.execute(stmt, valores)
            else:
                campos = CAMPOS_HOST_TIPADOS[tipo]
                columnas = [
                    'id_archivo',
                    'fecha_contable',
                    'linea_origen',
                    'correlation_id',
                    'campos_origen',
                    *campos,
                ]

                stmt = sql.SQL(
                    'INSERT INTO {} ({}) VALUES ({})'
                ).format(
                    sql.Identifier(tabla),
                    sql.SQL(',').join(
                        map(sql.Identifier, columnas)
                    ),
                    sql.SQL(',').join(
                        sql.Placeholder() * len(columnas)
                    ),
                )

                for registro in registros:
                    valores = [
                        id_archivo,
                        fecha,
                        registro['numero_linea'],
                        corr,
                        Jsonb(jsonable_encoder(registro)),
                    ]

                    for campo in campos:
                        valor = registro.get(campo.upper())

                        if valor in ('', None):
                            valor = None

                        elif campo in CAMPOS_HOST_NUMERICOS:
                            valor = Decimal(str(valor))

                        elif campo in CAMPOS_HOST_FECHAS:
                            from datetime import date
                            valor = date.fromisoformat(str(valor))

                        valores.append(valor)

                    cur.execute(stmt, valores)
            for control in resultado.controls:
                if tipo == 'CARTA_COMPENSACION':
                    esperado = control.get('esperado')
                    obtenido = control.get('obtenido')

                    valor_esperado = (
                        Decimal(str(esperado))
                        if esperado is not None
                        else None
                    )

                    valor_obtenido_num = (
                        Decimal(str(obtenido))
                        if control.get('codigo') == 'CUADRE_POSICION_NETA'
                        and obtenido is not None
                        else None
                    )

                    cur.execute(
                        """INSERT INTO con_detalle_control
                        (id_archivo, codigo, valor_obtenido,
                         correlation_id, valor_esperado,
                         valor_obtenido_numerico, estado_validacion)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            id_archivo,
                            control['codigo'],
                            str(obtenido),
                            corr,
                            valor_esperado,
                            valor_obtenido_num,
                            control.get('estado'),
                        )
                    )
                else:
                    cur.execute(
                        """INSERT INTO con_detalle_control
                        (id_archivo, codigo, valor_obtenido, correlation_id)
                        VALUES (%s,%s,%s,%s)""",
                        (
                            id_archivo,
                            control['codigo'],
                            str(control.get('obtenido')),
                            corr,
                        )
                    )
            if tipo in ('CAET','CANT','DEPO','CARTA_COMPENSACION','PMD','MEP','VSS','VISA_SS_INTERNATIONAL') and estado=='RECIBIDO':
                cur.execute("UPDATE con_archivo_carga SET estado='PROCESADO',total_registros=%s WHERE id_archivo=%s AND estado='RECIBIDO'",(len(registros),id_archivo))
                if cur.rowcount!=1: raise DetalleError('No se actualizo archivo')
                cur.execute("UPDATE con_insumo_esperado SET estado='PROCESADO',fec_actualizacion=CURRENT_TIMESTAMP WHERE id_insumo_esperado=%s AND estado='RECIBIDO'",(insumo,))
                if cur.rowcount!=1: raise DetalleError('No se actualizo insumo')
            cur.execute("""INSERT INTO con_trazabilidad
                           (correlation_id,id_archivo,id_jornada,tipo_evento,componente,detalle)
                           VALUES (%s,%s,%s,'DETALLE_PERSISTIDO','PROCESAMIENTO_DETALLE',%s)""",
                        (corr, id_archivo, id_jornada_bloqueada,
                         f'{tipo}: {len(registros)} filas'))
            return {'id_archivo':id_archivo,'tipo':tipo,'registros':len(registros),'idempotente':False}
