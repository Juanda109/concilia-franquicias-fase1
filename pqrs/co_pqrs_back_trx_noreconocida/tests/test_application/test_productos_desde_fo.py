"""Productos TXNR desde el financial-overview (roadmap PO, 24/08).

Decision de Fabian sobre el rombo "Se validan los productos del cliente":
saltar la Consulta ADA y validar el portafolio directamente con el
financial-overview. Estos tests corren contra el JSON REAL que compartio
Nicolas (sin mocks inventados): 8 contratos de los que solo 2 son tarjetas
operativas D/M.
"""

import json
import pathlib
import unittest

from application.trx.aso_rules import productos_desde_fo

FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "financial_overview_real_nicolas.json"


def _fo_real() -> dict:
    return json.loads(FIXTURE.read_text())


class ProductosDesdeFoTests(unittest.TestCase):
    def test_json_real_de_nicolas_da_sus_dos_tarjetas(self) -> None:
        out = productos_desde_fo(_fo_real())
        self.assertEqual(len(out), 2)
        self.assertEqual(
            {p["last_four"] for p in out}, {"2583", "2100"})

    def test_debito_y_credito_bien_clasificadas(self) -> None:
        por_last4 = {p["last_four"]: p for p in productos_desde_fo(_fo_real())}
        debito = por_last4["2583"]
        credito = por_last4["2100"]
        self.assertEqual(debito["tipo"], "TARJETA_DEBITO")
        self.assertEqual(debito["product_desc"], "Visa Débito")
        self.assertEqual(credito["tipo"], "TARJETA_CREDITO")
        self.assertEqual(credito["product_desc"], "VISA ORO")

    def test_franquicia_derivada_del_nombre(self) -> None:
        for p in productos_desde_fo(_fo_real()):
            self.assertEqual(p["card_brand"], "VISA")

    def test_cuentas_prestamos_y_fondos_quedan_fuera(self) -> None:
        """El fixture trae ACCOUNT/LOAN/INVESTMENT_FUND: ninguno pasa."""
        tipos = {p["tipo"] for p in productos_desde_fo(_fo_real())}
        self.assertEqual(tipos, {"TARJETA_DEBITO", "TARJETA_CREDITO"})

    def test_contrato_del_selector_v4(self) -> None:
        """v4 (Fabian 24/08): card_id (es el PAN), sin origin_flag ni
        contract_id ni customer_address; agreement_contract presente."""
        for p in productos_desde_fo(_fo_real()):
            for campo in ("card_id", "last_four", "product_desc",
                          "card_brand", "agreement_contract"):
                self.assertIn(campo, p)
            for retirado in ("contract_id", "origin_flag", "customer_address"):
                self.assertNotIn(retirado, p)

    def test_agreement_contract_solo_lo_trae_la_debito(self) -> None:
        """En el JSON real de Nicolas: la DEBITO trae agreementContract (vino
        anonimizado como token; el API real da 20 digitos) y la CREDITO no."""
        por_last4 = {p["last_four"]: p for p in productos_desde_fo(_fo_real())}
        self.assertTrue(por_last4["2583"]["agreement_contract"])
        self.assertEqual(por_last4["2100"]["agreement_contract"], "")

    def test_last_four_sale_de_number_pan(self) -> None:
        for p in productos_desde_fo(_fo_real()):
            self.assertEqual(p["numero_type"], "PAN")
            self.assertEqual(len(p["last_four"]), 4)

    def test_tarjeta_no_operativa_queda_fuera(self) -> None:
        fo = _fo_real()
        for c in fo["contracts"]:
            if str(c.get("productType")) == "CARD":
                c["status"]["id"] = "BLOCKED"
                c["detail"]["status"] = {"id": "BLOCKED"}
        self.assertEqual(productos_desde_fo(fo), [])

    def test_indicador_blockable_inactivo_excluye(self) -> None:
        fo = _fo_real()
        for c in fo["contracts"]:
            if str(c.get("productType")) == "CARD":
                for ind in c["detail"].get("indicators", []):
                    if ind.get("id") == "BLOCKABLE":
                        ind["isActive"] = False
        self.assertEqual(productos_desde_fo(fo), [])

    def test_fo_vacio_o_none_da_lista_vacia(self) -> None:
        self.assertEqual(productos_desde_fo(None), [])
        self.assertEqual(productos_desde_fo({}), [])
        self.assertEqual(productos_desde_fo({"data": {"contracts": []}}), [])

    def test_acepta_forma_con_data_contracts(self) -> None:
        """El fixture es la raiz; el aso_client podria envolver en data."""
        fo = {"data": _fo_real()}
        self.assertEqual(len(productos_desde_fo(fo)), 2)


class FranquiciaPorBinTests(unittest.TestCase):
    """H1 (24/08): la franquicia sale del primer digito del PAN; el nombre es
    respaldo. Motivo: una marca desconocida heredaba el trato VISA (180 dias,
    el plazo mas largo) -- dato inventado por defecto, vetado por Fabian."""

    def _tarjeta(self, pan: str, nombre: str) -> dict:
        return {
            "id": pan,
            "productType": "CARD",
            "subProductType": {"id": "CREDIT_CARD"},
            "status": {"id": "OPERATIVE"},
            "number": pan[-4:] if len(pan) >= 4 else pan,
            "numberType": {"id": "PAN"},
            "product": {"name": nombre},
            "currencies": [{"currency": "COP"}],
            "detail": {},
        }

    def _marca(self, pan: str, nombre: str) -> str:
        out = productos_desde_fo({"contracts": [self._tarjeta(pan, nombre)]})
        return out[0]["card_brand"]

    def test_bin_4_es_visa_aunque_el_nombre_no_lo_diga(self) -> None:
        self.assertEqual(self._marca("4912680517942100", "TARJETA AQUA"), "VISA")

    def test_bin_5_es_master(self) -> None:
        self.assertEqual(self._marca("5412750198763412", "TARJETA ORO"), "MASTER")

    def test_bin_2_es_master_serie_2017(self) -> None:
        self.assertEqual(self._marca("2221001234567890", "TARJETA ORO"), "MASTER")

    def test_bin_gana_al_nombre_cuando_contradicen(self) -> None:
        """El PAN es la fuente fiable; el nombre comercial puede mentir."""
        self.assertEqual(self._marca("5412750198763412", "VISA CLASICA"), "MASTER")

    def test_pan_enmascarado_cae_al_nombre(self) -> None:
        """El JSON de Nicolas venia con '********': respaldo por nombre."""
        self.assertEqual(self._marca("********", "Visa Débito"), "VISA")

    def test_sin_pan_ni_nombre_reconocible_queda_vacia(self) -> None:
        """Nada de adivinar: vacia, y el consumidor decide (hoy el agente
        trata vacia como VISA -- decision 1 de la estrategia solo-FO)."""
        self.assertEqual(self._marca("********", "TARJETA AQUA"), "")

    def test_las_tarjetas_reales_de_nicolas_siguen_visa(self) -> None:
        for p in productos_desde_fo(_fo_real()):
            self.assertEqual(p["card_brand"], "VISA")

class PanDesdeFormatsTests(unittest.TestCase):
    """Fix H-1 (31/08): con la forma REAL del ASO de DEV, card_id es el PAN de
    formats[].number, no el token de contracts[].id (operations lo rechaza)."""

    def _contrato_real_dev(self) -> dict:
        # Forma observada en la traza del 30/08 (cliente 00235597, •1106).
        return {
            "id": "WcQztTG27BMksUnchTBjPK1sk0HdOY0AQmpyLUdLcrs",
            "number": "1106",
            "numberType": {"id": "PAN", "name": ""},
            "status": {"id": "OPERATIVE", "name": ""},
            "product": {"id": "50", "name": "VISA CLÁSICA", "description": ""},
            "productType": "CARD",
            "subProductType": {"id": "CREDIT_CARD", "name": ""},
            "formats": [{"number": "4504070684131106",
                         "numberType": {"id": "PAN", "name": ""}}],
            "currencies": [{"currency": "COP", "isMajor": True}],
            "detail": {
                "agreementContract": "",
                "indicators": [{"id": "BLOCKABLE", "name": "", "isActive": True}],
                "status": {"id": "OPERATIVE", "name": "APAGADA"},
            },
        }

    def test_card_id_es_el_pan_de_formats(self) -> None:
        out = productos_desde_fo({"data": {"contracts": [self._contrato_real_dev()]}})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["card_id"], "4504070684131106")
        self.assertEqual(out[0]["last_four"], "1106")

    def test_franquicia_por_bin_revive_con_el_pan(self) -> None:
        # El token no empieza por 4/5/2 -> antes caia SIEMPRE al nombre.
        out = productos_desde_fo({"data": {"contracts": [self._contrato_real_dev()]}})
        self.assertEqual(out[0]["card_brand"], "VISA")

    def test_sin_formats_cae_al_id_como_antes(self) -> None:
        c = self._contrato_real_dev()
        c.pop("formats")
        c["id"] = "4912680517944979"  # el simulador local usa el PAN como id
        out = productos_desde_fo({"data": {"contracts": [c]}})
        self.assertEqual(out[0]["card_id"], "4912680517944979")

    def test_formats_sin_pan_no_inventa(self) -> None:
        c = self._contrato_real_dev()
        c["formats"] = [{"number": "****1106", "numberType": {"id": "MASKED"}}]
        out = productos_desde_fo({"data": {"contracts": [c]}})
        # tipo distinto de PAN -> se ignora y cae al id (token)
        self.assertEqual(out[0]["card_id"], "WcQztTG27BMksUnchTBjPK1sk0HdOY0AQmpyLUdLcrs")

class PanValidadoRobustoTests(unittest.TestCase):
    """Fix 02/09 (peticion de Fabian): no confiar ciegamente en formats.
    El card_id es el primer valor que sea un PAN de verdad -- formats si vale,
    si no el id. Cubre las dos formas de entorno y el caso que preocupa a
    Fabian (formats presente pero inexacto en PRD)."""

    def _card(self, **kw):
        base = {
            "number": "4818", "numberType": {"id": "PAN"},
            "status": {"id": "OPERATIVE"}, "product": {"name": "Visa Débito"},
            "productType": "CARD", "subProductType": {"id": "DEBIT_CARD"},
            "currencies": [{"currency": "COP", "isMajor": True}],
            "detail": {"agreementContract": "",
                       "indicators": [{"id": "BLOCKABLE", "isActive": True}],
                       "status": {"id": "OPERATIVE"}},
        }
        base.update(kw)
        return base

    def _fo(self, c):
        return {"data": {"contracts": [c]}}

    def test_prd_id_es_el_pan_sin_formats(self):
        c = self._card(id="4912684136504818")  # PRD: id=PAN, sin formats
        out = productos_desde_fo(self._fo(c))
        self.assertEqual(out[0]["card_id"], "4912684136504818")

    def test_dev_token_en_id_pan_en_formats(self):
        c = self._card(id="tok-XYZ-4818",
                       formats=[{"number": "4912684136504818",
                                 "numberType": {"id": "PAN"}}])
        out = productos_desde_fo(self._fo(c))
        self.assertEqual(out[0]["card_id"], "4912684136504818")

    def test_formats_enmascarado_cae_al_id_pan(self):
        # El escenario que preocupa a Fabian: formats existe pero NO es un PAN.
        c = self._card(id="4912684136504818",
                       formats=[{"number": "****4818", "numberType": {"id": "PAN"}}])
        out = productos_desde_fo(self._fo(c))
        self.assertEqual(out[0]["card_id"], "4912684136504818")

    def test_formats_con_ultimos4_cae_al_id_pan(self):
        c = self._card(id="4912684136504818",
                       formats=[{"number": "4818", "numberType": {"id": "PAN"}}])
        out = productos_desde_fo(self._fo(c))
        self.assertEqual(out[0]["card_id"], "4912684136504818")

