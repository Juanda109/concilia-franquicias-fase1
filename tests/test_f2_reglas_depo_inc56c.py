from app.services.fase2.reglas_depo_inc56c import evaluar


def test_control_05_prioridad_absoluta():
    d = evaluar({"TIPO_MOVIMIENTO":"05", "TASA_DE_INTERCAMBIO":12}, indicador_cnb="010", clasificacion_amex="AMEX INTERNACIONAL")
    assert d["decision_diagnostica"] == "NO_PERSISTIR_CONTROL_RESUMEN"
    assert d["reglas_activadas"] == []


def test_movimientos_permitidos():
    for tipo in ("02", "06", "26", "42"):
        d = evaluar({"TIPO_MOVIMIENTO":tipo, "TASA_DE_INTERCAMBIO":0})
        assert d["decision_diagnostica"] == "PERSISTIR_REGLA_VERIFICADA"


def test_cnb_explicito():
    d = evaluar({"TIPO_MOVIMIENTO":"99", "TASA_DE_INTERCAMBIO":0}, indicador_cnb="110")
    assert d["reglas_activadas"] == ["INDICADOR_CNB_PERMITIDO"]


def test_amex_explicito():
    d = evaluar({"TIPO_MOVIMIENTO":"99", "TASA_DE_INTERCAMBIO":0}, clasificacion_amex="AMEX INTERNACIONAL")
    assert "AMEX_INTERNACIONAL" in d["reglas_activadas"]


def test_tasa_no_cero():
    d = evaluar({"TIPO_MOVIMIENTO":"99", "TASA_DE_INTERCAMBIO":-1})
    assert "TASA_INTERCAMBIO_NO_CERO" in d["reglas_activadas"]


def test_sin_evidencia_no_descartar_como_definitivo():
    d = evaluar({"TIPO_MOVIMIENTO":"99", "TASA_DE_INTERCAMBIO":0})
    assert d["decision_diagnostica"] == "PENDIENTE_EVIDENCIA"
    assert d["cuenta_contable"] is None
    assert d["debe"] is None
    assert d["haber"] is None


def test_sin_importes_certificados():
    d = evaluar({"TIPO_MOVIMIENTO":"06", "TASA_DE_INTERCAMBIO":100})
    assert d["estado_monetario"] == "NO_HOMOLOGADO"
    assert d["neto"] is None
