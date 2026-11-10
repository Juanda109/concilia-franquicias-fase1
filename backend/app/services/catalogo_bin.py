from app.repositories.database import connection


def cargar_bines_activos():
    """
    Consulta el catalogo BIN activo.

    No aplica aun seleccion historica por fecha
    ni version de catalogo.
    """
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT bin_desde, tipo_tarjeta
                FROM con_parametro_bin_red
                WHERE tipo_catalogo = %s
                  AND activo = TRUE
            """, ("BINES_CANJE",))

            filas = cur.fetchall()

    return {
        int(bin_desde): tipo_tarjeta
        for bin_desde, tipo_tarjeta in filas
    }
