"""Rama TRX_PRODUCTS_SOURCE=fo de consultar_productos_activos (F2, 24/08).

El portafolio se valida directamente con el financial-overview (se salta la
Consulta ADA). Fail-closed si el FO no contesta; la direccion se enriquece
desde Postgres en fail-open (un fallo ahi no bloquea los productos).
"""

import json
import pathlib
from unittest.mock import patch

import pytest

from application.trx.analysis_service import TrxAnalysisService
from domain.trx.models import TrxCase
from infrastructure.persistence.aso_client import TrxAsoClient

FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "financial_overview_real_nicolas.json"


def _caso() -> TrxCase:
    return TrxCase(customer_id="1013634960", data={})


@pytest.fixture(autouse=True)
def _fuente_fo(monkeypatch):
    monkeypatch.setenv("TRX_PRODUCTS_SOURCE", "fo")


def _con_fo(fo, postgres=([], None)):
    return (
        patch.object(TrxAsoClient, "get_tsec", lambda self: "tsec"),
        patch.object(TrxAsoClient, "financial_overview", lambda self, **kw: fo),
        patch.object(TrxAnalysisService, "_load_products_from_postgres",
                     lambda self, cid: postgres),
    )


def test_fo_ok_devuelve_las_tarjetas_del_json_real():
    fo = json.loads(FIXTURE.read_text())
    p1, p2, p3 = _con_fo(fo)
    with p1, p2, p3:
        r = TrxAnalysisService().consultar_productos_activos(_caso())
    assert r.status == "ok"
    assert r.data["origin_flag"] == "FO"
    assert {p["last_four"] for p in r.data["products"]} == {"2583", "2100"}


def test_fo_caido_es_fail_closed():
    p1, p2, p3 = _con_fo(None)
    with p1, p2, p3:
        r = TrxAnalysisService().consultar_productos_activos(_caso())
    assert r.status == "error"
    assert r.data["error"] == "fo_error"


def test_fo_sin_tarjetas_es_not_found():
    fo = {"contracts": [{"productType": "ACCOUNT",
                         "subProductType": {"id": "SAVING"},
                         "status": {"id": "ACTIVATED"}}]}
    p1, p2, p3 = _con_fo(fo)
    with p1, p2, p3:
        r = TrxAnalysisService().consultar_productos_activos(_caso())
    assert r.status == "not_found"
    assert r.data["products"] == []


def test_solo_fo_no_toca_postgres_y_sin_direccion():
    """solo-FO v3 (24/08): Postgres NO se consulta y customer_address ya no
    viaja -- ni en los productos ni en el sobre. El agente lo lee con .get()
    tolerante y el .17.2 degrada al copy generico (verificado en G3.3)."""
    fo = json.loads(FIXTURE.read_text())

    def _explota(self, cid):
        raise AssertionError("la rama fo NO debe tocar Postgres")

    with patch.object(TrxAsoClient, "get_tsec", lambda self: "tsec"), \
         patch.object(TrxAsoClient, "financial_overview", lambda self, **kw: fo), \
         patch.object(TrxAnalysisService, "_load_products_from_postgres", _explota):
        r = TrxAnalysisService().consultar_productos_activos(_caso())
    assert r.status == "ok"
    assert "customer_address" not in r.data
    assert all("customer_address" not in p for p in r.data["products"])
    assert len(r.data["products"]) == 2


def test_el_defecto_de_configuracion_es_fo(monkeypatch):
    """Sin variable de entorno, la fuente es fo (solo-FO)."""
    monkeypatch.delenv("TRX_PRODUCTS_SOURCE", raising=False)
    monkeypatch.delenv("CUSTOMER_IDENTITY_SOURCE", raising=False)
    from infrastructure.core.config import load_trx_source_settings
    assert load_trx_source_settings().products_source == "fo"
