"""Lectura diagnostica Host. No certifica ni homologa conciliaciones."""
from decimal import Decimal
from app.repositories.database import connection

FUENTES = ("HA22", "HA26", "HA32")

def obtener_diagnostico_host(id_jornada: int) -> dict:
    if not isinstance(id_jornada, int) or id_jornada <= 0:
        raise ValueError("id_jornada invalido")
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("""
                SELECT h.tx_host, h.cuenta, h.centro, h.id_archivo,
                       COUNT(*) AS cantidad,
                       SUM(h.valor_debe) AS debe,
                       SUM(h.valor_haber) AS haber,
                       SUM(h.valor_normalizado) AS neto,
                       ARRAY_AGG(h.linea_origen ORDER BY h.linea_origen) AS lineas,
                       ARRAY_AGG(DISTINCT h.concepto) AS conceptos
                FROM con_host_resultado h
                WHERE h.tx_host IN ('HA22','HA26','HA32')
                  AND EXISTS (
                      SELECT 1 FROM con_insumo_esperado i
                      WHERE i.id_archivo=h.id_archivo AND i.id_jornada=%s
                  )
                GROUP BY h.tx_host,h.cuenta,h.centro,h.id_archivo
                ORDER BY h.cuenta,h.tx_host,h.centro,h.id_archivo
            """, (id_jornada,))
            registros = cur.fetchall()
    filas=[]
    for fuente,cuenta,centro,archivo,cantidad,debe,haber,neto,lineas,conceptos in registros:
        conceptos=[x for x in (conceptos or []) if x]
        sintetico=any('PRUEBA SINTETICA' in x.upper() for x in conceptos)
        filas.append(dict(fuente=fuente,cuenta=cuenta,centro=centro,id_archivo=archivo,
            cantidad=cantidad,debe=str(debe) if debe is not None else None,
            haber=str(haber) if haber is not None else None,
            neto_diagnostico=str(neto) if neto is not None else None,
            lineas_origen=lineas,conceptos=conceptos,
            evidencia_sintetica_explicita=sintetico,
            estado='DIAGNOSTICO_NO_HOMOLOGADO'))
    return dict(id_jornada=id_jornada,certificado=False,
        estado='HOST_DIAGNOSTICO_SIN_HOMOLOGACION',
        advertencia='No sumar fuentes HA entre si ni calcular diferencia contable.',
        filas=filas)
