from app.services.bloqueo_jornada import verificar_jornada_modificable
from app.services.bloqueo_jornada import bloquear_jornada_por_fecha
from fastapi import APIRouter, HTTPException, Path
from psycopg import OperationalError
from psycopg.rows import dict_row

from app.repositories.database import connection

router = APIRouter(
    prefix="/api/v1/archivos",
    tags=["Archivos"]
)


@router.get("")
def listar_archivos():
    try:
        with connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT
                        id_archivo,
                        fecha_contable,
                        proceso_origen,
                        tipo_archivo,
                        franquicia,
                        nombre_archivo,
                        total_registros,
                        estado,
                        correlation_id,
                        fec_recepcion
                    FROM con_archivo_carga
                    ORDER BY fec_recepcion DESC, id_archivo DESC
                """)

                archivos = cur.fetchall()

                return {
                    "total": len(archivos),
                    "archivos": archivos
                }

    except (OperationalError, KeyError):
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible"
        )


@router.get("/{id_archivo}")
def obtener_archivo(
    id_archivo: int = Path(gt=0)
):
    try:
        with connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT
                        id_archivo,
                        fecha_contable,
                        proceso_origen,
                        tipo_archivo,
                        franquicia,
                        nombre_archivo,
                        total_registros,
                        estado,
                        correlation_id,
                        fec_recepcion
                    FROM con_archivo_carga
                    WHERE id_archivo = %s
                """, (id_archivo,))

                archivo = cur.fetchone()

                if archivo is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Archivo no encontrado"
                    )

                return archivo

    except (OperationalError, KeyError):
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible"
        )

# Recepcion fisica de archivos - MVP1

import os
import uuid
from datetime import date
from pathlib import Path as FilePath

from fastapi import File, Form, UploadFile, BackgroundTasks
from psycopg import errors

from app.ingestion.catalogo import INSUMOS_FUNCIONALES
from app.services.validacion_archivos import validar_archivo, ArchivoRechazado
from app.services.validacion_fechas_host import (
    validar_fechas_host,
    FechaInternaHostInvalida,
)
from app.services.correspondencia_archivos import (
    validar_correspondencia,
    CorrespondenciaInvalida,
)
from app.services.almacenamiento import (
    guardar_archivo,
    ArchivoDemasiadoGrande,
)


@router.post("", status_code=201)
def recibir_archivo(
    archivo: UploadFile = File(...),
    fecha_contable: date = Form(...),
    tipo_archivo: str = Form(...),
    background_tasks: BackgroundTasks = None,
):
    tipo_archivo = tipo_archivo.strip().upper()

    if tipo_archivo not in INSUMOS_FUNCIONALES:
        raise HTTPException(
            status_code=422,
            detail="Tipo de insumo no permitido en MVP1"
        )

    fuente = INSUMOS_FUNCIONALES[tipo_archivo]
    correlation_id = str(uuid.uuid4())

    directorio = FilePath(
        os.getenv("UPLOAD_DIR", "data/uploads")
    )

    ruta_guardada = None
    persistencia_confirmada = False

    try:
        with connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:

                id_jornada_bloqueada = bloquear_jornada_por_fecha(
                    cur, fecha_contable
                )

                verificar_jornada_modificable(
                    cur, id_jornada_bloqueada
                )

                cur.execute("""
                    SELECT
                        j.id_jornada,
                        j.fecha_contable,
                        i.id_insumo_esperado,
                        i.estado,
                        i.id_archivo,
                        a.estado AS estado_archivo_anterior,
                        a.total_registros AS registros_anteriores,
                        a.checksum_sha256 AS checksum_anterior
                    FROM con_jornada j
                    JOIN con_insumo_esperado i
                      ON i.id_jornada = j.id_jornada
                    LEFT JOIN con_archivo_carga a
                      ON a.id_archivo = i.id_archivo
                    WHERE j.fecha_contable = %s
                      AND i.tipo_insumo = %s
                      AND i.fuente = %s
                    FOR UPDATE OF i
                """, (fecha_contable, tipo_archivo, fuente))

                esperado = cur.fetchone()

                if (
                    esperado is not None
                    and esperado["id_jornada"] != id_jornada_bloqueada
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Asociacion de jornada inconsistente"
                    )

                if esperado is None:
                    raise HTTPException(
                        status_code=409,
                        detail="Jornada o insumo no inicializado"
                    )

                # F1: archivo procesado es definitivo en la jornada.
                # Se valida el estado de ambos registros antes de guardar el archivo.
                if (esperado["estado"] == "PROCESADO" or
                        esperado["estado_archivo_anterior"] == "PROCESADO"):
                    raise HTTPException(409, "Archivo procesado exitosamente: no se permite volver a subir")
                if (esperado["id_archivo"] is not None and
                        esperado["estado_archivo_anterior"] != esperado["estado"]):
                    raise HTTPException(409, "Estados de archivo e insumo incompatibles")

                # F1: solo reemplazo de RECIBIDO, nunca PROCESADO.
                reemplazo_recibido = (
                    esperado["estado"] == "RECIBIDO"
                    and esperado["id_archivo"] is not None
                )
                if esperado["estado"] != "PENDIENTE" and not reemplazo_recibido:
                    raise HTTPException(409, "Insumo ya recibido o procesado")
                if reemplazo_recibido:
                    anterior = esperado["id_archivo"]
                    # Una confirmacion es una decision auditada; no se revoca
                    # implicitamente mediante una nueva carga.
                    cur.execute("""SELECT 1 FROM con_confirmacion_sin_movimientos
                                   WHERE id_archivo=%s""", (anterior,))
                    if cur.fetchone() is not None:
                        raise HTTPException(409, "Archivo confirmado sin movimientos: requiere procedimiento de revocacion")
                    # Evitar reemplazar un detalle ya persistido aunque el
                    # estado de recepcion este desactualizado.
                    tablas_detalle = {
                        "HA22": "con_ha22_detalle", "HA26": "con_ha26_detalle",
                        "HA32": "con_ha32_detalle", "CAET": "con_canje_detalle",
                        "CANT": "con_canje_detalle", "DEPO": "con_depo_detalle",
                        "CARTA_COMPENSACION": "con_carta_compensacion_detalle",
                        "PMD": "con_pmd_detalle", "MEP": "con_mep_detalle",
                        "VSS": "con_vss_detalle",
                    }
                    tabla = tablas_detalle[tipo_archivo]  # nombres cerrados, no entrada del usuario
                    cur.execute(f"SELECT 1 FROM {tabla} WHERE id_archivo=%s LIMIT 1", (anterior,))
                    if cur.fetchone() is not None:
                        raise HTTPException(409, "Archivo con detalle persistido: reemplazo no permitido")

                validar_correspondencia(
                    tipo_insumo=tipo_archivo,
                    nombre_original=archivo.filename,
                    fecha_contable=esperado["fecha_contable"],
                )

                guardado = guardar_archivo(
                    archivo,
                    directorio
                )

                ruta_guardada = FilePath(guardado["ruta"])

                if guardado["tamano_bytes"] == 0:
                    raise HTTPException(
                        status_code=422,
                        detail="Archivo vacio"
                    )

                resultado_validacion = validar_archivo(
                    tipo=tipo_archivo,
                    nombre_original=guardado["nombre_original"],
                    ruta_guardada=ruta_guardada,
                )

                validar_fechas_host(
                    tipo_insumo=tipo_archivo,
                    fecha_contable=esperado["fecha_contable"],
                    resultado=resultado_validacion,
                )

                total_registros = len(resultado_validacion.records)
                if reemplazo_recibido and guardado["checksum_sha256"] == esperado["checksum_anterior"]:
                    raise HTTPException(409, "El archivo nuevo es identico al anterior")

                cur.execute("""
                    INSERT INTO con_archivo_carga (
                        fecha_contable,
                        proceso_origen,
                        tipo_archivo,
                        franquicia,
                        nombre_archivo,
                        ruta_archivo,
                        checksum_sha256,
                        total_registros,
                        estado,
                        correlation_id
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, 'RECIBIDO', %s
                    )
                    RETURNING id_archivo
                """, (
                    fecha_contable,
                    fuente,
                    tipo_archivo,
                    None if fuente == "HOST" else fuente,
                    guardado["nombre_original"],
                    guardado["ruta"],
                    guardado["checksum_sha256"],
                    total_registros,
                    correlation_id,
                ))

                id_archivo = cur.fetchone()["id_archivo"]

                cur.execute("""
                    UPDATE con_insumo_esperado
                    SET estado = 'RECIBIDO',
                        id_archivo = %s,
                        fec_recepcion = CURRENT_TIMESTAMP,
                        fec_actualizacion = CURRENT_TIMESTAMP
                    WHERE id_insumo_esperado = %s
                """, (
                    id_archivo,
                    esperado["id_insumo_esperado"],
                ))

                if reemplazo_recibido:
                    cur.execute("""
                        INSERT INTO con_trazabilidad
                        (correlation_id,id_archivo,id_jornada,tipo_evento,componente,detalle)
                        VALUES (%s,%s,%s,'ARCHIVO_RECIBIDO_REEMPLAZADO','ARCHIVOS_API',%s)
                    """, (correlation_id,id_archivo,id_jornada_bloqueada,
                           f"{tipo_archivo}: anterior={esperado['id_archivo']}; nuevo={id_archivo}"))

                cur.execute("""
                    INSERT INTO con_trazabilidad (
                        correlation_id,
                        id_archivo,
                        id_jornada,
                        tipo_evento,
                        componente,
                        detalle
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s
                    )
                """, (
                    correlation_id,
                    id_archivo,
                    id_jornada_bloqueada,
                    "ARCHIVO_RECIBIDO",
                    "ARCHIVOS_API",
                    f"Recepcion de {tipo_archivo}"
                ))

        # Este punto solo se alcanza si el contexto
        # de conexion termino sin errores.
        persistencia_confirmada = True
        if background_tasks is not None:
            # Primero la ingesta individual F1; no espera los otros nueve insumos.
            from app.services.procesamiento_individual_f1 import procesar_archivo_recibido_f1
            from app.services.procesamiento_automatico import procesar_jornada_si_lista
            background_tasks.add_task(procesar_archivo_recibido_f1, id_jornada_bloqueada, id_archivo)
            background_tasks.add_task(procesar_jornada_si_lista, id_jornada_bloqueada)

        return {
            "id_archivo": id_archivo,
            "tipo_archivo": tipo_archivo,
            "fecha_contable": fecha_contable,
            "estado": "RECIBIDO",
            "checksum_sha256": guardado["checksum_sha256"],
            "correlation_id": correlation_id,
        }

    except FechaInternaHostInvalida as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.detalle()
        ) from exc

    except CorrespondenciaInvalida as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.detalle()
        ) from exc

    except ArchivoRechazado as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.detalle()
        ) from exc

    except ArchivoDemasiadoGrande:
        raise HTTPException(
            status_code=413,
            detail="Archivo supera el limite permitido"
        )

    except errors.UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="Archivo duplicado por checksum"
        )

    except (OperationalError, KeyError):
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible"
        )

    finally:
        if ruta_guardada is not None and not persistencia_confirmada:
            ruta_guardada.unlink(missing_ok=True)


from app.services.procesamiento_host import (
    procesar_host,
    ProcesamientoHostError,
)
from app.services.normalizacion_host import NormalizacionHostError


@router.post("/{id_archivo}/procesar")
def procesar_archivo_host(id_archivo: int = Path(gt=0)):
    """Procesa un archivo Host previamente recibido."""

    try:
        return procesar_host(id_archivo)

    except ProcesamientoHostError as exc:
        mensaje = str(exc)

        if mensaje == "Archivo no asociado a una jornada":
            raise HTTPException(
                status_code=404,
                detail={
                    "codigo": "ARCHIVO_NO_ENCONTRADO",
                    "mensaje": mensaje,
                },
            ) from exc

        raise HTTPException(
            status_code=409,
            detail={
                "codigo": "PROCESAMIENTO_HOST_RECHAZADO",
                "mensaje": mensaje,
            },
        ) from exc

    except FechaInternaHostInvalida as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.detalle(),
        ) from exc

    except NormalizacionHostError:
        raise HTTPException(
            status_code=422,
            detail={
                "codigo": "NORMALIZACION_HOST_INVALIDA",
                "mensaje": "El archivo contiene valores Host invalidos",
            },
        )

    except (OperationalError, KeyError):
        raise HTTPException(
            status_code=503,
            detail={
                "codigo": "SERVICIO_NO_DISPONIBLE",
                "mensaje": "Base de datos no disponible",
            },
        )
