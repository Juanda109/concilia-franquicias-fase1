"""INC020: diagnostico VISA-Host de solo lectura."""

from fastapi import APIRouter, HTTPException
from psycopg import Error as PostgreSQLError

from app.repositories.database import connection
from app.api.visa_documental_inc018 import (
    recuperar_vss,
)
from app.services.fase2.integracion_vss_inc018 import (
    integrar_vss,
)

router = APIRouter(
    prefix="/api/v1/jornadas",
    tags=["VISA Host INC020"],
)

CUENTAS_VISA = (
    "259095341",
    "299095888",
    "299095303",
)

FUENTES = ("HA22", "HA26", "HA32")


def consultar_host(id_jornada):
    sql = """
        SELECT
            i.tipo_insumo,
            i.id_archivo,
            h.cuenta,
            COUNT(h.id_host_resultado),
            SUM(h.valor_debe),
            SUM(h.valor_haber)
        FROM public.con_insumo_esperado i
        JOIN public.con_jornada j
          ON j.id_jornada = i.id_jornada
        LEFT JOIN public.con_host_resultado h
          ON h.id_archivo = i.id_archivo
         AND h.fecha_contable = j.fecha_contable
         AND h.tx_host = i.tipo_insumo
         AND h.cuenta = ANY(%s)
        WHERE i.id_jornada = %s
          AND i.tipo_insumo = ANY(%s)
        GROUP BY
            i.tipo_insumo,
            i.id_archivo,
            h.cuenta
        ORDER BY i.tipo_insumo, h.cuenta
    """

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(
                sql,
                (
                    list(CUENTAS_VISA),
                    id_jornada,
                    list(FUENTES),
                ),
            )
            filas = cur.fetchall()

    fuentes = {
        fuente: {
            "archivos": [],
            "cuentas": {},
        }
        for fuente in FUENTES
    }

    for fuente, archivo, cuenta, cantidad, debe, haber in filas:
        datos = fuentes[fuente]

        if archivo is not None and archivo not in datos["archivos"]:
            datos["archivos"].append(archivo)

        if cuenta is None:
            continue

        datos["cuentas"][cuenta] = {
            "movimientos": cantidad,
            "debe_cop": str(debe),
            "haber_cop": str(haber),
            "neto_cop": str(debe - haber),
        }

    cobertura = {
        fuente: {
            "presentes": [
                cuenta for cuenta in CUENTAS_VISA
                if cuenta in datos["cuentas"]
            ],
            "ausentes": [
                cuenta for cuenta in CUENTAS_VISA
                if cuenta not in datos["cuentas"]
            ],
        }
        for fuente, datos in fuentes.items()
    }

    completa = all(
        fuentes[fuente]["archivos"]
        and not cobertura[fuente]["ausentes"]
        for fuente in FUENTES
    )

    return fuentes, cobertura, completa


@router.get("/{id_jornada}/visa/diagnostico-host")
def diagnostico_visa_host(id_jornada: int):
    if id_jornada <= 0:
        raise HTTPException(422, "Jornada invalida")

    try:
        archivo, texto = recuperar_vss(id_jornada)

        visa = integrar_vss(
            id_jornada=id_jornada,
            id_archivo=archivo["id_archivo"],
            fecha_contable=archivo["fecha_contable"],
            contenido=texto,
            trm_confirmada=None,
        )

        fuentes, cobertura, completa = consultar_host(
            id_jornada
        )

    except HTTPException:
        raise
    except PostgreSQLError as exc:
        raise HTTPException(
            503, "PostgreSQL no disponible"
        ) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            409, "Diagnostico VISA no disponible"
        ) from exc

    return {
        "incremento": "INC020",
        "id_jornada": id_jornada,
        "fecha_contable": str(archivo["fecha_contable"]),
        "modo": "DIAGNOSTICO_SOLO_LECTURA",
        "estado": (
            "PENDIENTE_HOMOLOGACION"
            if completa
            else "COBERTURA_HOST_VISA_INSUFICIENTE"
        ),
        "visa": {
            "id_archivo": archivo["id_archivo"],
            "resumen_monetario": visa["resumen_monetario"],
        },
        "host": fuentes,
        "cobertura": cobertura,
        "diferencia_contable": None,
        "certificado": False,
        "conciliado_host": False,
        "homologado_contablemente": False,
    }
