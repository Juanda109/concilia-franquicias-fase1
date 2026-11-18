import hashlib
import json
from datetime import date
from unittest.mock import patch
import pytest
from app.services.fase2.vinculo_catalogo_inc64 import resolver_vinculo


def test_sin_registro_no_hay_catalogo(monkeypatch):
    monkeypatch.delenv('INC64_REGISTRO_CATALOGOS', raising=False)
    assert resolver_vinculo(1, date(2026, 10, 2)) is None


def test_vinculo_valido_y_controles(tmp_path):
    libro = tmp_path / 'catalogo.xlsx'
    libro.write_bytes(b'ejemplo')
    huella = hashlib.sha256(libro.read_bytes()).hexdigest()
    registro = tmp_path / 'registro.json'
    dato = {'jornadas': {'5066': {'fecha_contable': '2026-10-02', 'archivo': str(libro), 'sha256': huella}}}
    registro.write_text(json.dumps(dato))
    assert resolver_vinculo(5066, date(2026, 10, 2), registro) == libro
    with pytest.raises(ValueError, match='Fecha'):
        resolver_vinculo(5066, date(2026, 10, 3), registro)
    libro.write_bytes(b'alterado')
    with pytest.raises(ValueError, match='Huella'):
        resolver_vinculo(5066, date(2026, 10, 2), registro)
