"""Adaptador PostgreSQL para cierre diagnostico Credibanco F2.

Consulta agregados de F1 en transaccion consistente de solo lectura. No accede
al sistema de archivos ni a plantillas XLSX durante la ejecucion.
"""
from __future__ import annotations

import json
from pathlib import Path
from app.services.fase2.cierre_credibanco_v67 import construir_cierre


def ejecutar(id_jornada: int, conexion_factory=None, *, reglas_diagnostico=None) -> dict:
    if type(id_jornada) is not int or id_jornada <= 0:
        raise ValueError("id_jornada invalido")
    from psycopg.rows import dict_row
    if conexion_factory is None:
        from app.repositories.database import connection
        conexion_factory = connection
    with conexion_factory() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cur.execute("""
                SELECT id_jornada, fecha_contable, estado
                FROM public.con_jornada WHERE id_jornada=%s
            """, (id_jornada,))
            j = cur.fetchone()
            if j is None:
                return None
            cur.execute("""
                SELECT a.id_archivo, a.tipo_archivo, a.fecha_contable,
                       a.estado AS estado_archivo, i.estado AS estado_insumo
                FROM public.con_insumo_esperado i
                JOIN public.con_archivo_carga a
                  ON a.id_archivo=i.id_archivo AND a.tipo_archivo=i.tipo_insumo
                WHERE i.id_jornada=%s AND a.tipo_archivo IN
                ('CAET','CANT','DEPO','CARTA_COMPENSACION','HA22','HA26','HA32')
                ORDER BY a.tipo_archivo,a.id_archivo
            """, (id_jornada,))
            archivos = cur.fetchall()
            ids = {a["tipo_archivo"]: a["id_archivo"] for a in archivos
                   if a["estado_archivo"] == "PROCESADO" and a["estado_insumo"] == "PROCESADO"
                   and str(a["fecha_contable"]) == str(j["fecha_contable"])
                   and sum(1 for x in archivos if x["tipo_archivo"] == a["tipo_archivo"]) == 1}
            c_ids = [ids[t] for t in ("CAET", "CANT") if t in ids]
            d_ids = [ids[t] for t in ("DEPO",) if t in ids]
            carta_ids = [ids[t] for t in ("CARTA_COMPENSACION",) if t in ids]
            h_ids = [ids[t] for t in ("HA22", "HA26", "HA32") if t in ids]
            canje, depo, carta, host = [], [], [], []
            evidencia_l6 = []
            if c_ids:
                cur.execute("""
                    SELECT d.id_archivo, d.tipo_archivo, d.fecha_contable, d.cuenta,
                           d.cuentas_comisiones, d.tx, d.cod_error,
                           COUNT(*)::integer AS cantidad,
                           COUNT(*) FILTER (WHERE d.comision_op_exitosas IS NULL)::integer AS nulos_comision,
                           SUM(d.comision_op_exitosas) AS total_comision,
                           COUNT(*) FILTER (WHERE d.vl_total IS NULL)::integer AS nulos_total,
                           COUNT(*) FILTER (WHERE d.vl_interc IS NULL)::integer AS nulos_interc,
                           SUM(d.vl_total) AS total_valor,
                           SUM(d.vl_interc) AS total_intercambio,
                           MIN(d.linea_origen) AS primera_linea,
                           MAX(d.linea_origen) AS ultima_linea
                    FROM public.con_canje_detalle d
                    WHERE d.id_archivo = ANY(%s)
                    GROUP BY d.id_archivo,d.tipo_archivo,d.fecha_contable,d.cuenta,
                             d.cuentas_comisiones,d.tx,d.cod_error
                    ORDER BY d.id_archivo, d.cuenta, d.tx
                """, (c_ids,))
                canje = cur.fetchall()
            if d_ids:
                cur.execute("""
                    SELECT d.id_archivo, d.fecha_contable, d.cuenta AS concepto, d.tipo_movimiento,
                           d.cod_oficina, d.indicador_cash_back, d.amex_nacional,
                           COUNT(*)::integer AS cantidad,
                           COUNT(*) FILTER (WHERE d.valor_total IS NULL OR
                                  BTRIM(d.valor_total) !~ '^[0-9]+$')::integer AS valores_invalidos,
                           SUM(CASE WHEN BTRIM(d.valor_total) ~ '^[0-9]+$'
                               THEN BTRIM(d.valor_total)::numeric ELSE NULL END) AS valor_total_crudo,
                           SUM(CASE WHEN BTRIM(d.valor_intercambio) ~ '^[0-9]+(?:\.[0-9]+)?$' THEN BTRIM(d.valor_intercambio)::numeric ELSE NULL END) AS valor_intercambio_crudo,
                           COUNT(*) FILTER (WHERE d.valor_intercambio IS NULL OR BTRIM(d.valor_intercambio) !~ '^[0-9]+(?:\.[0-9]+)?$')::integer AS nulos_valor_intercambio,
                           SUM(CASE
                               WHEN BTRIM(d.valor_intercambio_2) ~ '^[0-9]+(?:\.[0-9]+)?$'
                               THEN BTRIM(d.valor_intercambio_2)::numeric
                               ELSE NULL
                           END) AS valor_intercambio_2_crudo,
                           COUNT(*) FILTER (
                               WHERE d.valor_intercambio_2 IS NULL
                                  OR BTRIM(d.valor_intercambio_2) !~ '^[0-9]+(?:\.[0-9]+)?$'
                           )::integer AS nulos_valor_intercambio_2,
                           SUM(d.tasa_de_intercambio) AS tasa_intercambio_cruda,
                           COUNT(*) FILTER (WHERE d.tasa_de_intercambio IS NULL)::integer AS nulos_tasa
                    FROM public.con_depo_detalle d
                    WHERE d.id_archivo = ANY(%s)
                    GROUP BY d.id_archivo,d.fecha_contable,d.cuenta,d.tipo_movimiento,
                             d.cod_oficina,d.indicador_cash_back,d.amex_nacional
                    ORDER BY d.id_archivo,d.cuenta,d.tipo_movimiento,d.cod_oficina,
                             d.indicador_cash_back,d.amex_nacional
                """, (d_ids,))
                depo = cur.fetchall()
            if carta_ids:
                cur.execute("""
                    SELECT d.id_archivo, d.fecha_contable, d.seccion, d.motivo_codigo,
                           d.es_control, d.lado, d.concepto,
                           COUNT(*)::integer AS cantidad,
                           SUM(d.valor_principal) AS valor_principal,
                           SUM(d.valor_red) AS valor_red,
                           SUM(d.valor_total) AS valor_total,
                           COUNT(*) FILTER (WHERE d.valor_principal IS NULL)::integer AS nulos_principal,
                           COUNT(*) FILTER (WHERE d.valor_red IS NULL)::integer AS nulos_red,
                           COUNT(*) FILTER (WHERE d.valor_total IS NULL)::integer AS nulos_total,
                           MIN(d.linea_origen) AS primera_linea
                    FROM public.con_carta_compensacion_detalle d
                    WHERE d.id_archivo = ANY(%s)
                    GROUP BY d.id_archivo,d.fecha_contable,d.seccion,d.motivo_codigo,d.es_control,d.lado,d.concepto
                    ORDER BY d.id_archivo,d.seccion,primera_linea
                """, (carta_ids,))
                carta = cur.fetchall()
                # Evidencia L6: conservar filas individuales y trazables.
                # No agregar ni homologar importes en esta consulta.
                cur.execute("""
                    SELECT d.id_archivo, a.nombre_archivo, a.checksum_sha256,
                           d.fecha_contable, d.linea_origen, d.seccion,
                           d.motivo_codigo, d.es_control, d.lado, d.concepto,
                           d.valor_principal, d.valor_depositos_electronicos
                    FROM public.con_carta_compensacion_detalle d
                    JOIN public.con_archivo_carga a
                      ON a.id_archivo = d.id_archivo
                    WHERE d.id_archivo = ANY(%s)
                      AND (
                            (d.seccion = 'CAI0228A' AND d.linea_origen = 9)
                         OR (d.seccion = 'CAI0224A' AND d.linea_origen = 18)
                      )
                    ORDER BY d.seccion, d.linea_origen, d.id_carta_detalle
                """, (carta_ids,))
                evidencia_l6 = cur.fetchall()
            if h_ids:
                cur.execute("""
                    SELECT h.id_archivo, h.tx_host, h.cuenta, h.centro,
                           h.concepto, h.fecha_contable,
                           COUNT(*)::integer AS cantidad,
                           COUNT(*) FILTER (WHERE h.valor_debe IS NULL OR
                                                  h.valor_haber IS NULL)::integer AS incompletos,
                           SUM(h.valor_debe) AS debe, SUM(h.valor_haber) AS haber
                    FROM public.con_host_resultado h
                    WHERE h.id_archivo = ANY(%s)
                    GROUP BY h.id_archivo,h.tx_host,h.cuenta,h.centro,
                             h.concepto,h.fecha_contable
                    ORDER BY h.cuenta,h.tx_host,h.id_archivo
                """, (h_ids,))
                host = cur.fetchall()
    catalogo_ruta = Path(__file__).resolve().parents[2] / "catalogos" / "cierre_credibanco_v67.json"
    catalogo = json.loads(catalogo_ruta.read_text(encoding="utf-8"))
    if catalogo.get("version_catalogo") != "CB-F2-V67-CIERRE-001":
        raise ValueError("Catalogo Credibanco sin version validada")
    resultado = construir_cierre(jornada=j, archivos=archivos, canje=canje,
                           depo=depo, carta=carta, host=host,
                           evidencia_l6=evidencia_l6,
                           aprobacion_l8=catalogo.get("aprobacion_l8"),
                           reglas_cruce=(reglas_diagnostico if reglas_diagnostico is not None else catalogo.get("reglas_cruce", ())))
    if reglas_diagnostico is not None:
        # Evidencia de origen, tomada del mismo snapshot PostgreSQL que el cierre.
        # No se convierte a cuenta Host salvo mediante la regla explicita de prueba.
        from decimal import Decimal
        evidencias = []
        for regla in reglas_diagnostico:
            if regla.get("insumo") not in ("CAET", "CANT"):
                continue
            for fila in canje:
                if (fila["id_archivo"] == ids.get(regla["insumo"])
                    and fila["cuenta"] == regla.get("concepto")
                    and fila["tx"] == regla.get("tx")
                    and fila["cod_error"] == "00"):
                    evidencias.append({
                        "insumo": regla["insumo"], "id_archivo": fila["id_archivo"],
                        "cuenta": fila["cuenta"], "tx": fila["tx"],
                        "cod_error": fila["cod_error"], "cantidad": fila["cantidad"],
                        "vl_total": str(fila["total_valor"]) if fila["nulos_total"] == 0 and fila["total_valor"] is not None else None,
                        "vl_interc": str(fila["total_intercambio"]) if fila["nulos_interc"] == 0 and fila["total_intercambio"] is not None else None,
                        "nulos_total": fila["nulos_total"], "nulos_interc": fila["nulos_interc"],
                        "primera_linea": fila["primera_linea"], "ultima_linea": fila["ultima_linea"],
                    })
        resultado["evidencia_monetaria_regla_prueba"] = evidencias
    return resultado

