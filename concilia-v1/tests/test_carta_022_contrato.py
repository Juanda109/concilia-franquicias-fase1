from pathlib import Path
from app.services.persistencia_detalle import CAMPOS_CARTA, NUMERICOS_CARTA

def test_carta_campos_18():
    assert len(CAMPOS_CARTA) == 18
    assert len(set(CAMPOS_CARTA)) == 18
    assert 'es_control' in CAMPOS_CARTA
    assert 'factor_compra' in NUMERICOS_CARTA

def test_carta_ddl():
    ddl=Path('sql/migrations/022_CARTA_COMPENSACION_DETALLE.sql').read_text(encoding='utf-8-sig').lower()
    for field in CAMPOS_CARTA:
        assert field in ddl
    assert 'unique(id_archivo,seccion,linea_origen)' in ddl
