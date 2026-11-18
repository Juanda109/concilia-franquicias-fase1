"""Cobertura monetaria Host de solo lectura."""
from decimal import Decimal
from app.repositories.database import connection

FUENTES = ("HA22", "HA26", "HA32")
CERO = Decimal("0.00")


def calcular_monetario_host(id_jornada, cuentas):
    resultado = {
        str(cuenta): {
            fuente: {
                "debe": "0.00",
                "haber": "0.00",
                "neto": "0.00",
                "cantidad": 0,
                "estado": "SIN_MOVIMIENTOS",
            }
            for fuente in FUENTES
        }
        for cuenta in cuentas
    }

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("""
                SELECT h.id_host_resultado, h.cuenta,
                       h.centro, h.tx_host,
                       h.valor_debe, h.valor_haber
                FROM public.con_host_resultado h
                WHERE EXISTS (
                    SELECT 1
                    FROM public.con_insumo_esperado i
                    WHERE i.id_jornada = %s
                      AND i.id_archivo = h.id_archivo
                )
                ORDER BY h.id_host_resultado
            """, (id_jornada,))
            filas = cur.fetchall()

    acumulado = {}
    vistos = set()

    for identificador, cuenta, centro, fuente, debe, haber in filas:
        cuenta = str(cuenta).strip()
        fuente = str(fuente).strip().upper()
        centro = "" if centro is None else str(centro).strip()

        if identificador in vistos:
            continue
        vistos.add(identificador)

        if cuenta not in resultado:
            continue
        if fuente not in FUENTES:
            continue
        if centro not in ("", "17", "0017"):
            continue

        clave = (cuenta, fuente)
        grupo = acumulado.setdefault(
            clave,
            {"debe": CERO, "haber": CERO,
             "cantidad": 0, "incompleto": False}
        )

        grupo["cantidad"] += 1

        if debe is None or haber is None:
            grupo["incompleto"] = True

        if debe is not None:
            grupo["debe"] += Decimal(str(debe))
        if haber is not None:
            grupo["haber"] += Decimal(str(haber))

    for (cuenta, fuente), grupo in acumulado.items():
        destino = resultado[cuenta][fuente]
        destino["cantidad"] = grupo["cantidad"]

        if grupo["incompleto"]:
            destino["estado"] = "DATO_INCOMPLETO"
            destino["debe"] = None
            destino["haber"] = None
            destino["neto"] = None
        else:
            destino["estado"] = "CON_MOVIMIENTOS"
            destino["debe"] = str(grupo["debe"])
            destino["haber"] = str(grupo["haber"])
            destino["neto"] = str(
                grupo["debe"] - grupo["haber"]
            )

    return resultado
