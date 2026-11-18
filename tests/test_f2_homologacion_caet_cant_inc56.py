from app.services.fase2.reporte_credibanco_inc51 import enriquecer

def test_cuentas_homologadas_sin_cruce():
    r={"certificado":False,"detalle":[],"totales_diagnosticos":[
        {"A":"017-CANJE RECIBIDO TARJETA CREDITO","B":4,"C":"219894","D":"219894"},
        {"A":"017-CANJE RECIBIDO TARJETA CREDITO REVERSION VENTAS 26 VLR. TOTAL","B":4,"C":"219894","D":"219894"}]}
    d=enriquecer(r)
    grupos=d["diagnostico_credibanco_inc51"]["agregados_sin_correspondencia"]
    assert [x["cuenta_homologada"] for x in grupos]==["299095302","299095302"]
    assert all(x["estado"]=="CUENTA_HOMOLOGADA_FORMULA_PENDIENTE" for x in grupos)
    assert d["certificado"] is False
    assert "valor_franquicia" not in grupos[0]
