"""Adaptador PostgreSQL del cuadre Redeban (ver app.core.cuadre_redeban_estructura).

Lee CON_PMD_RESULTADO y CON_HA2x_RESULTADO, que ya pueblan los parsers F1
(co-api-parseo). La homologacion codigo PMD -> cuenta sale de la hoja ESTRUCTURA
de la plantilla de cuadre Redeban (catalogos/estructura_redeban.json); las
fuentes Host que se consultan por cuenta, del inventario cuentas_redeban_host.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.cuadre_redeban_estructura import SIN_CUENTA, construir_cuadre_redeban

_CATALOGOS = Path(__file__).resolve().parents[1] / "catalogos"


def _cargar_estructura() -> dict:
    catalogo = json.loads((_CATALOGOS / "estructura_redeban.json").read_text(encoding="utf-8"))
    if catalogo.get("version_catalogo") != "REDEBAN-ESTRUCTURA-V1":
        raise ValueError("Catalogo ESTRUCTURA Redeban sin version validada")
    return catalogo


def _cargar_inventario_host() -> list[dict]:
    catalogo = json.loads((_CATALOGOS / "cuentas_redeban_host.json").read_text(encoding="utf-8"))
    if catalogo.get("version_catalogo") != "REDEBAN-CUENTAS-HOST-V1":
        raise ValueError("Inventario de consultas Host sin version validada")
    return catalogo["cuentas"]


_SQL_ARCHIVOS = """SELECT i.TIPO_INSUMO AS tipo, a.ID_ARCHIVO AS id_archivo
                   FROM CON_ARCHIVO_CARGA a JOIN CON_INSUMO_ESPERADO i ON i.ID_INSUMO=a.ID_INSUMO
                   WHERE a.ID_JORNADA=%s AND i.TIPO_INSUMO = ANY(%s) AND a.ESTADO_PROCESAMIENTO='Procesado'
                   ORDER BY a.ID_ARCHIVO"""


# Movimientos Host centro 17 de las cuentas pedidas; cada fuente queda marcada en tx_host.
SQL_HOST_POR_CUENTA = """SELECT id_archivo, tx_host, cuenta, fecha_contable, debe, haber
                         FROM (
                             SELECT id_archivo, 'HA22' AS tx_host, nucta AS cuenta, cedestin AS centro,
                                    fecon AS fecha_contable, debe, haber
                             FROM CON_HA22_RESULTADO WHERE id_archivo = ANY(%(ids)s)
                             UNION ALL
                             SELECT id_archivo, 'HA26', nucta, cedestin, fecon, debe, haber
                             FROM CON_HA26_RESULTADO WHERE id_archivo = ANY(%(ids)s)
                             UNION ALL
                             SELECT id_archivo, 'HA32', nucta, cedestin, fecont, debe, haber
                             FROM CON_HA32_RESULTADO WHERE id_archivo = ANY(%(ids)s)
                         ) h
                         WHERE cuenta = ANY(%(cuentas)s)
                           -- CEDESTIN llega con punto final en algunos HA22/26/32 ("17." en vez de "17")
                           AND TRIM(TRAILING '.' FROM centro) IN ('17', '0017')"""


class CierreRedebanRepository:
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
        jornada = {"id_jornada": j[0], "fecha_contable": j[1]}
        estructura = _cargar_estructura()
        columnas = estructura["columnas"]
        cuentas = sorted({dict(zip(columnas, f))["cuenta"] for f in estructura["filas"]} - set(SIN_CUENTA))

        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_SQL_ARCHIVOS, (id_jornada, ["PMD", "HA22", "HA26", "HA32"]))
            archivos: dict[str, list[int]] = {}
            for f in cur.fetchall():
                archivos.setdefault(f["tipo"], []).append(f["id_archivo"])

            pmd_filas: list[dict] = []
            if archivos.get("PMD"):
                cur.execute(
                    """SELECT id_archivo, numero_linea, producto_servicio, nivel,
                              (producto_servicio ILIKE 'TOTAL PRODUCTOS PMD%%') AS es_control,
                              debito_cantidad, debito_valor, debito_comision_intercambio,
                              debito_comision_admin, debito_neto,
                              credito_cantidad, credito_valor, credito_comision_intercambio,
                              credito_comision_admin, credito_neto, total
                       FROM CON_PMD_RESULTADO
                       WHERE id_archivo = ANY(%s)
                       ORDER BY numero_linea""",
                    (archivos["PMD"],),
                )
                pmd_filas = [
                    {
                        "id_archivo": f["id_archivo"],
                        "numero_linea": f["numero_linea"],
                        "PRODUCTO_SERVICIO": f["producto_servicio"],
                        "NIVEL": f["nivel"],
                        "ES_CONTROL": f["es_control"],
                        "DEBITO_CANTIDAD": f["debito_cantidad"],
                        "DEBITO_VALOR": f["debito_valor"],
                        "DEBITO_COMISION_INTERCAMBIO": f["debito_comision_intercambio"],
                        "DEBITO_COMISION_ADMIN": f["debito_comision_admin"],
                        "DEBITO_NETO": f["debito_neto"],
                        "CREDITO_CANTIDAD": f["credito_cantidad"],
                        "CREDITO_VALOR": f["credito_valor"],
                        "CREDITO_COMISION_INTERCAMBIO": f["credito_comision_intercambio"],
                        "CREDITO_COMISION_ADMIN": f["credito_comision_admin"],
                        "CREDITO_NETO": f["credito_neto"],
                        "TOTAL": f["total"],
                    }
                    for f in cur.fetchall()
                ]

            ids_host = [i for t in ("HA22", "HA26", "HA32") for i in archivos.get(t, [])]
            host_filas: list[dict] = []
            if ids_host:
                cur.execute(SQL_HOST_POR_CUENTA, {"ids": ids_host, "cuentas": cuentas})
                host_filas = cur.fetchall()

        return construir_cuadre_redeban(
            jornada=jornada,
            catalogo=estructura,
            pmd_filas=pmd_filas,
            host_filas=host_filas,
            fuentes_procesadas=[t for t in ("HA22", "HA26", "HA32") if archivos.get(t)],
            inventario_host=_cargar_inventario_host(),
        )
