"""financial-overview: SOLO ``customer.id`` (decision de Fabian, 24/08).

Incidente PRD 24/08: la peticion filtrada por ``contracts.id`` (LIC de ADA,
identificador que el filtro del ASO real no indexa) fallaba y el cliente veia
"no pudimos consultar tus productos" teniendo productos. Arreglo acordado en
el equipo: quitar el filtro por contrato y el de productType=CARDS -- traer
TODO el financial del cliente y localizar la tarjeta en la respuesta por
``number``. Estos tests fijan ese contrato de peticion.
"""

from unittest.mock import patch

from infrastructure.persistence.aso_client import TrxAsoClient

FO_OK = {"data": {"contracts": [{"number": "0060", "id": "4912680517940060"}]}}


def _llamar(contract_id: str) -> tuple[dict | None, list[dict]]:
    llamadas = []

    def falso_get(self, path, params, tsec, **kw):
        llamadas.append(dict(params))
        return FO_OK

    with patch.object(TrxAsoClient, "_get", falso_get):
        fo = TrxAsoClient().financial_overview(
            customer_id="1013634960", contract_id=contract_id)
    return fo, llamadas


def test_solo_customer_id_aunque_llegue_contrato():
    """El contract_id de los llamadores NO viaja al ASO."""
    fo, llamadas = _llamar("00131003201300060")
    assert fo == FO_OK
    assert len(llamadas) == 1
    assert llamadas[0] == {"customer.id": "1013634960"}


def test_solo_customer_id_sin_contrato():
    fo, llamadas = _llamar("")
    assert fo == FO_OK
    assert llamadas[0] == {"customer.id": "1013634960"}


def test_sin_filtro_cards():
    """Tampoco viaja contracts.productType=CARDS (se trae TODO el financial)."""
    _, llamadas = _llamar("00131003201300060")
    assert "contracts.productType" not in llamadas[0]
    assert "contracts.id" not in llamadas[0]


def test_fallo_sigue_fail_closed():
    """Si la unica llamada falla -> None: el .4.error honesto se conserva."""
    with patch.object(TrxAsoClient, "_get", lambda *a, **k: None):
        fo = TrxAsoClient().financial_overview(
            customer_id="1013634960", contract_id="00131003201300060")
    assert fo is None
