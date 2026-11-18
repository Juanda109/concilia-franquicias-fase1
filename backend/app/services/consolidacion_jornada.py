"""Servicio de consolidacion tecnica de jornadas MVP1."""

from uuid import uuid4

from app.repositories.database import connection


class ConsolidacionJornadaError(ValueError):
    pass


class JornadaNoEncontrada(ConsolidacionJornadaError):
    pass


class JornadaIncompleta(ConsolidacionJornadaError):
    pass


def consolidar_jornada(id_jornada: int):
    """Consolida segun el catalogo versionado de la jornada."""

    if id_jornada <= 0:
        raise ConsolidacionJornadaError(
            "Identificador de jornada invalido"
        )

    correlation_id = (
        "CONSOLIDACION-API-" + str(uuid4())
    )

    with connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SET LOCAL lock_timeout = '5s'"
            )

            cur.execute(
                "SET LOCAL statement_timeout = '60s'"
            )

            cur.execute("""
                SELECT estado, version_catalogo
                FROM public.con_jornada
                WHERE id_jornada = %s
                FOR UPDATE
            """, (id_jornada,))

            jornada = cur.fetchone()

            if jornada is None:
                raise JornadaNoEncontrada(
                    "Jornada no encontrada"
                )

            cur.execute("""
                SELECT *
                FROM public.fn_consolidar_jornada_tecnica(
                    %s, %s
                )
            """, (id_jornada, correlation_id))

            resultado = cur.fetchone()

            if resultado is None:
                raise JornadaIncompleta(
                    "Consolidacion sin resultado"
                )

            (
                jornada_resultado,
                estado,
                total_archivos,
                idempotente,
            ) = resultado

            esperados = {1: 10, 2: 10}.get(jornada[1])
            if esperados is None:
                raise JornadaIncompleta("Version de catalogo no soportada")
            if (
                jornada_resultado != id_jornada
                or estado != "COMPLETADA"
                or total_archivos != esperados
            ):
                raise JornadaIncompleta(
                    "Resultado de consolidacion incompatible"
                )

            return {
                "id_jornada": jornada_resultado,
                "estado": estado,
                "total_archivos": total_archivos,
                "idempotente": idempotente,
                "correlation_id": correlation_id,
            }
