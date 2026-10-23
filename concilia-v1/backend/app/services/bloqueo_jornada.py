"""Bloqueo transaccional de jornada para Concilia V1."""

from psycopg import sql


def _id_desde_fila(fila):
    if isinstance(fila, dict):
        return fila["id_jornada"]
    return fila[0]


class BloqueoJornadaError(ValueError):
    """Error de identificacion o bloqueo de jornada."""


def bloquear_jornada_por_id(cur, id_jornada):
    """Bloquea una jornada dentro de la transaccion existente."""

    cur.execute(
        """
        SELECT id_jornada
        FROM public.con_jornada
        WHERE id_jornada = %s
        FOR UPDATE
        """,
        (id_jornada,),
    )

    fila = cur.fetchone()

    if fila is None:
        raise BloqueoJornadaError(
            f"Jornada inexistente: {id_jornada}"
        )

    return id_jornada


def bloquear_jornada_por_archivo(cur, id_archivo):
    """Identifica la jornada y adquiere su bloqueo."""

    cur.execute(
        """
        SELECT id_jornada
        FROM public.con_insumo_esperado
        WHERE id_archivo = %s
        """,
        (id_archivo,),
    )

    filas = cur.fetchall()

    if len(filas) != 1:
        raise BloqueoJornadaError(
            "Archivo sin jornada unica asociada"
        )

    id_jornada = _id_desde_fila(filas[0])

    return bloquear_jornada_por_id(
        cur,
        id_jornada,
    )


def bloquear_jornada_por_fecha(cur, fecha_contable):
    """Bloquea la jornada correspondiente a la fecha."""

    cur.execute(
        """
        SELECT id_jornada
        FROM public.con_jornada
        WHERE fecha_contable = %s
        FOR UPDATE
        """,
        (fecha_contable,),
    )

    fila = cur.fetchone()

    if fila is None:
        raise BloqueoJornadaError(
            "Jornada no encontrada para fecha contable"
        )

    return _id_desde_fila(fila)


def verificar_asociacion_jornada(
    cur, id_archivo, id_jornada_bloqueada
):
    """Verifica la asociacion bajo bloqueo transaccional."""

    cur.execute(
        """
        SELECT id_jornada
        FROM public.con_insumo_esperado
        WHERE id_archivo = %s
        FOR UPDATE
        """,
        (id_archivo,),
    )

    filas = cur.fetchall()

    if len(filas) != 1:
        raise BloqueoJornadaError(
            "Archivo sin jornada unica asociada"
        )

    id_jornada_actual = _id_desde_fila(filas[0])

    if id_jornada_actual != id_jornada_bloqueada:
        raise BloqueoJornadaError(
            "Asociacion de jornada modificada"
        )

    return id_jornada_actual


def verificar_jornada_modificable(cur, id_jornada):
    """Impide modificar jornadas tecnicamente completadas."""

    cur.execute(
        """
        SELECT estado
        FROM public.con_jornada
        WHERE id_jornada = %s
        FOR UPDATE
        """,
        (id_jornada,),
    )

    fila = cur.fetchone()

    if fila is None:
        raise BloqueoJornadaError(
            "Jornada inexistente"
        )

    estado = (
        fila["estado"]
        if isinstance(fila, dict)
        else fila[0]
    )

    if estado != "PENDIENTE":
        raise BloqueoJornadaError(
            "Jornada no modificable: " + str(estado)
        )

    return id_jornada

