"""Pruebas unitarias del servicio, sin PostgreSQL."""
from pathlib import Path
from types import SimpleNamespace
import pytest

from app.services import validacion_archivos as val


def test_pmd_nombre_incorrecto(tmp_path):
    archivo = tmp_path / 'carga.bin'
    archivo.write_bytes(b'contenido')
    with pytest.raises(val.ArchivoRechazado) as exc:
        val.validar_archivo('PMD', 'otro.xlsx', archivo)
    assert exc.value.codigo == 'NOMBRE_INVALIDO'


def test_mep_extension_incorrecta(tmp_path):
    archivo = tmp_path / 'carga.bin'
    archivo.write_bytes(b'contenido')
    with pytest.raises(val.ArchivoRechazado) as exc:
        val.validar_archivo('MEP', 'archivo.xls', archivo)
    assert exc.value.codigo == 'FORMATO_INVALIDO'


def test_parser_recibe_nombre_original(tmp_path, monkeypatch):
    archivo = tmp_path / 'carga.bin'
    archivo.write_bytes(b'contenido')
    def parse(ruta):
        assert ruta.name == 'PMDGeneralEntidad260914.xlsx'
        assert ruta.read_bytes() == b'contenido'
        return SimpleNamespace(records=[{'x': 1}], errors=[], controls=[])
    monkeypatch.setattr(val, 'obtener_parser', lambda tipo: SimpleNamespace(parse=parse))
    resultado = val.validar_archivo('PMD', 'PMDGeneralEntidad260914.xlsx', archivo)
    assert len(resultado.records) == 1
    assert archivo.is_file()


def test_errores_parser_rechazan(tmp_path, monkeypatch):
    archivo = tmp_path / 'carga.bin'
    archivo.write_bytes(b'contenido')
    error = SimpleNamespace(linea=2, codigo='HEADER_INVALIDO', descripcion='Columnas incorrectas')
    monkeypatch.setattr(val, 'obtener_parser', lambda tipo: SimpleNamespace(parse=lambda p: SimpleNamespace(records=[], errors=[error], controls=[])))
    with pytest.raises(val.ArchivoRechazado) as exc:
        val.validar_archivo('MEP', 'mep.xlsx', archivo)
    assert exc.value.detalle()['errores'][0]['codigo'] == 'HEADER_INVALIDO'


def test_sin_registros_rechaza(tmp_path, monkeypatch):
    archivo = tmp_path / 'carga.bin'
    archivo.write_bytes(b'contenido')
    monkeypatch.setattr(val, 'obtener_parser', lambda tipo: SimpleNamespace(parse=lambda p: SimpleNamespace(records=[], errors=[], controls=[])))
    with pytest.raises(val.ArchivoRechazado) as exc:
        val.validar_archivo('MEP', 'mep.xlsx', archivo)
    assert exc.value.codigo == 'SIN_REGISTROS'
