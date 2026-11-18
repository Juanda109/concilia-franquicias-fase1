from pathlib import Path
import ast
from app.services.persistencia_detalle import CAMPOS_DEPO, CAMPOS_HOST_TIPADOS

def test_contrato_depo_y_host():
    assert len(CAMPOS_DEPO) == 50
    assert len(set(CAMPOS_DEPO)) == 50
    assert set(CAMPOS_HOST_TIPADOS) == {'HA22', 'HA26', 'HA32'}

def test_api_depo_integrada():
    source = Path('backend/app/api/detalle_archivos.py').read_text(encoding='utf-8-sig')
    ast.parse(source)
    assert '"DEPO": "con_depo_detalle"' in source
    assert "elif tipo == 'DEPO':" in source
