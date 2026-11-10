"""Bloqueo de concurrencia para Host Loader."""

from contextlib import contextmanager

from app.repositories.database import connection


CLAVE_BLOQUEO_HOST = 26102101


class HostLoaderOcupado(RuntimeError):
    pass


@contextmanager
def bloqueo_host():
    """Mantiene un advisory lock durante todo el batch."""

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_try_advisory_lock(%s)",
                (CLAVE_BLOQUEO_HOST,),
            )

            adquirido = cur.fetchone()[0]

            if not adquirido:
                raise HostLoaderOcupado(
                    "Ya existe un Host Loader en ejecucion"
                )

        try:
            yield
        finally:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_advisory_unlock(%s)",
                    (CLAVE_BLOQUEO_HOST,),
                )

                liberado = cur.fetchone()[0]

                if not liberado:
                    raise RuntimeError(
                        "No se pudo liberar el bloqueo Host"
                    )
