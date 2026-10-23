import pytest

from app.batch import host_loader


def archivos_prueba():
    return [
        {
            "id_archivo": 101,
            "tipo_archivo": "HA22",
            "fecha_contable": "2026-10-21",
            "nombre_archivo": "DESCARHA22_F261021.TXT",
        },
        {
            "id_archivo": 102,
            "tipo_archivo": "HA26",
            "fecha_contable": "2026-10-21",
            "nombre_archivo": "DESCARHA26_F261021.TXT",
        },
    ]


def test_diagnostico_no_procesa(monkeypatch):
    monkeypatch.setattr(
        host_loader,
        "consultar_pendientes",
        lambda limite: archivos_prueba(),
    )

    def prohibido(_):
        raise AssertionError("No debe procesar")

    monkeypatch.setattr(
        host_loader,
        "procesar_host",
        prohibido,
    )

    resultado = host_loader.ejecutar_host_loader(
        limite=100,
        ejecutar=False,
    )

    assert resultado["modo"] == "DIAGNOSTICO"
    assert resultado["total_pendientes"] == 2
    assert resultado["procesados"] == 0
    assert resultado["fallidos"] == 0
    assert len(resultado["resultados"]) == 2


def test_procesamiento_exitoso(monkeypatch):
    monkeypatch.setattr(
        host_loader,
        "consultar_pendientes",
        lambda limite: archivos_prueba(),
    )

    ejecutados = []

    def procesar(id_archivo):
        ejecutados.append(id_archivo)
        return {
            "id_archivo": id_archivo,
            "estado": "PROCESADO",
            "registros": 1,
            "idempotente": False,
        }

    monkeypatch.setattr(
        host_loader,
        "procesar_host",
        procesar,
    )

    resultado = host_loader.ejecutar_host_loader(
        limite=100,
        ejecutar=True,
    )

    assert ejecutados == [101, 102]
    assert resultado["procesados"] == 2
    assert resultado["fallidos"] == 0


def test_continua_despues_de_error(monkeypatch):
    monkeypatch.setattr(
        host_loader,
        "consultar_pendientes",
        lambda limite: archivos_prueba(),
    )

    ejecutados = []

    def procesar(id_archivo):
        ejecutados.append(id_archivo)

        if id_archivo == 101:
            raise RuntimeError("Fallo simulado")

        return {
            "id_archivo": id_archivo,
            "estado": "PROCESADO",
            "registros": 1,
            "idempotente": False,
        }

    monkeypatch.setattr(
        host_loader,
        "procesar_host",
        procesar,
    )

    resultado = host_loader.ejecutar_host_loader(
        ejecutar=True,
    )

    assert ejecutados == [101, 102]
    assert resultado["procesados"] == 1
    assert resultado["fallidos"] == 1
    assert resultado["resultados"][0]["estado"] == "ERROR"


@pytest.mark.parametrize("limite", [0, -1, 1001])
def test_limite_invalido(limite):
    with pytest.raises(ValueError):
        host_loader.consultar_pendientes(limite)


def test_ejecucion_adquiere_bloqueo(monkeypatch):
    from contextlib import contextmanager

    eventos = []

    @contextmanager
    def bloqueo_simulado():
        eventos.append("BLOQUEO_ADQUIRIDO")
        try:
            yield
        finally:
            eventos.append("BLOQUEO_LIBERADO")

    def lote_simulado(*, limite, ejecutar):
        eventos.append("LOTE_EJECUTADO")
        return {"procesados": 0, "fallidos": 0}

    monkeypatch.setattr(
        host_loader, "bloqueo_host", bloqueo_simulado
    )
    monkeypatch.setattr(
        host_loader, "_ejecutar_lote", lote_simulado
    )

    host_loader.ejecutar_host_loader(ejecutar=True)

    assert eventos == [
        "BLOQUEO_ADQUIRIDO",
        "LOTE_EJECUTADO",
        "BLOQUEO_LIBERADO",
    ]


def test_diagnostico_no_adquiere_bloqueo(monkeypatch):
    def bloqueo_prohibido():
        raise AssertionError("No debe adquirir bloqueo")

    monkeypatch.setattr(
        host_loader, "bloqueo_host", bloqueo_prohibido
    )

    monkeypatch.setattr(
        host_loader,
        "_ejecutar_lote",
        lambda **kwargs: {"modo": "DIAGNOSTICO"},
    )

    resultado = host_loader.ejecutar_host_loader(
        ejecutar=False
    )

    assert resultado["modo"] == "DIAGNOSTICO"


def test_bloqueo_ocupado_postgresql(monkeypatch):
    import os

    from app.repositories.database import connection
    from app.batch.bloqueo_host import (
        bloqueo_host,
        HostLoaderOcupado,
    )

    if os.environ.get("DB_NAME") != "concilia_test":
        pytest.skip("Requiere concilia_test")

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == "concilia_test"

    def lote_prohibido(*, limite, ejecutar):
        raise AssertionError(
            "No debe ejecutarse con bloqueo ocupado"
        )

    monkeypatch.setattr(
        host_loader,
        "_ejecutar_lote",
        lote_prohibido,
    )

    with bloqueo_host():
        with pytest.raises(HostLoaderOcupado):
            host_loader.ejecutar_host_loader(
                ejecutar=True
            )


def test_bloqueo_liberado_tras_excepcion():
    import os

    from app.repositories.database import connection
    from app.batch.bloqueo_host import bloqueo_host

    if os.environ.get("DB_NAME") != "concilia_test":
        pytest.skip("Requiere concilia_test")

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == "concilia_test"

    with pytest.raises(
        RuntimeError,
        match="FALLO_CONTROLADO_BATCH",
    ):
        with bloqueo_host():
            raise RuntimeError("FALLO_CONTROLADO_BATCH")

    # Debe poder adquirirse nuevamente.
    with bloqueo_host():
        pass


@pytest.mark.parametrize(
    "fallos,estado_esperado",
    [
        (set(), "FINALIZADO"),
        ({101}, "PARCIAL"),
        ({101, 102}, "ERROR"),
    ],
)
def test_observabilidad_estados(
    monkeypatch, fallos, estado_esperado
):
    from datetime import datetime
    from uuid import UUID

    monkeypatch.setattr(
        host_loader,
        "consultar_pendientes",
        lambda limite: archivos_prueba(),
    )

    def procesar(id_archivo):
        if id_archivo in fallos:
            raise RuntimeError("Fallo simulado")

        return {
            "id_archivo": id_archivo,
            "estado": "PROCESADO",
            "registros": 1,
            "idempotente": False,
        }

    monkeypatch.setattr(
        host_loader,
        "procesar_host",
        procesar,
    )

    resultado = host_loader._ejecutar_lote(
        limite=100,
        ejecutar=True,
    )

    UUID(resultado["id_ejecucion"])

    inicio = datetime.fromisoformat(resultado["inicio"])
    fin = datetime.fromisoformat(resultado["fin"])

    assert inicio.tzinfo is not None
    assert fin.tzinfo is not None
    assert fin >= inicio

    assert resultado["duracion_ms"] >= 0
    assert resultado["estado_ejecucion"] == estado_esperado
    assert resultado["total_pendientes"] == 2
    assert resultado["procesados"] == 2 - len(fallos)
    assert resultado["fallidos"] == len(fallos)


def test_error_funcional_clasificado(monkeypatch):
    from app.services.procesamiento_host import (
        ProcesamientoHostError,
    )

    monkeypatch.setattr(
        host_loader,
        "consultar_pendientes",
        lambda limite: archivos_prueba()[:1],
    )

    def procesar(_):
        raise ProcesamientoHostError(
            "Checksum del archivo fisico no corresponde"
        )

    monkeypatch.setattr(
        host_loader,
        "procesar_host",
        procesar,
    )

    resultado = host_loader._ejecutar_lote(
        limite=100,
        ejecutar=True,
    )

    assert resultado["fallidos"] == 1
    assert resultado["estado_ejecucion"] == "ERROR"

    error = resultado["resultados"][0]

    assert error["estado"] == "ERROR"
    assert error["categoria"] == "FUNCIONAL"
    assert error["codigo"] == "CHECKSUM_INVALIDO"
    assert error["reintentable"] is False
