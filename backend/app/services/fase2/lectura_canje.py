"""Adaptador read-only PostgreSQL -> clasificacion y agrupacion CAET/CANT F2.

No escribe en tablas F1. No usa cuenta, cuentas_comisiones ni cuenta_880
persistidas por parsers legacy. Los importes se usan con escala almacenada,
sin asumir conversion monetaria no aprobada.
"""
from decimal import Decimal
from app.services.fase2.clasificacion_canje import (
    clasificar_cuenta, clasificar_comision, clasificar_regalo,
)
from app.services.fase2.agrupacion_canje import agrupar_canje

CAMPOS = (
    'd.id_archivo', 'd.linea_origen', 'd.tipo_archivo', 'd.tx',
    'd.bin_dest', 'd.tipo', 'd.espacios', 'd.mot_cob', 'd.cod_error',
    'd.vl_total', 'd.vl_interc', 'd.comision_op_exitosas',
    'd.tii_recibida_emisor_visa_op_rever_ventas',
)


def _texto(valor):
    return '' if valor is None else str(valor).strip()


def _decimal(valor):
    if valor is None or valor == '':
        return None
    if isinstance(valor, (float, bool)):
        raise ValueError('Importe no exacto en lectura de detalle')
    numero = Decimal(str(valor))
    if not numero.is_finite():
        raise ValueError('Importe no finito en lectura de detalle')
    return numero


def transformar_fila(fila):
    """Convierte una fila SQL (dict) en una o varias partidas F2 trazables.

    Cuenta base, comision y regalo son partidas separadas; no se duplican
    importes: valor total/intercambio solo en cuenta base, comision y TII
    solo en la partida de comision, regalo se etiqueta sin sumar importes.
    """
    tipo_archivo = _texto(fila['tipo_archivo']).upper()
    if tipo_archivo not in ('CAET', 'CANT'):
        raise ValueError('Solo CAET/CANT')
    tx = _texto(fila['tx'])
    canal = _texto(fila['espacios'])
    tipo = _texto(fila['tipo'])
    bin_dest = _texto(fila['bin_dest'])
    cod_error = _texto(fila['cod_error'])
    mot_cob = _texto(fila['mot_cob'])
    base = clasificar_cuenta(cod_error=cod_error, tipo=tipo, canal=canal,
                            tx=tx, bin_dest=bin_dest, mot_cob=mot_cob)
    comision = _decimal(fila['comision_op_exitosas'])
    tii = _decimal(fila['tii_recibida_emisor_visa_op_rever_ventas'])
    com = clasificar_comision(tipo=tipo, canal=canal, tx=tx,
                             comision=comision, tii=tii)
    regalo = clasificar_regalo(bin_dest=bin_dest, tipo=tipo, canal=canal, tx=tx)
    common = dict(tipo_insumo=tipo_archivo, id_archivo=fila['id_archivo'],
                  linea_origen=fila['linea_origen'], tipo_tarjeta=tipo,
                  canal=canal, tx=tx)
    # La clasificacion regalo es etiqueta complementaria; no crea otra partida
    # monetaria mientras la equivalencia Excel de esa cuenta no este cerrada.
    principal = {**common, 'cuenta': base.cuenta or '',
                 'vl_total': _decimal(fila['vl_total']),
                 'vl_interc': _decimal(fila['vl_interc']),
                 'comision_op_exitosas': None, 'tii_recibida': None}
    partidas = [principal]
    if com.cuenta:
        # Distinta identidad logica de partida, no duplicar linea en el agregador.
        partidas.append({**common, 'cuenta': com.cuenta, 'linea_origen': f"{fila['linea_origen']}:COM",
                         'vl_total': None, 'vl_interc': None,
                         'comision_op_exitosas': comision if com.regla_id != 'F2-COM-003' else None,
                         'tii_recibida': tii if com.regla_id == 'F2-COM-003' else None})
    return partidas, {
        'id_archivo': fila['id_archivo'], 'linea_origen': fila['linea_origen'],
        'regla_cuenta': base.regla_id, 'motivo_cuenta': base.motivo,
        'regla_comision': com.regla_id, 'regla_regalo': regalo.regla_id,
    }


def consultar_y_agrupar_canje(id_archivo, conexion_factory, limite=100000):
    """Consulta read-only, falla si el archivo no esta procesado o supera limite.

    conexion_factory debe retornar conexion psycopg compatible con context manager.
    No se acepta archivo sin estado PROCESADO. Sin escritura SQL.
    """
    if type(id_archivo) is not int or id_archivo <= 0:
        raise ValueError('id_archivo invalido')
    if type(limite) is not int or not (1 <= limite <= 1000000):
        raise ValueError('limite invalido')
    with conexion_factory() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('''SELECT a.tipo_archivo, a.estado, i.estado
                FROM public.con_archivo_carga a
                JOIN public.con_insumo_esperado i ON i.id_archivo=a.id_archivo
                WHERE a.id_archivo=%s''', (id_archivo,))
            estado = cur.fetchone()
            if not estado or estado[0] not in ('CAET', 'CANT'):
                raise ValueError('Archivo no es CAET/CANT vigente')
            if estado[1] != 'PROCESADO' or estado[2] != 'PROCESADO':
                raise ValueError('Archivo e insumo deben estar PROCESADOS')
            cur.execute('SELECT COUNT(*) FROM public.con_canje_detalle WHERE id_archivo=%s', (id_archivo,))
            total = cur.fetchone()[0]
            if total > limite:
                raise ValueError(f'Archivo excede limite seguro de {limite} filas')
            cur.execute('SELECT ' + ', '.join(CAMPOS) +
                        ' FROM public.con_canje_detalle d WHERE d.id_archivo=%s ORDER BY d.linea_origen',
                        (id_archivo,))
            datos = cur.fetchall()
    if len(datos) != total:
        raise RuntimeError('Cantidad de detalle cambio durante lectura; reintentar')
    partidas = []
    auditoria = []
    for registro in datos:
        fila = dict(zip((c.split('.')[-1] for c in CAMPOS), registro))
        if fila['tipo_archivo'] != estado[0]:
            raise RuntimeError('Tipo de detalle incompatible con archivo')
        nuevas, audit = transformar_fila(fila)
        partidas.extend(nuevas)
        auditoria.append(audit)
    resultado = agrupar_canje(partidas)
    return {'id_archivo': id_archivo, 'tipo_archivo': estado[0],
            'filas_fuente': total, 'partidas_f2': len(partidas),
            'resultado': resultado, 'auditoria': auditoria,
            'advertencia': 'Agrupacion preliminar. No acredita equivalencia Excel ni cuadre contable.'}
