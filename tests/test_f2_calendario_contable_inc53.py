from datetime import date
import pytest
from app.services.fase2.calendario_contable_inc53 import (CalendarioColombia, Configuracion, TipoConsulta, festivos_colombia, planificar, claves_movimientos_unicas)

def test_puente_noviembre():
    c=CalendarioColombia()
    assert date(2026,11,2) in festivos_colombia(2026)
    assert not c.habil(date(2026,11,2))
    assert c.retroceder_habiles(date(2026,11,3),1)==date(2026,10,30)

def test_recupera_sabado_domingo_festivo():
    c=CalendarioColombia()
    cfg=Configuracion('299095302','0017',TipoConsulta.MOVIMIENTOS)
    p=planificar(cfg,date(2026,11,3),[date(2026,10,31),date(2026,11,1),date(2026,11,2)],c)
    assert p.desde==date(2026,10,31) and p.hasta==date(2026,11,2)
    assert len(p.fechas_pendientes)==3

def test_falla_habil_tambien_pendiente():
    c=CalendarioColombia()
    p=planificar(Configuracion('1','0017',TipoConsulta.MOVIMIENTOS),date(2026,11,4),[date(2026,11,3)],c)
    assert p.fechas_pendientes==(date(2026,11,3),)

def test_saldo_no_suma_dias():
    c=CalendarioColombia()
    p=planificar(Configuracion('1','0017',TipoConsulta.SALDO),date(2026,11,3),[date(2026,11,1)],c)
    assert p.corte_saldo==date(2026,10,30) and p.desde is None

def test_dos_habiles():
    c=CalendarioColombia()
    p=planificar(Configuracion('196095001859','0017',TipoConsulta.MOVIMIENTOS,2),date(2026,11,3),[date(2026,10,29)],c)
    assert c.retroceder_habiles(date(2026,11,3),2)==date(2026,10,29)

def test_referencia_pendiente():
    p=planificar(Configuracion('196095001830','0017',TipoConsulta.REFERENCIA),date(2026,11,3),[],CalendarioColombia())
    assert p.estado=='PENDIENTE_REFERENCIA'

def test_no_ejecuta_festivo():
    with pytest.raises(ValueError):
        planificar(Configuracion('1','0017',TipoConsulta.MOVIMIENTOS),date(2026,11,2),[],CalendarioColombia())

def test_deduplicacion_procedencia():
    m={'fuente':'HA22','id_archivo':1,'linea_origen':2}
    assert len(claves_movimientos_unicas([m,m,{**m,'fuente':'HA26'}]))==2
