import pytest

from app.services.fase2.homologacion_visa_inc021 import (
    CONCEPTOS,
    HomologacionNoAprobada,
    ReglaHomologacion,
    calcular_diferencia,
    estado_inc021,
    matriz_pendiente,
    validar_homologacion,
)


def test_matriz_sin_correspondencias():
    reglas = matriz_pendiente()

    assert len(reglas) == 4
    assert {r.concepto for r in reglas} == set(CONCEPTOS)

    for regla in reglas:
        assert regla.cuenta_host is None
        assert regla.fuente_host is None
        assert regla.signo is None
        assert regla.formula is None
        assert regla.tolerancia is None
        assert regla.aprobada is False


def test_rechaza_regla_pendiente():
    for regla in matriz_pendiente():
        with pytest.raises(HomologacionNoAprobada):
            validar_homologacion(regla)


def test_rechaza_regla_completada_sin_aprobacion():
    regla = ReglaHomologacion(
        concepto="LIQUIDACION_NETA_COP",
        moneda="COP",
        cuenta_host="259095341",
        fuente_host="HA22",
        signo="DEBE_MENOS_HABER",
        formula="NO_VALIDADA",
        tolerancia="0.00",
        evidencia="SIMULADA",
        aprobacion="NO_APROBADA",
    )

    with pytest.raises(HomologacionNoAprobada):
        validar_homologacion(regla)


def test_rechaza_moneda_incompatible():
    regla = ReglaHomologacion(
        concepto="LIQUIDACION_NETA_USD",
        moneda="COP",
    )

    with pytest.raises(HomologacionNoAprobada):
        validar_homologacion(regla)


def test_diferencia_deshabilitada():
    with pytest.raises(HomologacionNoAprobada):
        calcular_diferencia(100, 100)


def test_estado_no_certificado():
    estado = estado_inc021()

    assert estado["diferencia_contable"] is None
    assert estado["certificado"] is False
    assert estado["conciliado_host"] is False
    assert estado["homologado_contablemente"] is False
