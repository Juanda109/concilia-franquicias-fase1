from datetime import date
import pytest
from app.services.fase2.calendario_contable_inc53 import CalendarioColombia
from app.services.fase2.plan_recuperacion_inc54 import Cobertura, planificar_recuperacion

C = CalendarioColombia()

def plan(desde, ejecucion, coberturas=()):
    return planificar_recuperacion(desde=desde, ejecucion=ejecucion, coberturas=coberturas, calendario=C)

def test_fin_de_semana():
    r=plan(date(2026,10,24),date(2026,10,26))
    assert len(r['pendientes'])==6
    assert all(not x['habil'] for x in r['pendientes'])

def test_puente_todos_los_santos():
    r=plan(date(2026,10,31),date(2026,11,3))
    assert len(r['pendientes'])==9
    assert all(not x['habil'] for x in r['pendientes'])

def test_confirmado_no_se_repite():
    r=plan(date(2026,10,24),date(2026,10,26),[Cobertura(date(2026,10,24),'HA22','CONFIRMADA')])
    assert len(r['pendientes'])==5

def test_fallo_habil_se_recupera():
    r=plan(date(2026,10,23),date(2026,10,26),[Cobertura(date(2026,10,23),'HA26','FALLIDA')])
    assert any(x['estado']=='FALLIDA' and x['habil'] for x in r['pendientes'])

def test_no_ejecutar_festivo():
    with pytest.raises(ValueError):plan(date(2026,10,30),date(2026,11,2))

def test_conflicto_cobertura():
    with pytest.raises(ValueError):
        plan(date(2026,10,24),date(2026,10,26),[Cobertura(date(2026,10,24),'HA22','CONFIRMADA'),Cobertura(date(2026,10,24),'HA22','FALLIDA')])

def test_sin_ejecucion_automatica():
    assert plan(date(2026,10,24),date(2026,10,26))['ejecucion_automatica_habilitada'] is False
