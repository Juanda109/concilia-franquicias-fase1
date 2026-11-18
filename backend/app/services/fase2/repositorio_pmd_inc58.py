"""Repositorio de lectura PMD INC58.

Consulta PostgreSQL sin modificar datos.
"""

from app.repositories.database import connection

CAMPOS = (
    "DEBITO_CANTIDAD",
    "DEBITO_VALOR",
    "DEBITO_COMISION_INTERCAMBIO",
    "DEBITO_COMISION_ADMINISTRATIVA",
    "DEBITO_NETO",
    "CREDITO_CANTIDAD",
    "CREDITO_VALOR",
    "CREDITO_COMISION_INTERCAMBIO",
    "CREDITO_COMISION_ADMINISTRATIVA",
    "CREDITO_NETO",
    "TOTAL",
)


def normalizar(fila):
    resultado = {
        "id_archivo": fila["id_archivo"],
        "numero_linea": fila["linea_origen"],
        "PRODUCTO_SERVICIO": fila["producto_servicio"],
        "NIVEL": fila["nivel"],
        "ES_CONTROL": fila["es_control"],
    }

    for campo in CAMPOS:
        resultado[campo] = fila[campo.lower()]

    return resultado


def leer_jornada(id_jornada):
    """Lee PMD por jornada y valida integridad antes de devolver datos."""
    if type(id_jornada) is not int or id_jornada <= 0:
        raise ValueError("Jornada invalida")

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
                raise ValueError("Jornada inexistente")

            fecha_jornada = jornada[0]

            cur.execute("""
                SELECT DISTINCT
                    a.id_archivo,
                    a.fecha_contable
                FROM public.con_insumo_esperado i
                JOIN public.con_archivo_carga a
                  ON a.id_archivo = i.id_archivo
                WHERE i.id_jornada = %s
                  AND i.tipo_insumo = 'PMD'
                  AND a.tipo_archivo = 'PMD'
                  AND a.estado = 'PROCESADO'
                ORDER BY a.id_archivo
            """, (id_jornada,))

            archivos = [
                {
                    "id_archivo": fila[0],
                    "fecha_contable": fila[1],
                }
                for fila in cur.fetchall()
            ]

            if not archivos:
                return []

            if len(archivos) != 1:
                raise ValueError(
                    "Multiples archivos PMD procesados"
                )

            archivo = archivos[0]

            cur.execute("""
                SELECT
                    d.id_archivo,
                    d.linea_origen,
                    d.fecha_contable,
                    d.producto_servicio,
                    d.nivel,
                    d.es_control,
                    d.debito_cantidad,
                    d.debito_valor,
                    d.debito_comision_intercambio,
                    d.debito_comision_administrativa,
                    d.debito_neto,
                    d.credito_cantidad,
                    d.credito_valor,
                    d.credito_comision_intercambio,
                    d.credito_comision_administrativa,
                    d.credito_neto,
                    d.total
                FROM public.con_pmd_detalle d
                WHERE d.id_archivo = %s
                ORDER BY d.linea_origen
            """, (archivo["id_archivo"],))

            nombres = [
                columna.name
                for columna in cur.description
            ]

            filas_crudas = [
                dict(zip(nombres, fila))
                for fila in cur.fetchall()
            ]

            validar_integridad(
                id_jornada,
                fecha_jornada,
                archivos,
                filas_crudas,
            )

            return [
                normalizar(fila)
                for fila in filas_crudas
            ]

def validar_integridad(id_jornada, fecha_jornada, archivos, filas):
    """Valida integridad PMD antes del diagnostico monetario."""
    if type(id_jornada) is not int or id_jornada <= 0:
        raise ValueError("Jornada invalida")

    if fecha_jornada is None:
        raise ValueError("Fecha de jornada ausente")

    if len(archivos) != 1:
        raise ValueError("Se requiere un unico archivo PMD procesado")

    archivo = archivos[0]

    if archivo["fecha_contable"] != fecha_jornada:
        raise ValueError("Fecha de archivo diferente a jornada")

    if not filas:
        raise ValueError("Archivo PMD sin detalle")

    claves = set()

    for fila in filas:
        if fila["id_archivo"] != archivo["id_archivo"]:
            raise ValueError("Detalle asociado a otro archivo")

        if fila["fecha_contable"] != fecha_jornada:
            raise ValueError("Fecha de detalle diferente a jornada")

        clave = (fila["id_archivo"], fila["linea_origen"])

        if clave in claves:
            raise ValueError("Linea PMD duplicada")

        claves.add(clave)

    return True
