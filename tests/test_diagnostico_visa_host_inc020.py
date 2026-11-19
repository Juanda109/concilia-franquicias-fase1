from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.api import diagnostico_visa_host_inc020 as api

RUTA = "/api/v1/jornadas/3836/visa/diagnostico-host"

CUENTAS = {"259095341", "299095888", "299095303"}

ARCHIVOS = {
    "HA22": 3455,
    "HA26": 3456,
    "HA32": 3457,
}


def ejecutar(completa=False):
    fuentes = {
        fuente: {
            "archivos": [archivo],
            "cuentas": {},
        }
        for fuente, archivo in ARCHIVOS.items()
    }

    cobertura = {
        fuente: {
            "presentes": sorted(CUENTAS) if completa else [],
            "ausentes": [] if completa else sorted(CUENTAS),
        }
        for fuente in ARCHIVOS
    }

    with (
        patch.object(
            api,
            "recuperar_vss",
            return_value=(
                {
                    "id_archivo": 3460,
                    "fecha_contable": date(2026, 10, 26),
                },
                "VSS_SIMULADO",
            ),
        ),
        patch.object(
            api,
            "integrar_vss",
            return_value={
                "resumen_monetario": {
                    "liquidacion_neta_usd": "529630.06",
                    "liquidacion_neta_cop": None,
                }
            },
        ),
        patch.object(
            api,
            "consultar_host",
            return_value=(fuentes, cobertura, completa),
        ),
    ):
        with TestClient(app) as cliente:
            return cliente.get(RUTA)


def test_cobertura_insuficiente():
    respuesta = ejecutar()

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["estado"] == "COBERTURA_HOST_VISA_INSUFICIENTE"
    assert datos["visa"]["id_archivo"] == 3460

    for fuente in ARCHIVOS:
        assert set(datos["cobertura"][fuente]["ausentes"]) == CUENTAS
        assert datos["host"][fuente]["cuentas"] == {}

    assert datos["diferencia_contable"] is None
    assert datos["certificado"] is False
    assert datos["conciliado_host"] is False
    assert datos["homologado_contablemente"] is False


def test_cobertura_completa_no_homologa():
    respuesta = ejecutar(completa=True)

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["estado"] == "PENDIENTE_HOMOLOGACION"
    assert datos["diferencia_contable"] is None
    assert datos["certificado"] is False
    assert datos["conciliado_host"] is False
    assert datos["homologado_contablemente"] is False


def test_jornada_invalida():
    with TestClient(app) as cliente:
        respuesta = cliente.get(
            "/api/v1/jornadas/0/visa/diagnostico-host"
        )

    assert respuesta.status_code == 422


def test_inc020_consultar_host_sin_archivos():
    from unittest.mock import MagicMock

    cursor = MagicMock()
    cursor.fetchall.return_value = []

    conexion = MagicMock()
    conexion.cursor.return_value.__enter__.return_value = cursor

    from contextlib import contextmanager

    @contextmanager
    def conexion_simulada():
        yield conexion

    with patch.object(api, "connection", conexion_simulada):
        fuentes, cobertura, completa = api.consultar_host(3836)

    assert completa is False

    for fuente in api.FUENTES:
        assert fuentes[fuente]["archivos"] == []
        assert fuentes[fuente]["cuentas"] == {}
        assert set(cobertura[fuente]["ausentes"]) == set(api.CUENTAS_VISA)


def test_inc020_consultar_host_con_movimientos():
    from unittest.mock import MagicMock
    from decimal import Decimal
    from contextlib import contextmanager

    filas = [
        (
            "HA22", 3455, "259095341", 2,
            Decimal("1000.00"), Decimal("100.00"),
        ),
        (
            "HA26", 3456, "259095341", 2,
            Decimal("1000.00"), Decimal("100.00"),
        ),
        (
            "HA32", 3457, "259095341", 2,
            Decimal("1000.00"), Decimal("100.00"),
        ),
    ]

    cursor = MagicMock()
    cursor.fetchall.return_value = filas

    conexion = MagicMock()
    conexion.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def conexion_simulada():
        yield conexion

    with patch.object(api, "connection", conexion_simulada):
        fuentes, cobertura, completa = api.consultar_host(3836)

    assert completa is False

    for fuente in api.FUENTES:
        cuenta = fuentes[fuente]["cuentas"]["259095341"]

        assert cuenta["movimientos"] == 2
        assert cuenta["debe_cop"] == "1000.00"
        assert cuenta["haber_cop"] == "100.00"
        assert cuenta["neto_cop"] == "900.00"

        assert set(cobertura[fuente]["ausentes"]) == {
            "299095888",
            "299095303",
        }


def test_inc020_cobertura_completa_repositorio():
    from contextlib import contextmanager
    from decimal import Decimal
    from unittest.mock import MagicMock

    filas = [
        (
            fuente, ARCHIVOS[fuente], cuenta, 1,
            Decimal("1000.00"), Decimal("100.00"),
        )
        for fuente in api.FUENTES
        for cuenta in api.CUENTAS_VISA
    ]

    cursor = MagicMock()
    cursor.fetchall.return_value = filas

    conexion = MagicMock()
    conexion.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def conexion_simulada():
        yield conexion

    with patch.object(api, "connection", conexion_simulada):
        fuentes, cobertura, completa = api.consultar_host(3836)

    assert completa is True

    for fuente in api.FUENTES:
        assert len(fuentes[fuente]["cuentas"]) == 3
        assert cobertura[fuente]["ausentes"] == []


def test_inc020_error_postgresql():
    from psycopg import OperationalError

    with (
        patch.object(
            api,
            "recuperar_vss",
            return_value=(
                {
                    "id_archivo": 3460,
                    "fecha_contable": date(2026, 10, 26),
                },
                "VSS_SIMULADO",
            ),
        ),
        patch.object(
            api,
            "integrar_vss",
            return_value={"resumen_monetario": {}},
        ),
        patch.object(
            api,
            "consultar_host",
            side_effect=OperationalError("Error simulado"),
        ),
    ):
        with TestClient(app) as cliente:
            respuesta = cliente.get(RUTA)

    assert respuesta.status_code == 503


def test_inc020_sin_archivo_vss():
    from fastapi import HTTPException

    with patch.object(
        api,
        "recuperar_vss",
        side_effect=HTTPException(404, "VSS inexistente"),
    ):
        with TestClient(app) as cliente:
            respuesta = cliente.get(RUTA)

    assert respuesta.status_code == 404
