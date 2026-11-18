from app.services import procesamiento_host_completo as servicio


def test_coordinador_ejecuta_ambas_etapas(monkeypatch):
    llamadas = []

    def host(id_archivo):
        llamadas.append(("HOST", id_archivo))
        return {
            "id_archivo": id_archivo,
            "tipo_archivo": "HA22",
            "registros": 8,
            "idempotente": False,
        }

    def detalle(id_archivo):
        llamadas.append(("DETALLE", id_archivo))
        return {
            "id_archivo": id_archivo,
            "tipo": "HA22",
            "registros": 8,
            "idempotente": False,
        }

    monkeypatch.setattr(
        "app.services.procesamiento_host.procesar_host", host
    )
    monkeypatch.setattr(
        "app.services.persistencia_detalle.persistir_detalle", detalle
    )
    monkeypatch.setattr(
        servicio,
        "_verificar_persistencias",
        lambda *args: {
            "id_jornada": 100,
            "normalizados": 8,
            "detalles": 8,
            "lineas_distintas": 8,
            "eventos_host": 1,
            "eventos_detalle": 1,
        },
    )

    resultado = servicio.procesar_host_completo(101)

    assert llamadas == [
        ("HOST", 101),
        ("DETALLE", 101),
    ]
    assert resultado["estado"] == "HOST_COMPLETO"
    assert resultado["registros"] == 8
    assert resultado["idempotente"] is False


def test_coordinador_reconoce_reprocesamiento_idempotente(monkeypatch):
    monkeypatch.setattr(
        "app.services.procesamiento_host.procesar_host",
        lambda _: {
            "id_archivo": 101,
            "tipo_archivo": "HA26",
            "registros": 8,
            "idempotente": True,
        },
    )
    monkeypatch.setattr(
        "app.services.persistencia_detalle.persistir_detalle",
        lambda _: {
            "id_archivo": 101,
            "tipo": "HA26",
            "registros": 8,
            "idempotente": True,
        },
    )
    monkeypatch.setattr(
        servicio,
        "_verificar_persistencias",
        lambda *args: {
            "id_jornada": 100,
            "normalizados": 8,
            "detalles": 8,
            "lineas_distintas": 8,
            "eventos_host": 1,
            "eventos_detalle": 1,
        },
    )

    resultado = servicio.procesar_host_completo(101)

    assert resultado["estado"] == "HOST_COMPLETO"
    assert resultado["idempotente"] is True


def test_coordinador_rechaza_cantidades_diferentes(monkeypatch):
    monkeypatch.setattr(
        "app.services.procesamiento_host.procesar_host",
        lambda _: {
            "id_archivo": 101,
            "tipo_archivo": "HA32",
            "registros": 8,
            "idempotente": False,
        },
    )
    monkeypatch.setattr(
        "app.services.persistencia_detalle.persistir_detalle",
        lambda _: {
            "id_archivo": 101,
            "tipo": "HA32",
            "registros": 7,
            "idempotente": False,
        },
    )

    import pytest

    with pytest.raises(servicio.ProcesamientoHostCompletoError):
        servicio.procesar_host_completo(101)


def test_coordinador_rechaza_tipo_incompatible(monkeypatch):
    monkeypatch.setattr(
        "app.services.procesamiento_host.procesar_host",
        lambda _: {
            "id_archivo": 101,
            "tipo_archivo": "CAET",
            "registros": 8,
            "idempotente": False,
        },
    )

    import pytest

    with pytest.raises(servicio.ProcesamientoHostCompletoError):
        servicio.procesar_host_completo(101)


@__import__("pytest").mark.parametrize("id_archivo", [0, -1, True, "101", None])
def test_coordinador_rechaza_identificadores_invalidos(id_archivo):
    import pytest

    with pytest.raises(servicio.ProcesamientoHostCompletoError):
        servicio.procesar_host_completo(id_archivo)
