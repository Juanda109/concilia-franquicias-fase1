"""Procesamiento de franquicias MVP1. Host mantiene su endpoint historico."""
from fastapi import APIRouter, HTTPException, Path
from psycopg import OperationalError
from app.repositories.database import connection
from app.services.procesamiento_credibanco import (
    procesar_cant, ProcesamientoCredibancoError,
)
from app.services.persistencia_detalle import persistir_detalle, DetalleError

router = APIRouter(prefix="/api/v1/archivos", tags=["Procesamiento franquicias"])
TIPOS = frozenset(("CAET", "CANT", "DEPO", "CARTA_COMPENSACION", "PMD", "MEP", "VSS", "VISA_SS_INTERNATIONAL"))


def ejecutar_franquicia(id_archivo: int):
    # No mutar estados ni reescribir tablas desde la capa API.
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("""SELECT a.tipo_archivo, i.tipo_insumo, a.estado, i.estado
                           FROM con_archivo_carga a
                           JOIN con_insumo_esperado i ON i.id_archivo=a.id_archivo
                           WHERE a.id_archivo=%s""", (id_archivo,))
            fila = cur.fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    tipo, tipo_insumo, estado_archivo, estado_insumo = fila
    if tipo not in TIPOS or tipo_insumo != tipo:
        raise HTTPException(status_code=422, detail="Archivo no corresponde a franquicia MVP1")
    if estado_archivo not in ("RECIBIDO", "PROCESADO") or estado_archivo != estado_insumo:
        raise HTTPException(status_code=409, detail="Estados de archivo e insumo incompatibles")
    try:
        # Fase 1: ingesta y persistencia del detalle fuente exclusivamente.
        # Las reglas contables CANT pertenecen a Fase 2.
        detalle = persistir_detalle(id_archivo)
        return {"id_archivo": id_archivo, "tipo_archivo": tipo,
                "estado": "PROCESADO", "normalizado": None, "detalle": detalle}
    except (ProcesamientoCredibancoError, DetalleError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OperationalError, KeyError) as exc:
        raise HTTPException(status_code=503, detail="Base de datos no disponible") from exc


@router.post("/{id_archivo}/procesar-franquicia")
def procesar_archivo_franquicia(id_archivo: int = Path(gt=0)):
    return ejecutar_franquicia(id_archivo)
