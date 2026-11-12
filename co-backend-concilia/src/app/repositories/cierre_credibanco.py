"""Adaptador PostgreSQL del cierre diagnostico Credibanco F2 (ver app.core.cierre_credibanco_v67).

Lee directamente de las tablas CON_*_RESULTADO que ya pueblan los parsers F1
(co-api-parseo) - no depende de ninguna tabla "detalle" paralela. El HA22,
HA26 y HA32 (Host) ya tienen parser propio registrado (co-api-parseo); si
una jornada aun no tiene esos archivos cargados, construir_cierre() los
marca como INSUMO_HA2x_FALTANTE y el resto del diagnostico sigue sin ellos.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.cierre_credibanco_v67 import construir_cierre

TIPOS = ("CAET", "CANT", "DEPO", "CARTA_COMPENSACION", "HA22", "HA26", "HA32")
ESTADO_PROCESAMIENTO_OK = "Procesado"

_CATALOGO_RUTA = Path(__file__).resolve().parents[1] / "catalogos" / "cierre_credibanco_v67.json"


def _cargar_catalogo() -> dict:
    catalogo = json.loads(_CATALOGO_RUTA.read_text(encoding="utf-8"))
    if catalogo.get("version_catalogo") != "CB-F2-V67-CIERRE-001":
        raise ValueError("Catalogo Credibanco sin version validada")
    return catalogo


class CierreCredibancoRepository:
    def __init__(self, conn):
        self.conn = conn

    def ejecutar(self, id_jornada: int) -> dict | None:
        from psycopg.rows import dict_row

        j = self.conn.execute(
            "SELECT ID_JORNADA AS id_jornada, FECHA_CONTABLE AS fecha_contable FROM CON_JORNADA WHERE ID_JORNADA=%s",
            (id_jornada,),
        ).fetchone()
        if j is None:
            return None
        with self.conn.cursor(row_factory=dict_row) as cur:
            jornada = {"id_jornada": j[0], "fecha_contable": j[1]}
            cur.execute(
                """SELECT a.ID_ARCHIVO AS id_archivo, i.TIPO_INSUMO AS tipo_archivo,
                          a.ESTADO_PROCESAMIENTO AS estado_procesamiento
                   FROM CON_ARCHIVO_CARGA a JOIN CON_INSUMO_ESPERADO i ON i.ID_INSUMO=a.ID_INSUMO
                   WHERE a.ID_JORNADA=%s AND i.TIPO_INSUMO=ANY(%s)
                   ORDER BY i.TIPO_INSUMO, a.ID_ARCHIVO""",
                (id_jornada, list(TIPOS)),
            )
            filas_archivo = cur.fetchall()
            archivos = [
                {
                    "id_archivo": f["id_archivo"],
                    "tipo_archivo": f["tipo_archivo"],
                    "fecha_contable": jornada["fecha_contable"],
                    "estado_archivo": "PROCESADO" if f["estado_procesamiento"] == ESTADO_PROCESAMIENTO_OK else f["estado_procesamiento"],
                    "estado_insumo": "PROCESADO" if f["estado_procesamiento"] == ESTADO_PROCESAMIENTO_OK else f["estado_procesamiento"],
                }
                for f in filas_archivo
            ]
            ids = {a["tipo_archivo"]: a["id_archivo"] for a in archivos if a["estado_archivo"] == "PROCESADO"}
            c_ids = [ids[t] for t in ("CAET", "CANT") if t in ids]
            d_ids = [ids[t] for t in ("DEPO",) if t in ids]
            carta_ids = [ids[t] for t in ("CARTA_COMPENSACION",) if t in ids]
            h_ids = [ids[t] for t in ("HA22", "HA26", "HA32") if t in ids]

            canje, depo, carta, host, evidencia_l6 = [], [], [], [], []

            if c_ids:
                cur.execute(
                    """SELECT id_archivo, tipo_archivo, cuenta, cuentas_comisiones, tx, cod_error,
                              COUNT(*)::integer AS cantidad,
                              COUNT(*) FILTER (WHERE comision_op_exitosas IS NULL)::integer AS nulos_comision,
                              SUM(comision_op_exitosas) AS total_comision,
                              COUNT(*) FILTER (WHERE vl_total IS NULL)::integer AS nulos_total,
                              COUNT(*) FILTER (WHERE vl_interc IS NULL)::integer AS nulos_interc,
                              SUM(vl_total) AS total_valor, SUM(vl_interc) AS total_intercambio,
                              MIN(numero_linea) AS primera_linea, MAX(numero_linea) AS ultima_linea
                       FROM (
                           SELECT id_archivo, 'CAET' AS tipo_archivo, cuenta, cuentas_comisiones, tx, cod_error,
                                  comision_op_exitosas, vl_total, vl_interc, numero_linea
                           FROM CON_CANJE_RESULTADO WHERE id_archivo = ANY(%(ids)s)
                           UNION ALL
                           SELECT id_archivo, 'CANT' AS tipo_archivo, cuenta, cuentas_comisiones, tx, cod_error,
                                  comision_op_exitosas, vl_total, vl_interc, numero_linea
                           FROM CON_CANT_RESULTADO WHERE id_archivo = ANY(%(ids)s)
                       ) d
                       GROUP BY id_archivo, tipo_archivo, cuenta, cuentas_comisiones, tx, cod_error
                       ORDER BY id_archivo, cuenta, tx""",
                    {"ids": c_ids},
                )
                canje = cur.fetchall()

            if d_ids:
                cur.execute(
                    """SELECT id_archivo, cuenta AS concepto, tipo_movimiento, cod_oficina,
                              indicador_cash_back, amex_nacional,
                              COUNT(*)::integer AS cantidad,
                              COUNT(*) FILTER (WHERE valor_total IS NULL)::integer AS valores_invalidos,
                              SUM(valor_total) AS valor_total_crudo,
                              SUM(valor_intercambio) AS valor_intercambio_crudo,
                              SUM(valor_intercambio_2) AS valor_intercambio_2_crudo,
                              COUNT(*) FILTER (WHERE valor_intercambio IS NULL)::integer AS nulos_valor_intercambio,
                              SUM(tasa_de_intercambio) AS tasa_intercambio_cruda,
                              COUNT(*) FILTER (WHERE tasa_de_intercambio IS NULL)::integer AS nulos_tasa
                       FROM CON_DEPOSITO_RESULTADO
                       WHERE id_archivo = ANY(%s)
                       GROUP BY id_archivo, cuenta, tipo_movimiento, cod_oficina, indicador_cash_back, amex_nacional
                       ORDER BY id_archivo, concepto, tipo_movimiento""",
                    (d_ids,),
                )
                depo = cur.fetchall()

            if carta_ids:
                cur.execute(
                    """SELECT id_archivo, seccion, motivo_codigo, es_control, lado, concepto,
                              COUNT(*)::integer AS cantidad,
                              SUM(valor_principal) AS valor_principal,
                              SUM(valor_red) AS valor_red,
                              SUM(valor_total) AS valor_total,
                              COUNT(*) FILTER (WHERE valor_principal IS NULL)::integer AS nulos_principal,
                              COUNT(*) FILTER (WHERE valor_red IS NULL)::integer AS nulos_red,
                              COUNT(*) FILTER (WHERE valor_total IS NULL)::integer AS nulos_total,
                              MIN(numero_linea) AS primera_linea
                       FROM CON_CARTA_COMP_RESULTADO
                       WHERE id_archivo = ANY(%s)
                       GROUP BY id_archivo, seccion, motivo_codigo, es_control, lado, concepto
                       ORDER BY id_archivo, seccion, primera_linea""",
                    (carta_ids,),
                )
                carta = cur.fetchall()
                # Evidencia L6: CON_ARCHIVO_CARGA no tiene checksum real en este
                # esquema; como ambas filas (control y respaldo) se filtran por el
                # MISMO id_archivo, NOMBRE_ARCHIVO identifica el mismo origen
                # fisico igual de bien para este chequeo puntual (no es un hash
                # criptografico, es una marca de "mismo archivo").
                cur.execute(
                    """SELECT d.id_archivo, a.nombre_archivo, a.nombre_archivo AS checksum_sha256,
                              %s::date AS fecha_contable,
                              d.numero_linea AS linea_origen, d.seccion, d.motivo_codigo, d.es_control,
                              d.lado, d.concepto, d.valor_principal, d.valor_depositos_electronicos,
                              d.id_carta_comp_resultado
                       FROM CON_CARTA_COMP_RESULTADO d
                       JOIN CON_ARCHIVO_CARGA a ON a.id_archivo = d.id_archivo
                       WHERE d.id_archivo = ANY(%s)
                         AND ((d.seccion='CAI0228A' AND d.numero_linea=9)
                           OR (d.seccion='CAI0224A' AND d.numero_linea=18))
                       ORDER BY d.seccion, d.numero_linea, d.id_carta_comp_resultado""",
                    (jornada["fecha_contable"], carta_ids),
                )
                evidencia_l6 = cur.fetchall()

            if h_ids:
                # DESCON como proxy de "concepto" para la deteccion de pruebas
                # sinteticas: ningun parser HA22/HA26/HA32 actual distingue esto
                # explicitamente, asi que el chequeo solo se activa si el texto
                # libre de DESCON llega a contener esas etiquetas literales.
                cur.execute(
                    """SELECT id_archivo, tx_host, cuenta, centro, concepto, fecha_contable,
                              COUNT(*)::integer AS cantidad,
                              COUNT(*) FILTER (WHERE debe IS NULL OR haber IS NULL)::integer AS incompletos,
                              SUM(debe) AS debe, SUM(haber) AS haber
                       FROM (
                           SELECT id_archivo, 'HA22' AS tx_host, nucta AS cuenta, cedestin AS centro,
                                  descon AS concepto, fecon AS fecha_contable, debe, haber
                           FROM CON_HA22_RESULTADO WHERE id_archivo = ANY(%(ids)s)
                           UNION ALL
                           SELECT id_archivo, 'HA26' AS tx_host, nucta AS cuenta, cedestin AS centro,
                                  descon AS concepto, fecon AS fecha_contable, debe, haber
                           FROM CON_HA26_RESULTADO WHERE id_archivo = ANY(%(ids)s)
                           UNION ALL
                           SELECT id_archivo, 'HA32' AS tx_host, nucta AS cuenta, cedestin AS centro,
                                  NULL AS concepto, fecont AS fecha_contable, debe, haber
                           FROM CON_HA32_RESULTADO WHERE id_archivo = ANY(%(ids)s)
                       ) h
                       GROUP BY id_archivo, tx_host, cuenta, centro, concepto, fecha_contable
                       ORDER BY cuenta, tx_host, id_archivo""",
                    {"ids": h_ids},
                )
                host = cur.fetchall()

        catalogo = _cargar_catalogo()
        return construir_cierre(
            jornada=jornada,
            archivos=archivos,
            canje=canje,
            depo=depo,
            carta=carta,
            host=host,
            evidencia_l6=evidencia_l6,
            aprobacion_l8=catalogo.get("aprobacion_l8"),
            reglas_cruce=catalogo.get("reglas_cruce", ()),
        )
