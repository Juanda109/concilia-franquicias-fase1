"""Persistencia documental idempotente de Carta Auxiliar V69."""

import hashlib
import json

from datetime import date
from pathlib import Path

from psycopg.types.json import Jsonb
from psycopg.rows import dict_row

from app.repositories.database import connection
from app.parsers.carta_reportes_auxiliares_v69 import extraer


def _hash_archivo(ruta: Path) -> str:
    digest = hashlib.sha256()

    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)

    return digest.hexdigest()


def _fecha(valor):
    if valor is None or valor == "":
        return None

    if isinstance(valor, date):
        return valor

    return date.fromisoformat(str(valor)[:10])


def _hash_alerta(alerta: dict) -> str:
    contenido = json.dumps(
        alerta,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )

    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def persistir_carta_auxiliar_v69(
    id_archivo: int,
    dry_run: bool = True,
) -> dict:
    """
    Persiste hojas, paginas, lineas y alertas documentales V69.

    dry_run=True:
        Ejecuta todas las escrituras y verifica resultados,
        pero revierte la transaccion.

    dry_run=False:
        Confirma la persistencia mediante COMMIT.

    No habilita movimientos monetarios ni modifica L6/L8.
    """

    if id_archivo <= 0:
        raise ValueError("Identificador de archivo invalido.")

    # 1. Recuperar los metadatos de un insumo Carta ya procesado.

    with connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SET TRANSACTION READ ONLY")

            cur.execute("""
                SELECT
                    a.id_archivo,
                    a.nombre_archivo,
                    a.ruta_archivo,
                    a.checksum_sha256,
                    a.fecha_contable,
                    a.correlation_id,
                    a.estado,
                    i.id_jornada,
                    i.estado AS estado_insumo
                FROM public.con_archivo_carga a
                JOIN public.con_insumo_esperado i
                  ON i.id_archivo = a.id_archivo
                WHERE a.id_archivo = %s
                  AND a.tipo_archivo = 'CARTA_COMPENSACION'
                  AND i.tipo_insumo = 'CARTA_COMPENSACION'
                  AND i.obligatorio = TRUE
            """, (id_archivo,))

            archivo = cur.fetchone()

    if archivo is None:
        raise ValueError(
            "El archivo no esta asociado a una expectativa "
            "obligatoria de Carta de Compensacion."
        )

    if (
        archivo["estado"] != "PROCESADO"
        or archivo["estado_insumo"] != "PROCESADO"
    ):
        raise ValueError("El archivo o el insumo no estan PROCESADOS.")

    ruta = Path(archivo["ruta_archivo"])

    if not ruta.is_file():
        raise FileNotFoundError(str(ruta))

    checksum_calculado = _hash_archivo(ruta)
    checksum_registrado = archivo["checksum_sha256"].strip().lower()

    if checksum_calculado != checksum_registrado:
        raise ValueError("El checksum del archivo original no coincide.")

    id_jornada = archivo["id_jornada"]
    fecha_contable = archivo["fecha_contable"]
    correlation_id = archivo["correlation_id"]

    # 2. Ejecutar extractor sobre el original.

    resultado = extraer(
        ruta,
        fecha_contable.isoformat(),
        metadatos={
            "id_archivo": id_archivo,
            "id_jornada": id_jornada,
            "correlation_id": correlation_id,
            "checksum_registrado": checksum_registrado,
        },
    )

    paginas = resultado["paginas"]
    lineas = resultado["lineas"]
    alertas = resultado["alertas"]

    if not isinstance(paginas, list):
        raise ValueError("Contrato V69 invalido: paginas.")

    if not isinstance(lineas, list):
        raise ValueError("Contrato V69 invalido: lineas.")

    if not isinstance(alertas, list):
        raise ValueError("Contrato V69 invalido: alertas.")

    if not paginas:
        raise ValueError("V69 no identifico paginas documentales.")

    if any(p.get("habilitado_f2_monetario") is not False for p in paginas):
        raise ValueError("Una pagina aparece habilitada para F2 monetario.")

    if any(l.get("habilitado_f2_monetario") is not False for l in lineas):
        raise ValueError("Una linea aparece habilitada para F2 monetario.")

    # 3. Persistencia atomica.

    paginas_nuevas = 0
    lineas_nuevas = 0
    alertas_nuevas = 0
    mapa_paginas = {}

    with connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    checksum_sha256,
                    estado,
                    fecha_contable
                FROM public.con_archivo_carga
                WHERE id_archivo = %s
                FOR UPDATE
            """, (id_archivo,))

            actual = cur.fetchone()

            if actual is None:
                raise ValueError("El archivo desaparecio de la BD.")

            if (
                actual[0].strip().lower() != checksum_calculado
                or actual[1] != "PROCESADO"
                or actual[2] != fecha_contable
            ):
                raise ValueError(
                    "Los metadatos cambiaron durante el procesamiento."
                )

            # 3.1 Paginas.

            for pagina in paginas:
                clave = (
                    pagina["nombre_hoja"],
                    pagina["pagina_logica"],
                )

                campos = (
                    id_archivo,
                    id_jornada,
                    correlation_id,
                    checksum_calculado,
                    pagina["nombre_hoja"],
                    pagina["familia"],
                    pagina.get("referencia_meet"),
                    pagina.get("codigo_cabecera"),
                    pagina["estado_identidad"],
                    pagina["pagina_logica"],
                    pagina.get("pagina_impresa"),
                    pagina["linea_inicio"],
                    pagina["linea_fin"],
                    pagina["filas_con_texto"],
                    pagina["filas_candidatas"],
                    _fecha(pagina.get("fecha_impresion")),
                    _fecha(pagina.get("fecha_proceso")),
                    _fecha(pagina.get("fecha_canje")),
                    _fecha(pagina.get("fecha_sistema")),
                    _fecha(pagina.get("fecha_reporte")),
                    _fecha(pagina.get("fecha_outclear")),
                    fecha_contable,
                    pagina["estado_fecha"],
                    pagina.get("codigo_vss"),
                    Jsonb(pagina["tipos_de_linea"]),
                    pagina["huella_sha256"],
                    False,
                )

                cur.execute("""
                    INSERT INTO public.con_carta_auxiliar_pagina (
                        id_archivo, id_jornada, correlation_id,
                        checksum_archivo, nombre_hoja, familia,
                        referencia_meet, codigo_cabecera,
                        estado_identidad, pagina_logica,
                        pagina_impresa, linea_inicio, linea_fin,
                        filas_con_texto, filas_candidatas,
                        fecha_impresion, fecha_proceso, fecha_canje,
                        fecha_sistema, fecha_reporte, fecha_outclear,
                        fecha_contable_objetivo, estado_fecha,
                        codigo_vss, tipos_de_linea, huella_sha256,
                        habilitado_f2_monetario
                    )
                    VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s
                    )
                    ON CONFLICT (
                        id_archivo, nombre_hoja, pagina_logica
                    ) DO NOTHING
                    RETURNING id_auxiliar_pagina
                """, campos)

                insertada = cur.fetchone()

                if insertada:
                    id_pagina = insertada[0]
                    paginas_nuevas += 1
                else:
                    cur.execute("""
                        SELECT
                            id_auxiliar_pagina,
                            huella_sha256,
                            checksum_archivo,
                            correlation_id,
                            id_jornada
                        FROM public.con_carta_auxiliar_pagina
                        WHERE id_archivo = %s
                          AND nombre_hoja = %s
                          AND pagina_logica = %s
                    """, (id_archivo, *clave))

                    existente = cur.fetchone()

                    if existente is None:
                        raise RuntimeError("No se pudo recuperar pagina.")

                    (
                        id_pagina,
                        huella,
                        checksum,
                        corr,
                        jornada,
                    ) = existente

                    if (
                        huella != pagina["huella_sha256"]
                        or checksum != checksum_calculado
                        or corr != correlation_id
                        or jornada != id_jornada
                    ):
                        raise RuntimeError(
                            f"Conflicto documental en pagina {clave}."
                        )

                mapa_paginas[clave] = id_pagina

            # 3.2 Lineas.

            for linea in lineas:
                clave = (
                    linea["nombre_hoja"],
                    linea["pagina_logica"],
                )

                id_pagina = mapa_paginas.get(clave)

                if id_pagina is None:
                    raise RuntimeError(
                        f"Pagina no encontrada para linea {clave}."
                    )

                cur.execute("""
                    INSERT INTO public.con_carta_auxiliar_linea (
                        id_auxiliar_pagina, id_archivo, id_jornada,
                        correlation_id, checksum_archivo,
                        nombre_hoja, familia, pagina_logica,
                        numero_linea, tipo_linea,
                        codigo_transaccion_literal, codigo_vss,
                        huella_sha256, habilitado_f2_monetario
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE)
                    ON CONFLICT (
                        id_auxiliar_pagina, numero_linea
                    ) DO NOTHING
                    RETURNING id_auxiliar_linea
                """, (
                    id_pagina,
                    id_archivo,
                    id_jornada,
                    correlation_id,
                    checksum_calculado,
                    linea["nombre_hoja"],
                    linea["familia"],
                    linea["pagina_logica"],
                    linea["numero_linea"],
                    linea["tipo_linea"],
                    linea.get("codigo_transaccion_literal"),
                    linea.get("codigo_vss"),
                    linea["huella_sha256"],
                ))

                insertada = cur.fetchone()

                if insertada:
                    lineas_nuevas += 1
                else:
                    cur.execute("""
                        SELECT huella_sha256, checksum_archivo
                        FROM public.con_carta_auxiliar_linea
                        WHERE id_auxiliar_pagina = %s
                          AND numero_linea = %s
                    """, (id_pagina, linea["numero_linea"]))

                    existente = cur.fetchone()

                    if (
                        existente is None
                        or existente[0] != linea["huella_sha256"]
                        or existente[1] != checksum_calculado
                    ):
                        raise RuntimeError(
                            "Conflicto documental en linea: "
                            f"{clave}/{linea['numero_linea']}"
                        )

            # 3.3 Alertas.

            for alerta in alertas:
                hoja = alerta.get("hoja")
                numero_pagina = alerta.get("pagina")

                id_pagina = None

                if hoja is not None and numero_pagina is not None:
                    id_pagina = mapa_paginas.get(
                        (hoja, numero_pagina)
                    )

                huella_alerta = _hash_alerta(alerta)

                cur.execute("""
                    INSERT INTO public.con_carta_auxiliar_alerta (
                        id_archivo, id_jornada, id_auxiliar_pagina,
                        correlation_id, checksum_archivo,
                        tipo_alerta, nombre_hoja, pagina_logica,
                        detalle, huella_sha256
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (
                        id_archivo, huella_sha256
                    ) DO NOTHING
                    RETURNING id_auxiliar_alerta
                """, (
                    id_archivo,
                    id_jornada,
                    id_pagina,
                    correlation_id,
                    checksum_calculado,
                    alerta["tipo"],
                    hoja,
                    numero_pagina,
                    Jsonb(alerta),
                    huella_alerta,
                ))

                if cur.fetchone():
                    alertas_nuevas += 1

            # 3.4 Control de cantidades e integridad.

            cur.execute("""
                SELECT
                    (SELECT COUNT(*)
                     FROM public.con_carta_auxiliar_pagina
                     WHERE id_archivo = %s),
                    (SELECT COUNT(*)
                     FROM public.con_carta_auxiliar_linea
                     WHERE id_archivo = %s),
                    (SELECT COUNT(*)
                     FROM public.con_carta_auxiliar_alerta
                     WHERE id_archivo = %s),
                    (SELECT COUNT(*)
                     FROM public.con_carta_auxiliar_pagina
                     WHERE id_archivo = %s
                       AND habilitado_f2_monetario = TRUE),
                    (SELECT COUNT(*)
                     FROM public.con_carta_auxiliar_linea
                     WHERE id_archivo = %s
                       AND habilitado_f2_monetario = TRUE)
            """, (
                id_archivo, id_archivo, id_archivo,
                id_archivo, id_archivo,
            ))

            cantidades = cur.fetchone()

            esperadas = (
                len(paginas),
                len(lineas),
                len(alertas),
                0,
                0,
            )

            if tuple(cantidades) != esperadas:
                raise RuntimeError(
                    f"Conteos inconsistentes: "
                    f"BD={cantidades}, extractor={esperadas}"
                )


            # 3.5 Evento de trazabilidad en la misma transaccion.
            evento_detalle = json.dumps(
                {
                    "paginas": len(paginas),
                    "lineas": len(lineas),
                    "alertas": len(alertas),
                    "checksum_archivo": checksum_calculado,
                    "fecha_contable": fecha_contable.isoformat(),
                    "habilitado_f2_monetario": False,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )

            cur.execute("""
                SELECT detalle
                FROM public.con_trazabilidad
                WHERE id_archivo = %s
                  AND id_jornada = %s
                  AND correlation_id = %s
                  AND tipo_evento = 'CARTA_AUXILIAR_V69_PERSISTIDO'
                  AND componente = 'PERSISTENCIA_CARTA_AUXILIAR_V69'
                FOR UPDATE
            """, (id_archivo, id_jornada, correlation_id))

            eventos_v69 = cur.fetchall()

            if len(eventos_v69) > 1:
                raise RuntimeError(
                    "Existen eventos V69 duplicados para el archivo."
                )

            evento_nuevo = False

            if eventos_v69:
                if eventos_v69[0][0] != evento_detalle:
                    raise RuntimeError(
                        "El evento V69 existente tiene contenido incompatible."
                    )
            else:
                cur.execute("""
                    INSERT INTO public.con_trazabilidad (
                        correlation_id,
                        id_archivo,
                        id_jornada,
                        tipo_evento,
                        componente,
                        detalle
                    )
                    VALUES (
                        %s, %s, %s,
                        'CARTA_AUXILIAR_V69_PERSISTIDO',
                        'PERSISTENCIA_CARTA_AUXILIAR_V69',
                        %s
                    )
                """, (
                    correlation_id,
                    id_archivo,
                    id_jornada,
                    evento_detalle,
                ))

                evento_nuevo = True

            idempotente = (
                paginas_nuevas == 0
                and lineas_nuevas == 0
                and alertas_nuevas == 0
                and not evento_nuevo
            )

            if dry_run:
                conn.rollback()

    return {
        "id_archivo": id_archivo,
        "id_jornada": id_jornada,
        "checksum": checksum_calculado,
        "paginas": len(paginas),
        "lineas": len(lineas),
        "alertas": len(alertas),
        "paginas_nuevas": paginas_nuevas,
        "lineas_nuevas": lineas_nuevas,
        "alertas_nuevas": alertas_nuevas,
        "evento_trazabilidad_nuevo": evento_nuevo,
        "idempotente": idempotente,
        "habilitacion_monetaria": False,
        "simulacion": dry_run,
        "resultado": "ROLLBACK" if dry_run else "COMMIT",
    }
