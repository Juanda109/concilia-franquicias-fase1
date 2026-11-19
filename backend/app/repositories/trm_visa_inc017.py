"""RECON_F2_017: repositorio transaccional TRM Visa.

No consulta fuentes oficiales.
No realiza homologacion contable.
No certifica conciliaciones.
"""

from datetime import date
from decimal import Decimal

from app.repositories.database import connection
from app.services.fase2.trm_visa_inc017 import (
    ConfirmacionTRM,
    ErrorTRMVisa,
    validar_trm,
)


class ErrorPersistenciaTRM(ValueError):
    pass


def consultar_trm_vigente(id_jornada):
    if type(id_jornada) is not int or id_jornada <= 0:
        raise ErrorTRMVisa("Jornada invalida")

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")

            cur.execute("""
                SELECT fecha_contable
                FROM public.con_jornada
                WHERE id_jornada = %s
            """, (id_jornada,))

            jornada = cur.fetchone()

            if jornada is None:
                raise LookupError("Jornada inexistente")

            cur.execute("""
                SELECT id_trm, version, fecha_referencia,
                       trm_oficial, trm_aplicada, fuente,
                       referencia_fuente,
                       modificada_manualmente,
                       justificacion, usuario_confirmacion,
                       fecha_confirmacion
                FROM public.con_trm_jornada
                WHERE id_jornada = %s
                ORDER BY version DESC
                LIMIT 1
            """, (id_jornada,))

            fila = cur.fetchone()

    if fila is None:
        return {
            "id_jornada": id_jornada,
            "fecha_contable": jornada[0].isoformat(),
            "estado": "SIN_TRM_CONFIRMADA",
            "trm": None,
        }

    return {
        "id_jornada": id_jornada,
        "fecha_contable": jornada[0].isoformat(),
        "estado": "TRM_CONFIRMADA",
        "trm": {
            "id_trm": fila[0],
            "version": fila[1],
            "fecha_referencia": fila[2].isoformat(),
            "trm_oficial": (
                str(fila[3]) if fila[3] is not None else None
            ),
            "trm_aplicada": str(fila[4]),
            "fuente": fila[5],
            "referencia_fuente": fila[6],
            "modificada_manualmente": fila[7],
            "justificacion": fila[8],
            "usuario_confirmacion": fila[9],
            "fecha_confirmacion": fila[10].isoformat(),
        },
    }


def registrar_confirmacion_trm(
    *,
    id_jornada: int,
    trm_aplicada: str | Decimal,
    trm_oficial: str | Decimal | None,
    fuente: str,
    referencia_fuente: str | None,
    modificada_manualmente: bool,
    justificacion: str | None,
    usuario_autenticado: str,
):
    """Registra una version nueva dentro de una transaccion.

    Solo debe invocarse desde una capa que haya autenticado
    y autorizado al usuario. No se expone como API publica.
    """

    if type(id_jornada) is not int or id_jornada <= 0:
        raise ErrorTRMVisa("Jornada invalida")

    if (
        not isinstance(usuario_autenticado, str)
        or not usuario_autenticado.strip()
    ):
        raise ErrorTRMVisa("Usuario autenticado obligatorio")

    if (
        not isinstance(fuente, str)
        or not fuente.strip()
    ):
        raise ErrorTRMVisa("Fuente obligatoria")

    if (
        type(modificada_manualmente) is not bool
    ):
        raise ErrorTRMVisa("Indicador manual invalido")

    aplicada = validar_trm(trm_aplicada)

    oficial = (
        validar_trm(trm_oficial)
        if trm_oficial is not None else None
    )

    with connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT fecha_contable, estado
                FROM public.con_jornada
                WHERE id_jornada = %s
                FOR UPDATE
            """, (id_jornada,))

            jornada = cur.fetchone()

            if jornada is None:
                raise LookupError("Jornada inexistente")

            fecha_contable, estado_jornada = jornada

            # No habilitar modificaciones en jornadas cerradas.
            # La politica definitiva de estados debe validarse
            # antes de habilitar una API de escritura.
            # RECON_F2_017_ESTADOS_PERMITIDOS
            # Politica provisional: solo jornadas pendientes.
            if estado_jornada != "PENDIENTE":
                raise ErrorPersistenciaTRM(
                    "Estado de jornada no autorizado para TRM"
                )

            cur.execute("""
                SELECT COALESCE(MAX(version), 0)
                FROM public.con_trm_jornada
                WHERE id_jornada = %s
            """, (id_jornada,))

            version_actual = cur.fetchone()[0]
            if version_actual > 0:
                raise ErrorPersistenciaTRM(
                    "La jornada ya tiene TRM confirmada"
                )
            version = version_actual + 1

            confirmacion = ConfirmacionTRM(
                id_jornada=id_jornada,
                fecha_contable=fecha_contable,
                fecha_referencia=fecha_contable,
                trm_oficial=oficial,
                trm_aplicada=aplicada,
                fuente=fuente,
                modificada_manualmente=modificada_manualmente,
                justificacion=justificacion,
                usuario_confirmacion=usuario_autenticado,
                version=version,
            )

            cur.execute("""
                INSERT INTO public.con_trm_jornada (
                    id_jornada,
                    fecha_referencia,
                    version,
                    trm_oficial,
                    trm_aplicada,
                    fuente,
                    referencia_fuente,
                    modificada_manualmente,
                    justificacion,
                    usuario_confirmacion
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                RETURNING id_trm
            """, (
                confirmacion.id_jornada,
                confirmacion.fecha_referencia,
                confirmacion.version,
                confirmacion.trm_oficial,
                confirmacion.trm_aplicada,
                confirmacion.fuente,
                referencia_fuente,
                confirmacion.modificada_manualmente,
                confirmacion.justificacion,
                confirmacion.usuario_confirmacion,
            ))

            id_trm = cur.fetchone()[0]

    return {
        "id_trm": id_trm,
        "id_jornada": id_jornada,
        "fecha_referencia": fecha_contable.isoformat(),
        "version": version,
        "trm_aplicada": str(aplicada),
        "estado": "TRM_CONFIRMADA",
        "certificado": False,
        "conciliado_host": False,
    }
