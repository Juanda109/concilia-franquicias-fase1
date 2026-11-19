"""INC021: consulta Host por pares autorizados, solo lectura."""

import re
from collections import Counter

from app.repositories.database import connection
from app.services.fase2.elegibilidad_host_inc021 import clasificar_movimiento
from app.services.fase2.catalogo_host_cuenta_inc021 import pares_para_cuentas

FUENTES = ('HA22', 'HA26', 'HA32')
_MARCADOR_PRUEBA = re.compile(r'(?<![A-Z0-9])(?:PRUEBA|SINTETIC[AO]?)(?![A-Z0-9])', re.IGNORECASE)


def archivo_de_prueba(nombre):
    """Marcadores delimitados en el nombre, sin inferir origen real por ausencia."""
    return bool(_MARCADOR_PRUEBA.search(str(nombre or '')))


def consultar_elegibilidad_host(id_jornada, cuentas):
    if type(id_jornada) is not int or id_jornada <= 0:
        raise ValueError('Jornada invalida')
    pares = pares_para_cuentas(cuentas)
    # Dos arreglos parametrizados forman una relacion de pares, no producto cartesiano.
    fuentes = [f for f, _ in pares]
    cuentas_pares = [c for _, c in pares]
    sql = """
        WITH pares(tx_host, cuenta) AS (
            SELECT * FROM unnest(%s::text[], %s::text[])
        )
        SELECT
            h.id_host_resultado, i.id_jornada, h.id_archivo,
            h.fecha_contable, h.tx_host, h.cuenta, h.centro,
            h.referencia, h.concepto, h.valor_debe, h.valor_haber,
            h.valor_normalizado, h.linea_origen, h.correlation_id,
            a.nombre_archivo, a.proceso_origen, a.estado AS estado_archivo,
            a.checksum_sha256
        FROM public.con_host_resultado h
        JOIN public.con_insumo_esperado i
          ON i.id_archivo = h.id_archivo AND i.tipo_insumo = h.tx_host
        JOIN public.con_jornada j ON j.id_jornada = i.id_jornada
        JOIN public.con_archivo_carga a ON a.id_archivo = h.id_archivo
        JOIN pares p ON p.tx_host = h.tx_host AND p.cuenta = h.cuenta
        WHERE i.id_jornada = %s
          AND h.fecha_contable = j.fecha_contable
          AND a.tipo_archivo = h.tx_host
        ORDER BY h.tx_host, h.cuenta, h.linea_origen, h.id_host_resultado
    """
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute(sql, (fuentes, cuentas_pares, id_jornada))
            columnas = [d.name for d in cur.description]
            filas = [dict(zip(columnas, fila)) for fila in cur.fetchall()]

    movimientos = []
    for fila in filas:
        individual = clasificar_movimiento(fila, procedencia_verificada=False)
        sint_archivo = archivo_de_prueba(fila['nombre_archivo'])
        estado = 'SINTETICO' if sint_archivo else individual.estado
        motivo = 'MARCADOR_PRUEBA_ARCHIVO' if sint_archivo else individual.motivo
        movimientos.append({
            'id_host_resultado': fila['id_host_resultado'],
            'id_jornada': fila['id_jornada'],
            'id_archivo': fila['id_archivo'],
            'fecha_contable': str(fila['fecha_contable']),
            'tx_host': fila['tx_host'], 'cuenta': fila['cuenta'],
            'centro': fila['centro'], 'referencia': fila['referencia'],
            'concepto': fila['concepto'], 'linea_origen': fila['linea_origen'],
            'correlation_id': fila['correlation_id'],
            'nombre_archivo': fila['nombre_archivo'],
            'proceso_origen': fila['proceso_origen'],
            'estado_archivo': fila['estado_archivo'],
            'checksum_sha256': str(fila['checksum_sha256']).strip() if fila['checksum_sha256'] is not None else None,
            'valor_debe': str(fila['valor_debe']) if fila['valor_debe'] is not None else None,
            'valor_haber': str(fila['valor_haber']) if fila['valor_haber'] is not None else None,
            'valor_normalizado': str(fila['valor_normalizado']) if fila['valor_normalizado'] is not None else None,
            'estado': estado, 'motivo': motivo, 'puede_homologar': False,
        })
    resumen = {}
    for fuente in FUENTES:
        estados = Counter(m['estado'] for m in movimientos if m['tx_host'] == fuente)
        resumen[fuente] = {
            'movimientos': sum(estados.values()),
            'sinteticos': estados['SINTETICO'],
            'origen_no_verificado': estados['ORIGEN_NO_VERIFICADO'],
            'elegibles_revision': estados['ELEGIBLE_REVISION'],
        }
    return {
        'incremento': 'INC021', 'id_jornada': id_jornada,
        'modo': 'DIAGNOSTICO_SOLO_LECTURA', 'estado': 'SIN_HOMOLOGACION',
        'pares_consultados': [list(par) for par in pares],
        'movimientos': movimientos, 'resumen_por_fuente': resumen,
        'total_movimientos': len(movimientos),
        'certificado': False, 'conciliado_host': False,
        'homologado_contablemente': False,
    }
