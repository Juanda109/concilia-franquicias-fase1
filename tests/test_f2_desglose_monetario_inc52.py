import pytest
from app.services.fase2.desglose_monetario_inc52 import desglose_host, desglose_host_unico

def ejemplo():
    r={'cuenta':'299095302','centro':'17','id_archivo':2207,'lineas_origen':[2],
       'debe':'100.00','haber':'20.00','neto_diagnostico':'80.00'}
    return {'cuenta':'299095302','host_diagnostico_inc50':{'fuentes':{'HA22':[r]}}}

def test_desglose_conserva_debe_haber_neto():
    d=desglose_host(ejemplo())[0]
    assert (d['debe'],d['haber'],d['neto_diagnostico'])==('100.00','20.00','80.00')

def test_no_duplica_misma_cuenta_en_dos_conceptos():
    assert len(desglose_host_unico([ejemplo(),ejemplo()]))==1

def test_rechaza_neto_inconsistente():
    e=ejemplo();e['host_diagnostico_inc50']['fuentes']['HA22'][0]['neto_diagnostico']='99'
    with pytest.raises(ValueError): desglose_host(e)

def test_ha32_saldo_no_inventado():
    e=ejemplo();e['host_diagnostico_inc50']['fuentes']={'HA32':[e['host_diagnostico_inc50']['fuentes']['HA22'][0]]}
    assert desglose_host(e)[0]['saldo_inicial'] is None
