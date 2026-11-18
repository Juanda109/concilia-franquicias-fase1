import hashlib
import pytest
from app.services.fase2.plantilla_reglas_redeban import resolver_plantilla_reglas


def test_sin_configuracion(monkeypatch):
    monkeypatch.delenv('INC64_PLANTILLA_REGLAS', raising=False)
    monkeypatch.delenv('INC64_PLANTILLA_REGLAS_SHA256', raising=False)
    assert resolver_plantilla_reglas(5683, '2026-11-10') is None


def test_requiere_huella(monkeypatch, tmp_path):
    ruta = tmp_path / 'reglas.xlsx'
    ruta.write_bytes(b'ejemplo')
    monkeypatch.setenv('INC64_PLANTILLA_REGLAS', str(ruta))
    monkeypatch.delenv('INC64_PLANTILLA_REGLAS_SHA256', raising=False)
    with pytest.raises(ValueError):
        resolver_plantilla_reglas(5683, '2026-11-10')


def test_valida_huella(monkeypatch, tmp_path):
    ruta = tmp_path / 'reglas.xlsx'
    ruta.write_bytes(b'ejemplo')
    monkeypatch.setenv('INC64_PLANTILLA_REGLAS', str(ruta))
    monkeypatch.setenv('INC64_PLANTILLA_REGLAS_SHA256', hashlib.sha256(b'ejemplo').hexdigest())
    assert resolver_plantilla_reglas(5683, '2026-11-10') == ruta
    monkeypatch.setenv('INC64_PLANTILLA_REGLAS_SHA256', '0'*64)
    with pytest.raises(ValueError):
        resolver_plantilla_reglas(5683, '2026-11-10')
