"""Host Loader para HA22, HA26 y HA32."""

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from app.batch.clasificacion_errores import clasificar_error
from app.batch.bloqueo_host import bloqueo_host
from app.repositories.database import connection
from app.services.procesamiento_host import procesar_host

TIPOS_HOST = ("HA22", "HA26", "HA32")

logger = logging.getLogger(__name__)


def consultar_pendientes(limite=100):
    """Consulta archivos Host recibidos y asociados."""

    if not 1 <= limite <= 1000:
        raise ValueError("Limite fuera del rango permitido")

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    a.id_archivo,
                    a.tipo_archivo,
                    a.fecha_contable,
                    a.nombre_archivo
                FROM con_archivo_carga a
                JOIN con_insumo_esperado i
                  ON i.id_archivo = a.id_archivo
                JOIN con_jornada j
                  ON j.id_jornada = i.id_jornada
                WHERE a.tipo_archivo IN ('HA22', 'HA26', 'HA32')
                  AND i.tipo_insumo = a.tipo_archivo
                  AND a.estado = 'RECIBIDO'
                  AND i.estado = 'RECIBIDO'
                  AND a.fecha_contable = j.fecha_contable
                ORDER BY
                    a.fecha_contable,
                    a.id_archivo
                LIMIT %s
            """, (limite,))

            return [
                {
                    "id_archivo": fila[0],
                    "tipo_archivo": fila[1],
                    "fecha_contable": fila[2].isoformat(),
                    "nombre_archivo": fila[3],
                }
                for fila in cur.fetchall()
            ]


def _ejecutar_lote(*, limite=100, ejecutar=False):
    """Ejecuta el lote o presenta un diagnostico."""
    inicio_monotonic = time.monotonic()
    inicio = datetime.now(timezone.utc)
    id_ejecucion = str(uuid4())


    pendientes = consultar_pendientes(limite)

    resumen = {
        "id_ejecucion": id_ejecucion,
        "inicio": inicio.isoformat(),
        "modo": "EJECUCION" if ejecutar else "DIAGNOSTICO",
        "total_pendientes": len(pendientes),
        "procesados": 0,
        "fallidos": 0,
        "resultados": [],
    }

    for archivo in pendientes:
        id_archivo = archivo["id_archivo"]

        if not ejecutar:
            resumen["resultados"].append({
                **archivo,
                "accion": "PENDIENTE_PROCESAMIENTO",
            })
            continue

        try:
            resultado = procesar_host(id_archivo)

            resumen["procesados"] += 1
            resumen["resultados"].append(resultado)

        except Exception as exc:
            logger.exception(
                "Error procesando Host id_archivo=%s",
                id_archivo,
            )

            clasificacion = clasificar_error(exc)

            resumen["fallidos"] += 1
            resumen["resultados"].append({
                "id_archivo": id_archivo,
                "tipo_archivo": archivo["tipo_archivo"],
                "estado": "ERROR",
                "categoria": clasificacion["categoria"],
                "codigo": clasificacion["codigo"],
                "reintentable": clasificacion["reintentable"],
            })

    fin = datetime.now(timezone.utc)

    resumen["fin"] = fin.isoformat()
    resumen["duracion_ms"] = round(
        (time.monotonic() - inicio_monotonic) * 1000,
        2,
    )

    if resumen["fallidos"] == 0:
        resumen["estado_ejecucion"] = "FINALIZADO"
    elif resumen["procesados"] > 0:
        resumen["estado_ejecucion"] = "PARCIAL"
    else:
        resumen["estado_ejecucion"] = "ERROR"

    return resumen



def ejecutar_host_loader(*, limite=100, ejecutar=False):
    """Ejecuta el lote bajo bloqueo cuando corresponde."""

    if not ejecutar:
        return _ejecutar_lote(
            limite=limite,
            ejecutar=False,
        )

    with bloqueo_host():
        return _ejecutar_lote(
            limite=limite,
            ejecutar=True,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Host Loader - Concilia V1"
    )
    parser.add_argument(
        "--ejecutar",
        action="store_true",
        help="Procesar archivos recibidos",
    )
    parser.add_argument(
        "--limite",
        type=int,
        default=100,
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    resumen = ejecutar_host_loader(
        limite=args.limite,
        ejecutar=args.ejecutar,
    )

    print(json.dumps(
        resumen,
        ensure_ascii=False,
        indent=2,
    ))

    if resumen["fallidos"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
