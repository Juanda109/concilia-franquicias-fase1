from pathlib import Path

def test_mep_opcional_version_2():
    sql=Path('sql/migrations/032_CONFIRMACION_Y_MEP_OPCIONAL.sql').read_text()
    assert "version_catalogo = 2 AND tipo_insumo = 'MEP'" in sql

def test_orquestador_no_procesa_ceros_sin_confirmacion():
    codigo=Path('backend/app/services/procesamiento_automatico.py').read_text()
    assert 'r[4]==0 and not r[6]' in codigo
    assert "or confirmado or total==0" in codigo
