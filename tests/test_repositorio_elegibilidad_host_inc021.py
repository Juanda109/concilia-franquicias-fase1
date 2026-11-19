"""Compatibilidad del repositorio INC021 con el catalogo Host."""

from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.repositories import elegibilidad_host_inc021 as repo


COLUMNAS = [
    "id_host_resultado", "id_jornada", "id_archivo",
    "fecha_contable", "tx_host", "cuenta", "centro",
    "referencia", "concepto", "valor_debe", "valor_haber",
    "valor_normalizado", "linea_origen", "correlation_id",
    "nombre_archivo", "proceso_origen", "estado_archivo",
    "checksum_sha256",
]

CUENTAS = ["259095341", "299095870", "299095303"]

ARCHIVOS = {
    "HA22": 3455,
    "HA26": 3456,
    "HA32": 3457,
}

CUENTA_FUENTE = {
    "HA22": "259095341",
    "HA26": "299095870",
    "HA32": "299095303",
}


def fila(fuente, referencia, concepto, identificador,
         nombre_archivo="MUESTRA_HOST.txt"):
    return (
        identificador, 3836, ARCHIVOS[fuente],
        date(2026, 10, 26), fuente, CUENTA_FUENTE[fuente],
        "17", referencia, concepto,
        Decimal("3468266.00"), Decimal("0.00"),
        Decimal("3468266.00"), 4, "TEST",
        nombre_archivo, "HOST", "PROCESADO", "checksum-test",
    )


def ejecutar(filas):
    cursor = MagicMock()
    cursor.description = []

    for nombre in COLUMNAS:
        descripcion = MagicMock()
        descripcion.name = nombre
        cursor.description.append(descripcion)

    cursor.fetchall.return_value = filas

    conexion = MagicMock()
    conexion.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def conexion_simulada():
        yield conexion

    with patch.object(repo, "connection", conexion_simulada):
        resultado = repo.consultar_elegibilidad_host(
            3836, CUENTAS
        )

    return resultado, cursor


def test_clasificacion_por_fuente():
    filas = [
        fila("HA22", "S", "PRUEBA SINTETICA", 1),
        fila("HA26", "S", "PRUEBA SINTETICA", 2),
        fila("HA32", None, None, 3),
    ]

    resultado, cursor = ejecutar(filas)
    resumen = resultado["resumen_por_fuente"]

    assert resultado["total_movimientos"] == 3
    assert resumen["HA22"]["sinteticos"] == 1
    assert resumen["HA26"]["sinteticos"] == 1
    assert resumen["HA32"]["origen_no_verificado"] == 1

    assert resultado["certificado"] is False
    assert resultado["conciliado_host"] is False
    assert resultado["homologado_contablemente"] is False

    assert cursor.execute.call_count == 2
    assert cursor.execute.call_args_list[0].args[0] == (
        "SET TRANSACTION READ ONLY"
    )


def test_sin_movimientos():
    resultado, _ = ejecutar([])

    assert resultado["total_movimientos"] == 0

    for fuente in repo.FUENTES:
        assert resultado["resumen_por_fuente"][fuente][
            "movimientos"
        ] == 0


def test_trazabilidad():
    resultado, _ = ejecutar([
        fila("HA22", "S", "PRUEBA SINTETICA", 99)
    ])

    movimiento = resultado["movimientos"][0]

    assert movimiento["id_host_resultado"] == 99
    assert movimiento["id_archivo"] == 3455
    assert movimiento["linea_origen"] == 4
    assert movimiento["cuenta"] == "259095341"
    assert movimiento["tx_host"] == "HA22"
    assert movimiento["puede_homologar"] is False


@pytest.mark.parametrize(
    "jornada,cuentas",
    [
        (0, ["259095341"]),
        (-1, ["259095341"]),
        ("3836", ["259095341"]),
        (True, ["259095341"]),
        (3836, []),
        (3836, [""]),
        (3836, [None]),
        (3836, ["299095038"]),
    ],
)
def test_parametros_invalidos(jornada, cuentas):
    with pytest.raises(ValueError):
        repo.consultar_elegibilidad_host(jornada, cuentas)


def test_consulta_parametrizada():
    resultado, cursor = ejecutar([])

    sql, parametros = cursor.execute.call_args.args

    assert "unnest(%s::text[], %s::text[])" in sql
    assert "p.tx_host = h.tx_host" in sql
    assert "p.cuenta = h.cuenta" in sql
    assert "i.id_jornada = %s" in sql

    fuentes, cuentas, jornada = parametros

    assert jornada == 3836

    pares = set(zip(fuentes, cuentas))

    assert pares == {
        ("HA22", "259095341"),
        ("HA26", "299095870"),
        ("HA32", "299095303"),
    }

    assert len(fuentes) == len(cuentas) == 3
    assert set(map(tuple, resultado["pares_consultados"])) == pares


def test_archivo_prueba_ha32():
    resultado, _ = ejecutar([
        fila(
            "HA32", None, None, 7,
            "HA32_F261026_PRUEBA.txt",
        )
    ])

    movimiento = resultado["movimientos"][0]

    assert movimiento["estado"] == "SINTETICO"
    assert movimiento["motivo"] == "MARCADOR_PRUEBA_ARCHIVO"
    assert movimiento["puede_homologar"] is False


def test_doble_fuente_conservada():
    resultado, cursor = ejecutar([])

    with patch.object(repo, "connection") as conexion:
        conexion.return_value.__enter__.return_value = MagicMock()
        # El catalogo se verifica directamente, sin ejecutar SQL.
        from app.services.fase2.catalogo_host_cuenta_inc021 import (
            pares_para_cuentas,
        )
        pares = pares_para_cuentas(["299095302", "196095001838"])

    assert set(pares) == {
        ("HA22", "299095302"),
        ("HA32", "299095302"),
        ("HA22", "196095001838"),
        ("HA32", "196095001838"),
    }
