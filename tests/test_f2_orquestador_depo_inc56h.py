from pathlib import Path
import pytest
from app.services.fase2.orquestador_depo_inc56h import conciliar_depo


def test_sin_excel_y_sin_certificar(tmp_path):
    depo=tmp_path/'depo.txt'
    depo.write_text('02'+'0'*280+'\n',encoding='utf-8')
    r=conciliar_depo(depo)
    assert r['certificado_monetario'] is False
    assert r['valor_franquicia'] is None and r['diferencia'] is None
    assert r['diagnostico_depo']['tipos']['02']==1


def test_fuentes_no_se_suman(tmp_path):
    depo=tmp_path/'depo.txt'; depo.write_text('02'+'0'*280+'\n')
    filas=[{'fuente':f,'cuenta':'196095001838','naturaleza':'D','importe':'2910.00','linea_origen':2}
           for f in ('HA22','HA26','HA32')]
    with pytest.raises(ValueError):
        conciliar_depo(depo,filas)
    r=conciliar_depo(depo,filas,fuente_host='HA22')
    assert r['sumatorias_host'][0]['importe_contable']=='2910.00'
    assert r['certificado_monetario'] is False


def test_clasificacion_no_aprobada_no_calcula(tmp_path):
    depo=tmp_path/'depo.txt'; depo.write_text('02'+'0'*280+'\n')
    r=conciliar_depo(depo,movimientos_clasificados=[{'archivo_origen':'depo.txt',
        'linea_origen':1,'concepto_verificado':'DEPOSITO_NACIONAL',
        'clasificacion_aprobada':False,'importe_crudo':'123'}])
    assert r['agregados_depo']['resultados']==[]
    assert len(r['agregados_depo']['pendientes'])==1
