import json
from pathlib import Path
import pytest
from app.services.fase2.validador_equivalencias_inc70 import validar

BASE = Path(__file__).resolve().parent / "fixtures" / "redeban"
def datos():
    return (json.loads((BASE/'inc69_matriz_equivalencias_6466.json').read_text(encoding='utf-8')),json.loads((BASE/'inc69_cardinalidad_padres_6466.json').read_text(encoding='utf-8')))
def test_universo_real():
    m,c=datos(); r=validar(m,c)
    assert r['conteos']=={'PADRE_COMPARTIDO_NO_DISTRIBUIR':350,'PADRE_UNICO_PENDIENTE_HOMOLOGACION':6,'SIN_EQUIVALENCIA':8}
    assert len(r['grupos'])==46 and not r['certificado']
    assert all(f['neto_homologado'] is None for f in r['decisiones'])
def test_rechaza_homologacion_sin_evidencia():
    m,c=datos();m['matriz'][0]['neto_homologado']='10'
    with pytest.raises(ValueError): validar(m,c)
def test_rechaza_asignacion_duplicada():
    m,c=datos();c['grupos'][1]['filas_excel'][0]=c['grupos'][0]['filas_excel'][0]
    with pytest.raises(ValueError): validar(m,c)
def test_rechaza_jornada_distinta():
    m,c=datos();m['id_jornada']=7
    with pytest.raises(ValueError): validar(m,c)
