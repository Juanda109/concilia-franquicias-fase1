"""Adaptador PostgreSQL de la conciliacion VISA (ver app.core.conciliacion_visa).

Lee CON_VSS_REPORTE/CON_VSS_DETALLE, CON_ISS_RESULTADO y CON_HA2x_RESULTADO, que
ya pueblan los parsers F1 (co-api-parseo), y las capturas manuales de la
liquidacion en CON_VISA_CAPTURA_MANUAL. Las capturas nunca se sobrescriben: cada
cambio inserta una version nueva y se usa la ultima de cada campo.
"""
from __future__ import annotations

from app.core.conciliacion_visa import CUENTAS_VISA, construir_conciliacion_visa, validar_captura
from app.core.host_por_cuenta import FUENTES_HOST
from app.repositories.cierre_redeban import SQL_HOST_POR_CUENTA, _SQL_ARCHIVOS, _cargar_inventario_host


class ConciliacionVisaRepository:
    def __init__(self, conn):
        self.conn = conn

    def _jornada(self, id_jornada: int, *, bloquear: bool = False):
        sql = "SELECT ID_JORNADA, FECHA_CONTABLE FROM CON_JORNADA WHERE ID_JORNADA=%s"
        return self.conn.execute(sql + (" FOR UPDATE" if bloquear else ""), (id_jornada,)).fetchone()

    def ejecutar(self, id_jornada: int) -> dict | None:
        from psycopg.rows import dict_row

        j = self._jornada(id_jornada)
        if j is None:
            return None
        jornada = {"id_jornada": j[0], "fecha_contable": j[1]}

        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_SQL_ARCHIVOS, (id_jornada, ["VSS", "ISS", *FUENTES_HOST]))
            archivos: dict[str, list[int]] = {}
            for f in cur.fetchall():
                archivos.setdefault(f["tipo"], []).append(f["id_archivo"])

            reportes, detalle = [], []
            if archivos.get("VSS"):
                cur.execute(
                    """SELECT id_vss_reporte, id_archivo, report_id, reporting_for, funds_xfer_entity,
                              proc_date, settlement_currency
                       FROM CON_VSS_REPORTE WHERE id_archivo = ANY(%s) ORDER BY id_vss_reporte""",
                    (archivos["VSS"],),
                )
                reportes = cur.fetchall()
                if reportes:
                    cur.execute(
                        """SELECT id_vss_reporte, numero_linea, numero_pagina, clearing_currency, seccion,
                                  concepto, subtipo, clearing_amount, credit_amount, debit_amount,
                                  total_amount, naturaleza
                           FROM CON_VSS_DETALLE WHERE id_vss_reporte = ANY(%s)
                           ORDER BY id_vss_reporte, numero_linea""",
                        ([r["id_vss_reporte"] for r in reportes],),
                    )
                    detalle = cur.fetchall()

            iss = []
            if archivos.get("ISS"):
                cur.execute(
                    """SELECT id_archivo, numero_linea, ftsre, nombre, moneda, monto_neto, naturaleza, fecha_valor
                       FROM CON_ISS_RESULTADO WHERE id_archivo = ANY(%s) ORDER BY id_archivo, numero_linea""",
                    (archivos["ISS"],),
                )
                iss = cur.fetchall()

            ids_host = [i for t in FUENTES_HOST for i in archivos.get(t, [])]
            host_filas = []
            if ids_host:
                cur.execute(SQL_HOST_POR_CUENTA, {"ids": ids_host, "cuentas": list(CUENTAS_VISA)})
                host_filas = cur.fetchall()

            capturas = self._capturas_vigentes(cur, id_jornada)

        return construir_conciliacion_visa(
            jornada=jornada, vss_reportes=reportes, vss_detalle=detalle, iss_filas=iss, capturas=capturas,
            host_filas=host_filas, fuentes_procesadas=[t for t in FUENTES_HOST if archivos.get(t)],
            inventario_host=_cargar_inventario_host(),
        )

    @staticmethod
    def _capturas_vigentes(cur, id_jornada: int) -> dict[str, dict]:
        cur.execute(
            """SELECT DISTINCT ON (campo) campo, valor, version, usuario, fecha_creacion AS fecha
               FROM CON_VISA_CAPTURA_MANUAL WHERE id_jornada=%s
               ORDER BY campo, version DESC""",
            (id_jornada,),
        )
        return {f["campo"]: f for f in cur.fetchall()}

    def guardar_capturas(self, id_jornada: int, valores: dict, usuario: dict | None,
                         observacion: str | None) -> bool:
        """Inserta una version nueva por campo. False si la jornada no existe.
        Lanza CapturaInvalida (app.core.conciliacion_visa) si algun valor no es valido."""
        normalizados = validar_captura(valores)
        # Bloquea la jornada: dos capturas simultaneas no pueden calcular la misma version.
        if self._jornada(id_jornada, bloquear=True) is None:
            return False
        quien = (usuario or {}).get("email") or (usuario or {}).get("sub") or "desconocido"
        for campo, valor in normalizados.items():
            self.conn.execute(
                """INSERT INTO CON_VISA_CAPTURA_MANUAL (ID_JORNADA, CAMPO, VALOR, VERSION, USUARIO, OBSERVACION)
                   SELECT %s, %s, %s, COALESCE(MAX(VERSION), 0) + 1, %s, %s
                   FROM CON_VISA_CAPTURA_MANUAL WHERE ID_JORNADA=%s AND CAMPO=%s""",
                (id_jornada, campo, valor, quien, observacion, id_jornada, campo),
            )
        return True
