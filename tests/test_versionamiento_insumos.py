import pytest

from app.services.versionamiento_insumos import (
    VersionamientoInsumoError,
    decidir_recepcion,
)


def test_primera_recepcion_no_es_una_nueva_version():
    assert decidir_recepcion(
        estado_insumo="PENDIENTE",
        estado_archivo=None,
        id_archivo_actual=None,
    ) == "INICIAL"


def test_archivo_procesado_requiere_nueva_version_explicita():
    with pytest.raises(VersionamientoInsumoError, match="nueva_version=true"):
        decidir_recepcion(
            estado_insumo="PROCESADO",
            estado_archivo="PROCESADO",
            id_archivo_actual=100,
        )


def test_archivo_procesado_admite_nueva_version_con_motivo():
    assert decidir_recepcion(
        estado_insumo="PROCESADO",
        estado_archivo="PROCESADO",
        id_archivo_actual=100,
        nueva_version=True,
        motivo_version="Actualizacion de extracto Host autorizada",
    ) == "NUEVA_VERSION"


@pytest.mark.parametrize("motivo", [None, "", "   "])
def test_nueva_version_procesada_exige_motivo(motivo):
    with pytest.raises(VersionamientoInsumoError, match="motivo_version es obligatorio"):
        decidir_recepcion(
            estado_insumo="PROCESADO",
            estado_archivo="PROCESADO",
            id_archivo_actual=100,
            nueva_version=True,
            motivo_version=motivo,
        )


def test_motivo_no_supera_500_caracteres():
    with pytest.raises(VersionamientoInsumoError, match="500 caracteres"):
        decidir_recepcion(
            estado_insumo="PROCESADO",
            estado_archivo="PROCESADO",
            id_archivo_actual=100,
            nueva_version=True,
            motivo_version="x" * 501,
        )


def test_archivo_recibido_conserva_reemplazo_compatible_f1():
    assert decidir_recepcion(
        estado_insumo="RECIBIDO",
        estado_archivo="RECIBIDO",
        id_archivo_actual=100,
    ) == "REEMPLAZO_RECIBIDO"


def test_archivo_recibido_puede_versionarse_expresamente():
    assert decidir_recepcion(
        estado_insumo="RECIBIDO",
        estado_archivo="RECIBIDO",
        id_archivo_actual=100,
        nueva_version=True,
        motivo_version="Se recibe archivo corregido",
    ) == "NUEVA_VERSION"


def test_estados_incompatibles_no_se_normalizan_implicitamente():
    with pytest.raises(VersionamientoInsumoError, match="incompatibles"):
        decidir_recepcion(
            estado_insumo="PROCESADO",
            estado_archivo="RECIBIDO",
            id_archivo_actual=100,
            nueva_version=True,
            motivo_version="Correccion",
        )


def test_no_se_puede_marcar_version_en_primera_recepcion():
    with pytest.raises(VersionamientoInsumoError, match="sin archivo previo"):
        decidir_recepcion(
            estado_insumo="PENDIENTE",
            estado_archivo=None,
            id_archivo_actual=None,
            nueva_version=True,
            motivo_version="Primera carga",
        )
