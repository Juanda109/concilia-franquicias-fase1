from decimal import Decimal
import pytest

from app.services.fase2.parser_vss_visa import ErrorVSSVisa, parsear_vss110


VSS_12NOV26 = """REPORT ID: VSS-110 PAGE: 1
SETTLEMENT CURRENCY: COP
CLEARING CURRENCY: COP
REPORT DATE: 12NOV26
SIMULATED NET SETTLEMENT 1,250.00CR
END OF VSS-110""".replace(",", "")


def test_parsea_vss_12nov26():
    r = parsear_vss110(VSS_12NOV26)
    assert r.report_id == "VSS-110"
    assert r.page == 1
    assert r.settlement_currency == "COP"
    assert r.clearing_currency == "COP"
    assert r.report_date == "12NOV26"
    assert r.simulated_net_settlement == Decimal("1250.00")
    assert r.simulated_sign == "CR"


def test_no_inventa_importe_real():
    texto = VSS_12NOV26.replace("SIMULATED NET SETTLEMENT 1250.00CR\n", "")
    r = parsear_vss110(texto)
    assert r.simulated_net_settlement is None
    assert r.simulated_sign is None

@pytest.mark.parametrize("texto", [
    "",
    "REPORT ID: VSS-110 PAGE: 1",
    "REPORT ID: VSS-999 PAGE: 1\nSETTLEMENT CURRENCY: COP\nCLEARING CURRENCY: COP\nREPORT DATE: 12NOV26",
])
def test_rechaza_layout_incompleto(texto):
    with pytest.raises(ErrorVSSVisa):
        parsear_vss110(texto)


# RECON_F2_011_PRUEBAS_MILES

def test_importe_con_separador_miles():
    texto = VSS_12NOV26.replace(
        "1250.00CR", "1,250.00CR"
    )

    r = parsear_vss110(texto)

    assert r.simulated_net_settlement == Decimal("1250.00")
    assert r.simulated_sign == "CR"


def test_debito_con_separador_miles():
    texto = VSS_12NOV26.replace(
        "1250.00CR", "1,250.00DB"
    )

    r = parsear_vss110(texto)

    assert r.simulated_net_settlement == Decimal("1250.00")
    assert r.simulated_sign == "DB"
