from datetime import date
from decimal import Decimal, InvalidOperation

from app.repositories.database import connection
from app.services.fase2.integracion_vss_visa_inc010 import (
    diagnosticar_vss110,
)


class EvidenciaVisaInconsistente(ValueError):
    pass


def consultar_evidencia_visa(id_jornada: int) -> dict:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")

            cur.execute("""
                SELECT fecha_contable
                FROM public.con_jornada
                WHERE id_jornada = %s
            """, (id_jornada,))

            fila = cur.fetchone()

            if fila is None:
                raise LookupError("Jornada inexistente")

            fecha = fila[0]

            cur.execute("""
                SELECT d.id_detalle, d.id_archivo, d.reporte,
                       d.pagina, d.moneda_liquidacion,
                       d.moneda_compensacion, d.fecha_reporte,
                       d.concepto, d.valores, d.signos,
                       d.texto_original
                FROM public.con_vss_detalle d
                JOIN public.con_archivo_carga a
                  ON a.id_archivo = d.id_archivo
                WHERE d.fecha_contable = %s
                  AND a.fecha_contable = %s
                  AND d.reporte = 'VSS-110'
                  AND EXISTS (
                      SELECT 1
                      FROM public.con_insumo_esperado i
                      WHERE i.id_jornada = %s
                        AND i.id_archivo = d.id_archivo
                        AND i.tipo_insumo = 'VSS'
                  )
                ORDER BY d.id_detalle
            """, (fecha, fecha, id_jornada))

            registros = cur.fetchall()

    if not registros:
        return {
            "id_jornada": id_jornada,
            "fecha_contable": fecha.isoformat(),
            "estado": "SIN_EVIDENCIA_VSS",
            "certificado": False,
            "conciliado_host": False,
            "evidencia": None,
        }

    if len(registros) != 1:
        raise EvidenciaVisaInconsistente(
            "Se esperaba un registro VSS-110 unico"
        )

    (id_detalle, id_archivo, reporte, pagina,
     moneda_liq, moneda_comp, fecha_rep,
     concepto, valores, signos, texto_original) = registros[0]

    if concepto != "SIMULATED NET SETTLEMENT":
        raise EvidenciaVisaInconsistente(
            "Concepto VSS no reconocido"
        )

    if (
        not isinstance(valores, list)
        or not isinstance(signos, list)
        or len(valores) != 1
        or len(signos) != 1
    ):
        raise EvidenciaVisaInconsistente(
            "Operandos VSS incompletos"
        )

    try:
        esperado = Decimal(str(valores[0]))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise EvidenciaVisaInconsistente(
            "Importe persistido invalido"
        ) from exc

    if (
        not esperado.is_finite()
        or esperado < 0
        or esperado.as_tuple().exponent < -2
    ):
        raise EvidenciaVisaInconsistente(
            "Importe persistido fuera de formato"
        )

    texto = (
        f"REPORT ID: {reporte} PAGE: {pagina}\n"
        f"SETTLEMENT CURRENCY: {moneda_liq}\n"
        f"CLEARING CURRENCY: {moneda_comp}\n"
        f"REPORT DATE: {fecha_rep}\n"
        f"{texto_original}\n"
        "END OF VSS-110\n"
    )

    try:
        resultado = diagnosticar_vss110(
            texto,
            id_jornada=id_jornada,
            fecha_contable=fecha,
        )
    except ValueError as exc:
        raise EvidenciaVisaInconsistente(
            "Texto VSS incompatible"
        ) from exc

    if (
        resultado["importe_observado"] is None
        or Decimal(resultado["importe_observado"]) != esperado
        or resultado["signo_observado"] != signos[0]
    ):
        raise EvidenciaVisaInconsistente(
            "Paridad VSS persistida no coincide"
        )

    return {
        "id_jornada": id_jornada,
        "fecha_contable": fecha.isoformat(),
        "estado": resultado["estado"],
        "certificado": False,
        "conciliado_host": False,
        "evidencia": {
            "id_detalle": id_detalle,
            "id_archivo": id_archivo,
            "reporte": reporte,
            "concepto": concepto,
            "moneda_liquidacion": moneda_liq,
            "moneda_compensacion": moneda_comp,
            "importe_observado": resultado["importe_observado"],
            "signo_observado": resultado["signo_observado"],
            "neto_observado": resultado["neto_observado"],
            "modo": "SOLO_PRUEBAS",
            "origen_simulado": True,
            "liquidacion_recalculada": None,
        },
    }
