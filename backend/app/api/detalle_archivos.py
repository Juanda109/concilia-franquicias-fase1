from pathlib import Path
from contextlib import contextmanager
from tempfile import TemporaryDirectory
import shutil
"""Consulta paginada de resultados persistidos - Fase 1."""

from math import ceil
from pathlib import Path as FilePath
import os
import stat
from fastapi.encoders import jsonable_encoder
from app.ingestion.registry import obtener_parser

from fastapi import APIRouter, HTTPException, Path as ApiPath, Query
from psycopg import OperationalError
from psycopg.rows import dict_row

from app.repositories.database import connection


router = APIRouter(
    prefix="/api/v1/archivos",
    tags=["Detalle de archivos"],
)


COLUMNAS_HOST = (
    "linea_origen",
    "tx_host",
    "cuenta",
    "centro",
    "referencia",
    "concepto",
    "valor_debe",
    "valor_haber",
    "valor_saldo",
    "valor_normalizado",
)

COLUMNAS_FRANQUICIA = (
    "linea_origen",
    "reporte_origen",
    "franquicia",
    "cuenta",
    "concepto",
    "referencia",
    "moneda",
    "valor",
)



@contextmanager
def archivo_con_nombre_original(fisico, nombre_original):
    """Copia temporal para parsers que validan el nombre."""

    nombre = Path(nombre_original).name

    if nombre in ("", ".", ".."):
        raise ValueError("Nombre original invalido")

    with TemporaryDirectory(prefix="concilia_detalle_") as carpeta:
        temporal = Path(carpeta) / nombre
        shutil.copyfile(fisico, temporal)
        yield temporal


def interpretar_archivo_con_nombre_original(
    tipo, fisico, nombre_original
):
    """Ejecuta el parser sin modificar el archivo almacenado."""

    if tipo in ("MEP", "PMD", "VISA_SS_INTERNATIONAL"):
        with archivo_con_nombre_original(
            fisico, nombre_original
        ) as temporal:
            return obtener_parser(tipo).parse(temporal)

    return obtener_parser(tipo).parse(fisico)


@router.get("/{id_archivo}/contenido")
def consultar_contenido(
    id_archivo: int = ApiPath(gt=0),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=30, ge=1, le=100),
):
    try:
        with connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT
                        id_archivo,
                        tipo_archivo,
                        proceso_origen,
                        nombre_archivo,
                        fecha_contable,
                        estado,
                        total_registros,
                        fec_recepcion,
                        correlation_id,
                        ruta_archivo
                    FROM con_archivo_carga
                    WHERE id_archivo = %s
                """, (id_archivo,))

                archivo = cur.fetchone()

                if archivo is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Archivo no encontrado",
                    )

                tipo = archivo["tipo_archivo"]

                tabla_nueva = {
                    "HA22": "con_ha22_detalle",
                    "HA26": "con_ha26_detalle",
                    "HA32": "con_ha32_detalle",
                    "CAET": "con_canje_detalle",
                    "CANT": "con_canje_detalle",
                    "DEPO": "con_depo_detalle",
                    "CARTA_COMPENSACION": "con_carta_compensacion_detalle",
                    "PMD": "con_pmd_detalle",
                    "MEP": "con_mep_detalle",
                    "VSS": "con_vss_detalle",
                    "VISA_SS_INTERNATIONAL": "con_visa_ss_international_detalle",
                }.get(tipo)
                # Fase 1: CANT se consulta como plano fuente, sin cuentas ni
                # filtros de conciliacion. No expone PAN/TARJETA ni linea cruda.
                if tipo == "CANT":
                    import hashlib
                    fisico = FilePath(archivo["ruta_archivo"]).resolve()
                    raiz = os.environ.get("CONCILIA_ARCHIVOS_ROOT")
                    if raiz and not fisico.is_relative_to(FilePath(raiz).resolve()):
                        raise HTTPException(403, "Ruta fuera del directorio autorizado")
                    if not fisico.is_file() or fisico.stat().st_size > 100 * 1024 * 1024:
                        raise HTTPException(409, "Archivo fuente no disponible o excede limite")
                    # Evitar mostrar una copia distinta de la recibida.
                    cur.execute("SELECT checksum_sha256 FROM con_archivo_carga WHERE id_archivo=%s", (id_archivo,))
                    checksum = cur.fetchone()["checksum_sha256"]
                    if checksum:
                        with fisico.open("rb") as verificacion:
                            sha = hashlib.file_digest(verificacion, "sha256").hexdigest()
                        if sha.lower() != str(checksum).lower():
                            raise HTTPException(409, "Checksum del archivo fuente no coincide")
                    registros = []
                    total = 0
                    with fisico.open("r", encoding="utf-8", errors="replace") as fuente:
                        for numero, linea in enumerate(fuente, start=1):
                            linea = linea.rstrip("\r\n")
                            if not linea:
                                continue
                            total += 1
                            if (total - 1) // pageSize != page - 1:
                                continue
                            def campo(inicio, longitud):
                                return linea[inicio - 1:inicio - 1 + longitud].strip()
                            tx = campo(1, 2)
                            registros.append({
                                "linea_origen": numero,
                                "tx_original": tx,
                                "clase_registro": "TOTAL_CONTROL" if tx.isdigit() and int(tx) % 2 else "MOVIMIENTO_CANDIDATO",
                                "bin_dest": campo(9, 6),
                                "fecha_canje_origen": campo(15, 6),
                                "vl_total_origen": campo(123, 9),
                                "cod_error_origen": campo(198, 2),
                                "longitud": len(linea),
                            })
                    campos_fuente = (
                        "linea_origen", "tx_original", "clase_registro",
                        "bin_dest", "fecha_canje_origen", "vl_total_origen",
                        "cod_error_origen", "longitud",
                    )
                    archivo_publico = dict(archivo)
                    archivo_publico.pop("ruta_archivo", None)
                    return {
                        "id_archivo": id_archivo,
                        "archivo": archivo_publico,
                        "origen_datos": "FUENTE_F1",
                        "controles": [], "errores": [],
                        "advertencia": "Vista del plano original: incluye movimientos candidatos y registros de control. No equivale a registros persistidos ni a conciliacion contable.",
                        "contenido": {
                            "headers": [{"key": k, "label": k.upper()} for k in campos_fuente],
                            "items": registros, "total": total, "page": page,
                            "pageSize": pageSize,
                            "totalPages": max(1, ceil(total / pageSize)),
                        },
                    }

                if tabla_nueva:
                    cur.execute("SELECT to_regclass(%s) AS tabla", (f"public.{tabla_nueva}",))
                    if cur.fetchone()["tabla"] is not None:
                        cur.execute(f"SELECT COUNT(*) AS total FROM {tabla_nueva} WHERE id_archivo=%s", (id_archivo,))
                        cantidad = cur.fetchone()["total"]
                        if cantidad:
                            offset = (page - 1) * pageSize
                            if tipo in ("CAET", "CANT"):
                                from app.services.persistencia_detalle import CAMPOS_CANJE
                                campos = ("linea_origen", *CAMPOS_CANJE)
                                cur.execute(
                                    f"SELECT {', '.join(campos)} FROM {tabla_nueva} WHERE id_archivo=%s ORDER BY linea_origen LIMIT %s OFFSET %s",
                                    (id_archivo, pageSize, offset),
                                )
                                items = cur.fetchall()
                            elif tipo == 'CARTA_COMPENSACION':
                                from app.services.persistencia_detalle import CAMPOS_CARTA
                                campos = ('linea_origen', *CAMPOS_CARTA)
                                cur.execute(
                                    f"SELECT {', '.join(campos)} FROM {tabla_nueva} WHERE id_archivo=%s ORDER BY linea_origen LIMIT %s OFFSET %s",
                                    (id_archivo, pageSize, offset),
                                )
                                items = cur.fetchall()
                            elif tipo == 'VISA_SS_INTERNATIONAL':
                                campos = ('linea_origen', 'pagina', 'ftsre', 'nombre_entidad',
                                          'moneda', 'importe_neto', 'tipo_movimiento',
                                          'fecha_valor', 'fecha_procesamiento')
                                cur.execute(
                                    f"SELECT {', '.join(campos)} FROM {tabla_nueva} "
                                    "WHERE id_archivo=%s ORDER BY linea_origen LIMIT %s OFFSET %s",
                                    (id_archivo, pageSize, offset))
                                items = cur.fetchall()
                            elif tipo == 'VSS':
                                from app.services.persistencia_detalle import CAMPOS_VSS

                                campos = ('linea_origen', *CAMPOS_VSS)

                                cur.execute(
                                    f"SELECT {', '.join(campos)} "
                                    f"FROM {tabla_nueva} "
                                    "WHERE id_archivo=%s "
                                    "ORDER BY linea_origen "
                                    "LIMIT %s OFFSET %s",
                                    (id_archivo, pageSize, offset),
                                )

                                items = cur.fetchall()

                            elif tipo == 'MEP':
                                from app.services.persistencia_detalle import CAMPOS_MEP

                                campos = ('linea_origen', *CAMPOS_MEP)

                                cur.execute(
                                    f"SELECT {', '.join(campos)} "
                                    f"FROM {tabla_nueva} "
                                    "WHERE id_archivo=%s "
                                    "ORDER BY linea_origen "
                                    "LIMIT %s OFFSET %s",
                                    (id_archivo, pageSize, offset),
                                )

                                items = cur.fetchall()

                                for item in items:
                                    for clave, valor in item.items():
                                        if hasattr(valor, 'as_tuple'):
                                            item[clave] = str(valor)

                            elif tipo == 'PMD':
                                from app.services.persistencia_detalle import CAMPOS_PMD

                                campos = ('linea_origen', *CAMPOS_PMD)

                                cur.execute(
                                    f"SELECT {', '.join(campos)} "
                                    f"FROM {tabla_nueva} "
                                    "WHERE id_archivo=%s "
                                    "ORDER BY linea_origen "
                                    "LIMIT %s OFFSET %s",
                                    (id_archivo, pageSize, offset),
                                )

                                items = cur.fetchall()

                                for item in items:
                                    for clave, valor in item.items():
                                        if hasattr(valor, 'as_tuple'):
                                            item[clave] = str(valor)

                            elif tipo == 'DEPO':
                                from app.services.persistencia_detalle import CAMPOS_DEPO
                                campos = ('linea_origen', *CAMPOS_DEPO)
                                cur.execute(
                                    f"SELECT {', '.join(campos)} FROM {tabla_nueva} WHERE id_archivo=%s ORDER BY linea_origen LIMIT %s OFFSET %s",
                                    (id_archivo, pageSize, offset),
                                )
                                items = cur.fetchall()
                            else:
                                cur.execute(
                                    f"SELECT linea_origen, campos_origen FROM {tabla_nueva} WHERE id_archivo=%s ORDER BY linea_origen LIMIT %s OFFSET %s",
                                    (id_archivo, pageSize, offset),
                                )
                                items = []
                                for r in cur.fetchall():
                                    items.append({"linea_origen": r["linea_origen"], **r["campos_origen"]})
                                campos = tuple(dict.fromkeys(k for item in items for k in item))
                            cur.execute(
                                "SELECT codigo, valor_obtenido FROM con_detalle_control WHERE id_archivo=%s ORDER BY codigo",
                                (id_archivo,),
                            )
                            controles_persistidos = [
                                {"codigo": c["codigo"], "obtenido": c["valor_obtenido"]}
                                for c in cur.fetchall()
                            ]
                            archivo_publico = dict(archivo)
                            archivo_publico.pop("ruta_archivo", None)
                            return {
                                "id_archivo": id_archivo, "archivo": archivo_publico,
                                "origen_datos": "PERSISTIDO", "controles": controles_persistidos, "errores": [],
                                "advertencia": None,
                                "contenido": {
                                    "headers": [{"key": c, "label": c.upper()} for c in campos],
                                    "items": jsonable_encoder(items), "total": cantidad,
                                    "page": page, "pageSize": pageSize,
                                    "totalPages": max(1, ceil(cantidad / pageSize)),
                                },
                            }

                # F1: CAET/CANT sin detalle persistido no deben caer al
                # resultado contable legado (con_franquicia_resultado).
                if tipo in ("CAET", "CANT"):
                    fisico = FilePath(archivo["ruta_archivo"]).resolve()
                    raiz = os.environ.get("CONCILIA_ARCHIVOS_ROOT")
                    if raiz and not fisico.is_relative_to(FilePath(raiz).resolve()):
                        raise HTTPException(403, "Ruta fuera del directorio autorizado")
                    controles, errores, advertencia = [], [], None
                    registros = []
                    origen = "NO_DISPONIBLE"
                    try:
                        estado_fisico = fisico.stat()
                        if not stat.S_ISREG(estado_fisico.st_mode):
                            raise ValueError("Ruta no corresponde a archivo regular")
                        if estado_fisico.st_size > 100 * 1024 * 1024:
                            raise ValueError("Archivo supera limite de visualizacion")
                        resultado = interpretar_archivo_con_nombre_original(
                            tipo, fisico, archivo["nombre_archivo"]
                        )
                        registros = resultado.records
                        controles = jsonable_encoder(resultado.controls)
                        errores = jsonable_encoder(resultado.errors)
                        origen = "INTERPRETADO_NO_PERSISTIDO"
                    except (OSError, ValueError) as exc:
                        advertencia = f"No fue posible interpretar el archivo: {type(exc).__name__}"
                    total = len(registros)
                    offset = (page - 1) * pageSize
                    items = jsonable_encoder(registros[offset:offset + pageSize])
                    columnas = tuple(dict.fromkeys(k for item in items for k in item))
                    archivo_publico = dict(archivo)
                    archivo_publico.pop("ruta_archivo", None)
                    return {
                        "id_archivo": id_archivo, "archivo": archivo_publico,
                        "origen_datos": origen, "controles": controles,
                        "errores": errores, "advertencia": advertencia,
                        "contenido": {
                            "headers": [{"key": k, "label": k.upper()} for k in columnas],
                            "items": items, "total": total, "page": page,
                            "pageSize": pageSize,
                            "totalPages": max(1, ceil(total / pageSize)),
                        },
                    }

                if tipo in ("HA22", "HA26", "HA32"):
                    tabla = "con_host_resultado"
                    columnas = COLUMNAS_HOST
                    orden = "linea_origen, id_host_resultado"

                else:
                    tabla = "con_franquicia_resultado"
                    columnas = COLUMNAS_FRANQUICIA
                    orden = (
                        "linea_origen NULLS LAST, "
                        "id_franquicia_resultado"
                    )

                cur.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM {tabla}
                    WHERE id_archivo = %s
                    """,
                    (id_archivo,),
                )

                total = cur.fetchone()["total"]
                paginas = max(1, ceil(total / pageSize))
                offset = (page - 1) * pageSize

                cur.execute(
                    f"""
                    SELECT {", ".join(columnas)}
                    FROM {tabla}
                    WHERE id_archivo = %s
                    ORDER BY {orden}
                    LIMIT %s OFFSET %s
                    """,
                    (id_archivo, pageSize, offset),
                )

                filas = cur.fetchall()

                for fila in filas:
                    for clave, valor in fila.items():
                        if hasattr(valor, "as_tuple"):
                            fila[clave] = str(valor)

                origen = "PERSISTIDO"
                controles = []
                errores = []
                advertencia = None
                if total == 0 and archivo["estado"] == "RECIBIDO":
                    # Solo ruta previamente registrada en PostgreSQL.
                    # Un directorio raiz autorizado puede restringirse mediante
                    # CONCILIA_ARCHIVOS_ROOT; no se acepta ruta desde HTTP.
                    fisico = FilePath(archivo["ruta_archivo"]).resolve()
                    raiz = os.environ.get("CONCILIA_ARCHIVOS_ROOT")
                    if raiz and not fisico.is_relative_to(FilePath(raiz).resolve()):
                        raise HTTPException(403, "Ruta fuera del directorio autorizado")
                    try:
                        estado_fisico = fisico.stat()
                        if not stat.S_ISREG(estado_fisico.st_mode):
                            raise ValueError("Ruta no corresponde a archivo regular")
                        if estado_fisico.st_size > 100 * 1024 * 1024:
                            raise ValueError("Archivo supera limite de visualizacion")
                        resultado = interpretar_archivo_con_nombre_original(tipo, fisico, archivo['nombre_archivo'])
                        registros = resultado.records
                        controles = jsonable_encoder(resultado.controls)
                        errores = jsonable_encoder(resultado.errors)
                        total = len(registros)
                        paginas = max(1, ceil(total / pageSize))
                        filas = jsonable_encoder(registros[offset:offset + pageSize])
                        columnas = tuple(dict.fromkeys(
                            clave for registro in filas for clave in registro.keys()
                        ))
                        origen = "INTERPRETADO"
                    except (OSError, ValueError) as exc:
                        origen = "NO_DISPONIBLE"
                        advertencia = f"No fue posible leer el archivo: {type(exc).__name__}"
                        filas = []
                        columnas = ()

                archivo_publico = dict(archivo)
                archivo_publico.pop("ruta_archivo", None)
                return {
                    "id_archivo": id_archivo,
                    "archivo": archivo_publico,
                    "origen_datos": origen,
                    "controles": controles,
                    "errores": errores,
                    "advertencia": advertencia,
                    "contenido": {
                        "headers": [
                            {
                                "key": columna,
                                "label": columna.upper(),
                            }
                            for columna in columnas
                        ],
                        "items": filas,
                        "total": total,
                        "page": page,
                        "pageSize": pageSize,
                        "totalPages": paginas,
                    },
                }

    except (OperationalError, KeyError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible",
        ) from exc
