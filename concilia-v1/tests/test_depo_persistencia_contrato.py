from pathlib import Path
from app.parsers.depo import FIELDS
from app.services.persistencia_detalle import CAMPOS_DEPO

def test_contrato_50_columnas():
    assert len(FIELDS) == 44
    assert len(CAMPOS_DEPO) == 50
    assert CAMPOS_DEPO[:44] == tuple(n.lower() for n,_,_ in FIELDS)
    assert len(set(CAMPOS_DEPO)) == 50

def test_migracion_depo():
    ddl = Path('sql/migrations/021_DEPO_DETALLE.sql').read_text(encoding='utf-8')
    assert 'con_depo_detalle' in ddl
    for campo in CAMPOS_DEPO:
        assert ' '+campo+' ' in ddl
    assert 'UNIQUE(id_archivo,linea_origen)' in ddl
