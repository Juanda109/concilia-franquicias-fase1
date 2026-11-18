from datetime import date
from pydantic import BaseModel
from fastapi import APIRouter
from fastapi import HTTPException
from psycopg.rows import dict_row
from psycopg import OperationalError, errors

from app.repositories.database import connection

router = APIRouter(
    prefix="/api/v1/jornadas",
    tags=["Jornadas"]
)


@router.get("")
def listar_jornadas():
    try:
        with connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT
                        id_jornada,
                        fecha_contable,
                        estado,
                        version_catalogo,
                        total_archivos,
                        fec_inicio,
                        fec_completitud
                    FROM con_jornada
                    ORDER BY fecha_contable DESC
                """)
                return {
                    "total": cur.rowcount,
                    "jornadas": cur.fetchall()
                }

    except (OperationalError, KeyError):
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible"
        )

@router.get("/{id_jornada}")
def obtener_jornada(id_jornada: int):
    if id_jornada <= 0:
        raise HTTPException(
            status_code=422,
            detail="ID de jornada invalido"
        )

    try:
        with connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT
                        id_jornada,
                        fecha_contable,
                        estado,
                        version_catalogo,
                        total_archivos,
                        fec_inicio,
                        fec_completitud
                    FROM con_jornada
                    WHERE id_jornada = %s
                """, (id_jornada,))

                jornada = cur.fetchone()

                if jornada is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Jornada no encontrada"
                    )

                return jornada

    except (OperationalError, KeyError):
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible"
        )

@router.get("/{id_jornada}/insumos")
def obtener_insumos_jornada(id_jornada: int):
    if id_jornada <= 0:
        raise HTTPException(
            status_code=422,
            detail="ID de jornada invalido"
        )

    try:
        with connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:

                cur.execute("""
                    SELECT id_jornada
                    FROM con_jornada
                    WHERE id_jornada = %s
                """, (id_jornada,))

                if cur.fetchone() is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Jornada no encontrada"
                    )

                cur.execute("""
                    SELECT
                        id_insumo_esperado,
                        tipo_insumo,
                        fuente,
                        obligatorio,
                        estado,
                        id_archivo,
                        fec_recepcion,
                        fec_actualizacion
                    FROM con_insumo_esperado
                    WHERE id_jornada = %s
                    ORDER BY fuente, tipo_insumo
                """, (id_jornada,))

                insumos = cur.fetchall()

                return {
                    "id_jornada": id_jornada,
                    "total": len(insumos),
                    "insumos": insumos
                }

    except (OperationalError, KeyError):
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible"
        )


class CrearJornadaRequest(BaseModel):
    fecha_contable: date


@router.post("", status_code=201)
def crear_jornada(payload: CrearJornadaRequest):
    try:
        with connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    INSERT INTO con_jornada (
                        fecha_contable,
                        estado
                    )
                    VALUES (%s, 'PENDIENTE')
                    RETURNING
                        id_jornada,
                        fecha_contable,
                        estado,
                        version_catalogo
                """, (payload.fecha_contable,))

                return cur.fetchone()

    except errors.UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="Ya existe una jornada para esta fecha contable"
        )

    except (OperationalError, KeyError):
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible"
        )


class InicializarJornadaRequest(BaseModel):
    version_catalogo: int


@router.post("/{id_jornada}/inicializar")
def inicializar_jornada(
    id_jornada: int,
    payload: InicializarJornadaRequest
):
    if id_jornada <= 0 or payload.version_catalogo <= 0:
        raise HTTPException(
            status_code=422,
            detail="ID de jornada o version de catalogo invalida"
        )

    try:
        with connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT fn_inicializar_insumos_jornada(%s, %s)
                    AS insertados
                """, (id_jornada, payload.version_catalogo))

                resultado = cur.fetchone()

                cur.execute("""
                    SELECT
                        id_jornada,
                        fecha_contable,
                        estado,
                        version_catalogo
                    FROM con_jornada
                    WHERE id_jornada = %s
                """, (id_jornada,))

                jornada = cur.fetchone()

                return {
                    "jornada": jornada,
                    "insumos_insertados": resultado["insertados"]
                }

    except errors.RaiseException as exc:
        mensaje = str(exc).splitlines()[0]

        if mensaje.startswith("Jornada inexistente"):
            raise HTTPException(status_code=404, detail=mensaje)

        if mensaje.startswith("Catalogo incompleto"):
            raise HTTPException(status_code=409, detail=mensaje)

        if mensaje.startswith("Cambio de version no permitido"):
            raise HTTPException(status_code=409, detail=mensaje)

        if mensaje.startswith("Jornada ") and "sin version" in mensaje:
            raise HTTPException(status_code=409, detail=mensaje)

        raise HTTPException(
            status_code=422,
            detail="No fue posible inicializar la jornada"
        )

    except (OperationalError, KeyError):
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible"
        )
