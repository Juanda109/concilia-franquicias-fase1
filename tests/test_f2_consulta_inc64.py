from datetime import date
from unittest.mock import patch
from app.services.fase2.reporte_pmd_inc59 import consultar

def test_consultar_sin_configuracion_preserva_inc59(monkeypatch):
    monkeypatch.delenv('INC64_REGISTRO_CATALOGOS', raising=False)
    base = {'id_jornada': 5683, 'certificado': False, 'columnas': list(range(11))}
    with patch('app.services.fase2.reporte_pmd_inc59.consultar_base', return_value=base), \
         patch('app.services.fase2.reporte_pmd_inc59.leer_jornada', return_value=[]), \
         patch('app.services.fase2.reporte_pmd_inc59.enriquecer', return_value=base):
        assert consultar(5683) == base


def test_consultar_con_vinculo_integra(monkeypatch, tmp_path):
    monkeypatch.setenv('INC64_REGISTRO_CATALOGOS', str(tmp_path / 'registro.json'))
    base = {'id_jornada': 5683, 'certificado': False, 'columnas': list(range(11))}
    with patch('app.services.fase2.reporte_pmd_inc59.consultar_base', return_value=base), \
         patch('app.services.fase2.reporte_pmd_inc59.leer_jornada', return_value=[]), \
         patch('app.services.fase2.reporte_pmd_inc59.enriquecer', return_value=base), \
         patch('app.services.fase2.vinculo_catalogo_inc64.consultar_fecha_jornada', return_value=date(2026,10,2)), \
         patch('app.services.fase2.vinculo_catalogo_inc64.resolver_vinculo', return_value=tmp_path/'catalogo.xlsx'), \
         patch('app.services.fase2.catalogo_estructura_inc60.leer_catalogo', return_value={'version_catalogo':'hash','registros':[]}), \
         patch('app.services.fase2.proyeccion_estructura_inc60.proyectar_estructura', return_value={'id_jornada':5683,'version_catalogo':'hash','filas':[],'cantidad_filas':0,'certificado':False}), \
         patch('app.services.fase2.integracion_redeban_inc64.adjuntar_diagnostico', return_value={'ok':True}) as adj:
        assert consultar(5683) == {'ok': True}
        adj.assert_called_once()
