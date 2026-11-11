from pathlib import Path

def test_orquestador_no_tiene_exclusion_especial_por_tipo():
    codigo=Path('backend/app/services/procesamiento_automatico.py').read_text()
    assert "r[1]!='MEP'" not in codigo


def test_orquestador_no_procesa_ceros_sin_confirmacion():
    codigo=Path('backend/app/services/procesamiento_automatico.py').read_text()
    assert 'r[4]==0 and not r[6]' in codigo
    assert "or confirmado or total==0" in codigo
