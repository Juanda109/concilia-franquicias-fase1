import json
import unittest
from datetime import datetime
from pathlib import Path

from application.trx.aso_rules import (
    clasificar_investigacion,
    extraer_card_id,
    extraer_detalle,
    filtrar_por_rango,
    parse_movimientos_operations,
    recurrencia_por_subject,
)

# Fixtures = data real del simulador (garantiza congruencia sim <-> reglas).
SIM_DATA = (
    Path(__file__).resolve().parents[3]
    / "co_pqrs_back_trx_aso_simulator"
    / "data"
)

_SUBJECTS = ("no reconoce", "transaccion no reconocida", "transacción no reconocida")


def _load(*parts: str) -> dict:
    with (SIM_DATA.joinpath(*parts)).open("r", encoding="utf-8") as fh:
        return json.load(fh)


class RecurrenciaTests(unittest.TestCase):
    def test_recurrencia_subject_reciente_cuenta_pero_no_alcanza_el_tope(self) -> None:
        # Politica IT4.6: hasta 3 solicitudes en 6 meses. Un solo caso reciente
        # se cuenta, pero no desvia.
        issues = _load("salesforce", "1013634958.json")["data"]
        r = recurrencia_por_subject(
            issues, subjects_txnr=_SUBJECTS, now=datetime(2026, 8, 13)
        )
        self.assertFalse(r["has_recurrence"])
        self.assertGreaterEqual(r["matched_total"], 2)  # 2 subjects TXNR
        self.assertEqual(r["recent_total"], 1)          # solo el de 2026-08-01 es <=6m
        self.assertEqual(r["max_solicitudes"], 3)

    def test_recurrencia_con_tope_uno_desvia_al_primer_caso(self) -> None:
        # Comportamiento anterior, recuperable por configuracion.
        issues = _load("salesforce", "1013634958.json")["data"]
        r = recurrencia_por_subject(
            issues, subjects_txnr=_SUBJECTS, now=datetime(2026, 8, 13), max_solicitudes=1
        )
        self.assertTrue(r["has_recurrence"])

    def test_recurrencia_alcanza_el_tope_con_tres_casos_recientes(self) -> None:
        issues = [
            {"subject": "Usuario reporta que no reconoce la transaccion",
             "creationDate": f"2026-0{m}-05T09:00:00.000-0500"}
            for m in (5, 6, 7)
        ]
        r = recurrencia_por_subject(issues, subjects_txnr=_SUBJECTS, now=datetime(2026, 8, 13))
        self.assertTrue(r["has_recurrence"])
        self.assertEqual(r["recent_total"], 3)

    def test_recurrencia_dos_casos_recientes_no_alcanza_el_tope(self) -> None:
        issues = [
            {"subject": "Usuario reporta que no reconoce la transaccion",
             "creationDate": f"2026-0{m}-05T09:00:00.000-0500"}
            for m in (6, 7)
        ]
        r = recurrencia_por_subject(issues, subjects_txnr=_SUBJECTS, now=datetime(2026, 8, 13))
        self.assertFalse(r["has_recurrence"])
        self.assertEqual(r["recent_total"], 2)

    def test_recurrencia_solo_antiguo_no_dispara(self) -> None:
        issues = [
            {"subject": "Transaccion no reconocida - reclamo previo",
             "creationDate": "2025-01-10T09:00:00.000-0500"}
        ]
        r = recurrencia_por_subject(issues, subjects_txnr=_SUBJECTS, now=datetime(2026, 8, 13))
        self.assertFalse(r["has_recurrence"])

    def test_recurrencia_sin_subject_txnr(self) -> None:
        issues = [
            {"subject": "Bloqueo de productos - radicaciones iniciales",
             "creationDate": "2026-08-10T09:00:00.000-0500"}
        ]
        r = recurrencia_por_subject(issues, subjects_txnr=_SUBJECTS, now=datetime(2026, 8, 13))
        self.assertFalse(r["has_recurrence"])
        self.assertEqual(r["matched_total"], 0)


class CardIdTests(unittest.TestCase):
    def test_extraer_card_id_por_ultimos4(self) -> None:
        fo = _load("financial_overview", "1013634960.json")
        self.assertEqual(extraer_card_id(fo, match_value="0060"), "4912680517940060")

    def test_extraer_card_id_no_match(self) -> None:
        fo = _load("financial_overview", "1013634960.json")
        self.assertIsNone(extraer_card_id(fo, match_value="9999"))


class MovimientosTests(unittest.TestCase):
    """Listado de movimientos desde /cards/v2/operations (cambio 2026-08-25).

    Antes se leia /cards/v2/cards/{card_id}/transactions, retirado tras devolver
    500 de forma sistematica. `operations` ya trae el dia completo CON detalle,
    asi que el paso 2.4.0.1.9 puede mostrarlo sin una segunda llamada.
    """

    def test_parse_desde_operations(self) -> None:
        ops = _load("operations", "4912680517940060.json")
        movs = parse_movimientos_operations(ops)
        self.assertTrue(movs)
        primero = movs[0]
        # Contrato que ya consumia el agente.
        for campo in ("id", "descripcion", "valor", "fecha", "status"):
            self.assertIn(campo, primero)
        self.assertIsInstance(primero["valor"], float)
        self.assertRegex(primero["fecha"], r"^\d{4}-\d{2}-\d{2}$")

    def test_incluye_el_detalle_para_mostrarlo(self) -> None:
        """2.4.0.1.9 muestra el detalle: debe venir en el mismo listado."""

        movs = parse_movimientos_operations(_load("operations", "4912680517940060.json"))
        primero = movs[0]
        for campo in ("hora", "establecimiento", "moneda", "intereses",
                      "numero_extracto", "numero_operacion"):
            self.assertIn(campo, primero)

    def test_payload_vacio(self) -> None:
        self.assertEqual(parse_movimientos_operations({}), [])
        self.assertEqual(parse_movimientos_operations({"data": []}), [])

    def test_tolera_campos_ausentes(self) -> None:
        """Un movimiento incompleto se muestra, no desaparece del listado."""

        movs = parse_movimientos_operations(
            {"data": [{"operations": [{"id": "TX1"}]}]}
        )
        self.assertEqual(len(movs), 1)
        self.assertEqual(movs[0]["id"], "TX1")
        self.assertIsNone(movs[0]["valor"])
        self.assertEqual(movs[0]["descripcion"], "Sin descripcion")


class FiltroDeRangoTests(unittest.TestCase):
    """El filtro de importe se aplica en nuestro codigo: operations no lo acepta."""

    MOVS = [
        {"id": "A", "valor": 20000.0},
        {"id": "B", "valor": 150000.0},
        {"id": "C", "valor": 750000.0},
        {"id": "D", "valor": None},
    ]

    def test_filtra_por_rango(self) -> None:
        dentro, fuera = filtrar_por_rango(self.MOVS, monto_min=35000, monto_max=500000)
        self.assertEqual([m["id"] for m in dentro], ["B", "D"])
        self.assertEqual(fuera, 2)  # A por debajo, C por encima

    def test_cuenta_los_que_quedan_fuera(self) -> None:
        """Quien busca su compra de 750.000 no puede recibir "no hay compras"."""

        dentro, fuera = filtrar_por_rango(
            [{"id": "C", "valor": 750000.0}], monto_min=35000, monto_max=500000
        )
        self.assertEqual(dentro, [])
        self.assertEqual(fuera, 1)

    def test_sin_rango_devuelve_todo(self) -> None:
        dentro, fuera = filtrar_por_rango(self.MOVS, monto_min=None, monto_max=None)
        self.assertEqual(len(dentro), 4)
        self.assertEqual(fuera, 0)

    def test_movimiento_sin_importe_se_conserva(self) -> None:
        """Sin importe no se puede excluir con criterio."""

        dentro, _ = filtrar_por_rango(
            [{"id": "D", "valor": None}], monto_min=35000, monto_max=500000
        )
        self.assertEqual(len(dentro), 1)


class DetalleYClasificacionTests(unittest.TestCase):
    def _detalle(self, pan: str, tx_id: str) -> dict:
        ops = _load("operations", f"{pan}.json")
        return extraer_detalle(ops, tx_id=tx_id)

    def test_detalle_match_por_id(self) -> None:
        det = self._detalle("4912680517940060", "TXC01")
        self.assertIsNotNone(det)
        self.assertEqual(det["eci"], "5")
        self.assertIs(det["eCard"], True)

    def test_clasificacion_devolucion(self) -> None:
        det = self._detalle("4912680517940061", "TXD01")
        r = clasificar_investigacion(det, origin_flag="TDC")
        self.assertEqual(r["resultado"], "devolucion")
        self.assertFalse(r["pendiente_tdc"])

    def test_clasificacion_pqr_eci_no_permitido(self) -> None:
        det = self._detalle("4912680517940060", "TXC01")
        r = clasificar_investigacion(det, origin_flag="TDC")
        self.assertEqual(r["resultado"], "pqr")

    def test_clasificacion_presencial_eci_9(self) -> None:
        det = self._detalle("4912680517940067", "TXH01")
        r = clasificar_investigacion(det, origin_flag="TDC")
        self.assertEqual(r["resultado"], "presencial")

    def test_clasificacion_reversado(self) -> None:
        det = self._detalle("4912680517940068", "TXI01")
        r = clasificar_investigacion(det, origin_flag="TDC")
        self.assertEqual(r["resultado"], "reversado")

    def test_clasificacion_pqr_eci_vacio(self) -> None:
        det = self._detalle("4912680517940069", "TXJ01")
        r = clasificar_investigacion(det, origin_flag="TDC")
        self.assertEqual(r["resultado"], "pqr")

    def test_pendiente_tdc(self) -> None:
        det = self._detalle("4912680517940064", "TXG01")
        r = clasificar_investigacion(det, origin_flag="TDC")
        self.assertTrue(r["pendiente_tdc"])


class ProductosTests(unittest.TestCase):
    def _rows(self):
        return [
            {"contract_id": "00131003201300060", "contract_status_type_desc": "ACTIVO",
             "origin_flag": "TDC", "card_flag": True, "card_type": "M", "card_brand": "VISA",
             "last_four_pan_id": "0060", "product_desc": "Tarjeta de Credito"},
            {"contract_id": "00131002201300002", "contract_status_type_desc": "ACTIVO",
             "origin_flag": "TDC", "card_flag": False, "card_type": "M", "card_brand": "VISA",
             "last_four_pan_id": "0002", "product_desc": "Tarjeta de Credito"},
            {"contract_id": "00131009000000009", "contract_status_type_desc": "CANCELADO",
             "origin_flag": "TDC", "card_flag": True, "card_type": "M", "card_brand": "VISA",
             "last_four_pan_id": "0009", "product_desc": "Tarjeta de Credito"},
            {"contract_id": "00131008000000008", "contract_status_type_desc": "ACTIVO",
             "origin_flag": "CREDITO", "card_flag": True, "card_type": "M", "card_brand": "VISA",
             "last_four_pan_id": "0008", "product_desc": "Credito de consumo"},
            {"contract_id": "00131010000000010", "contract_status_type_desc": "ACTIVO",
             "origin_flag": "PASIVO", "card_flag": True, "card_type": "A", "card_brand": "",
             "last_four_pan_id": "0010", "product_desc": "Cuenta de ahorros"},
        ]

    def test_filtra_por_estado_origin_y_card_flag(self) -> None:
        from application.trx.aso_rules import filtrar_productos

        out = filtrar_productos(self._rows())
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["contract_id"], "00131003201300060")
        self.assertEqual(out[0]["last_four"], "0060")

    def test_sin_productos_validos(self) -> None:
        from application.trx.aso_rules import filtrar_productos

        rows = [r for r in self._rows() if r["card_flag"] is False]
        self.assertEqual(filtrar_productos(rows), [])

    # --- Criterio de Fabian (diagrama, 24/08) --------------------------------
    # origin_flag=TDC -> contract_status_type_desc=ACTIVO -> card_type en
    # {D, M} -> card_flag=true. Sustituye al criterio del 21/08 (VIGENTE ya no
    # entra; los seeds de dev se realinearon a ACTIVO).
    def _row_con_estado(self, estado: str, card_type: str = "M") -> dict:
        return {
            "contract_id": "00131003201300060",
            "contract_status_type_desc": estado,
            "origin_flag": "TDC",
            "card_flag": True,
            "card_type": card_type,
            "card_brand": "VISA",
            "last_four_pan_id": "0060",
            "product_desc": "Tarjeta de Credito",
        }

    def test_acepta_estado_activo(self) -> None:
        """El valor real de produccion."""

        from application.trx.aso_rules import filtrar_productos

        out = filtrar_productos([self._row_con_estado("ACTIVO")])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["contract_id"], "00131003201300060")

    def test_vigente_ya_no_entra(self) -> None:
        """Criterio 24/08: solo ACTIVO. VIGENTE era un artefacto de los seeds."""

        from application.trx.aso_rules import filtrar_productos

        self.assertEqual(filtrar_productos([self._row_con_estado("VIGENTE")]), [])

    def test_estado_es_insensible_a_mayusculas_y_espacios(self) -> None:
        from application.trx.aso_rules import filtrar_productos

        for estado in ("activo", "Activo", " ACTIVO "):
            with self.subTest(estado=estado):
                self.assertEqual(
                    len(filtrar_productos([self._row_con_estado(estado)])),
                    1,
                    f"no acepto el estado {estado!r}",
                )

    def test_card_type_d_y_m_entran_p_y_a_no(self) -> None:
        """Cuarto eslabon de la cadena: card_type en {D, M}."""

        from application.trx.aso_rules import filtrar_productos

        for ctype, esperado in (("D", 1), ("M", 1), ("m", 1), (" d ", 1),
                                ("P", 0), ("A", 0), ("", 0)):
            with self.subTest(card_type=ctype):
                self.assertEqual(
                    len(filtrar_productos([self._row_con_estado("ACTIVO", ctype)])),
                    esperado,
                )

    def test_pasivo_ya_no_entra(self) -> None:
        """Criterio 24/08: solo origin_flag=TDC (las cuentas quedan fuera)."""

        from application.trx.aso_rules import filtrar_productos

        fila = dict(self._row_con_estado("ACTIVO"), origin_flag="PASIVO")
        self.assertEqual(filtrar_productos([fila]), [])

    def test_otros_estados_siguen_excluidos(self) -> None:
        from application.trx.aso_rules import filtrar_productos

        for estado in ("CANCELADO", "CANCELADA", "INACTIVO", "", "BLOQUEADO", "VIGENTE"):
            with self.subTest(estado=estado):
                self.assertEqual(
                    filtrar_productos([self._row_con_estado(estado)]),
                    [],
                    f"dejo pasar el estado {estado!r}",
                )


if __name__ == "__main__":
    unittest.main()


class ClientesPruebaRealTests(unittest.TestCase):
    """Clientes de prueba reales del usuario: verifica desenlace por card_id/last4.

    - 98787954 (CC 1216963399, PAN ..3399): DEVOLUCION (eci=5, eCard=true, Exitosa).
    - 10482895 (CE 1025079,   PAN ..5079): PRESENCIAL (eCard=false).
    - 01576905 (CC 17389461,  PAN ..9461): PQR (eci=1 contracargable).
    """

    def _resolve(self, customer_id: str, last4: str, tx_id: str) -> dict:
        fo = _load("financial_overview", f"{customer_id}.json")
        card_id = extraer_card_id(fo, match_value=last4)
        self.assertIsNotNone(card_id, f"card_id no resuelto para {customer_id}/{last4}")
        # Cambio 2026-08-25: el listado sale de /cards/v2/operations, no de
        # /cards/v2/cards/{card_id}/transactions (retirado).
        movs = parse_movimientos_operations(_load("operations", f"{card_id}.json"))
        self.assertGreaterEqual(len(movs), 1, f"sin movimientos para {card_id}")
        det = extraer_detalle(_load("operations", f"{card_id}.json"), tx_id=tx_id)
        self.assertIsNotNone(det, f"detalle no encontrado {card_id}/{tx_id}")
        return {
            "card_id": card_id,
            "movs": movs,
            "clasif": clasificar_investigacion(det, origin_flag="TDC"),
        }

    def test_98787954_devolucion(self) -> None:
        r = self._resolve("98787954", "3399", "TXR301")
        self.assertEqual(r["card_id"], "4916555123453399")
        self.assertEqual(r["movs"][0]["valor"], 150000.0)
        self.assertEqual(r["clasif"]["resultado"], "pqr")
        self.assertFalse(r["clasif"]["pendiente_tdc"])

    def test_10482895_presencial(self) -> None:
        r = self._resolve("10482895", "5079", "TXR101")
        self.assertEqual(r["card_id"], "4916555110255079")
        self.assertEqual(r["clasif"]["resultado"], "devolucion")

    def test_eci_contracargables_del_tablero(self) -> None:
        """El tablero fija: contracargables 0,1,2,3,7 -> devolucion.

        El "0" se habia perdido al pasar a un literal {1,2,3,7}, y no habia
        ningun fixture con eci=0 que lo delatara: una compra responsabilidad
        del comercio acababa en el formulario de PQR. Se comprueba tambien que
        el conjunto es el CONFIGURABLE y no un literal: si se restringe, el
        resultado cambia.
        """
        det = {"eci": "0", "eCard": True, "observations": "OPER FINALIZADA CON EXITO"}
        for eci in ("0", "1", "2", "3", "7"):
            r = clasificar_investigacion({**det, "eci": eci}, origin_flag="TDC")
            self.assertEqual(r["resultado"], "devolucion", f"ECI {eci} es contracargable")
        for eci in ("4", "5", "6", "8", ""):
            r = clasificar_investigacion({**det, "eci": eci}, origin_flag="TDC")
            self.assertEqual(r["resultado"], "pqr", f"ECI {eci!r} no es contracargable")
        # presencial ya NO depende del ECI: 4o bloque de observations 10/01
        # (dev f365adc). Con bloques presentes gana a cualquier otra regla.
        self.assertEqual(
            clasificar_investigacion(
                {**det, "eci": "9",
                 "observations": "00 APROBADA |TERMINAL POS |BOGOTA |10 LECTURA CHIP"},
                origin_flag="TDC",
            )["resultado"],
            "presencial",
        )
        # el conjunto llega por parametro y debe respetarse
        r = clasificar_investigacion(
            {**det, "eci": "0"}, origin_flag="TDC", eci_chargeback_set=frozenset({"1"})
        )
        self.assertEqual(r["resultado"], "pqr", "el conjunto configurable debe mandar")

    def test_01576905_devolucion(self) -> None:
        """ECI 1 es contracargable -> devolucion automatica.

        El nombre anterior (test_01576905_pqr) y su asercion "pqr" venian de la
        regla vieja, que estaba invertida. Fabian lo zanjo el 20/08: con ECI
        0,1,2,3,7 el cliente recibe la DEVOLUCION automatica; lo que queda fuera
        de ese conjunto es lo que va al formulario PQR. El merge habia dejado
        las dos aserciones contradictorias en el mismo test.
        """
        r = self._resolve("01576905", "9461", "TXR201")
        self.assertEqual(r["card_id"], "4916555117389461")
        self.assertEqual(r["clasif"]["eci"], "1")
        self.assertEqual(r["clasif"]["resultado"], "devolucion")


class RecurrenciaViaAsoTests(unittest.TestCase):
    """TRX_SALESFORCE_SOURCE=aso consulta la costura; si falla, cae al mock local.

    Antes salesforce_issues() era codigo muerto: la recurrencia solo leia el
    fichero mock y el escenario A del simulador no podia funcionar (H-04).
    """

    def _servicio_con_identidad(self):
        from application.trx.analysis_service import TrxAnalysisService

        service = TrxAnalysisService()
        service._load_identity_from_postgres = lambda _cid: ("1", "1013634958")
        service._request_tsec = lambda: "TSEC-TEST"
        return service

    def _caso(self):
        from domain.trx.models import TrxCase

        return TrxCase(customer_id="1013634958", data={})

    def test_fuente_aso_consulta_la_costura(self) -> None:
        import os
        from unittest.mock import patch

        respuesta = {"data": [{
            "subject": "Usuario reporta que no reconoce la transaccion",
            "creationDate": "2099-01-01T10:00:00.000-0500",
            "issuer": {"identityDocument": {"documentNumber": "1013634958"}},
        }]}
        service = self._servicio_con_identidad()
        # Tope en 1 para que un unico caso reciente desvie: lo que se prueba aqui
        # es que la costura ASO se consulta, no el valor del tope.
        with patch.dict(os.environ, {"TRX_SALESFORCE_SOURCE": "aso", "MAX_TRX_BOT_RECURRENCE": "1"}), \
             patch("infrastructure.persistence.aso_client.TrxAsoClient.get_tsec",
                   return_value="TSEC-ASO"), \
             patch("infrastructure.persistence.aso_client.TrxAsoClient.salesforce_issues",
                   return_value=respuesta) as llamada:
            resultado = service._mock_salesforce_recurrence(self._caso())
        # el TSEC sale del propio cliente ASO (granting ticket via ASO_BASE_URL),
        # no del legacy TRX_TICKET_URL que el configmap deja vacio
        llamada.assert_called_once_with("1-1013634958", "TSEC-ASO")
        self.assertTrue(resultado["has_recurrence"])
        self.assertEqual(resultado["source_used"], "aso")

    def test_costura_caida_cae_al_mock_local_sin_romper(self) -> None:
        import os
        from unittest.mock import patch

        service = self._servicio_con_identidad()
        with patch.dict(os.environ, {"TRX_SALESFORCE_SOURCE": "aso",
                                     "TRX_SALESFORCE_MOCK_FILE": ""}), \
             patch("infrastructure.persistence.aso_client.TrxAsoClient.get_tsec",
                   return_value=""), \
             patch("infrastructure.persistence.aso_client.TrxAsoClient.salesforce_issues",
                   return_value=None):
            resultado = service._mock_salesforce_recurrence(self._caso())
        # fail-open de verdad: sin costura NO se inventa recurrencia, y la traza
        # tiene que poder distinguir el fallback de una respuesta real del ASO
        self.assertFalse(resultado["has_recurrence"])
        self.assertEqual(resultado["source_used"], "aso_fallback_error")

    def test_sin_identidad_en_postgres_no_toca_la_costura_y_avisa(self) -> None:
        import os
        from unittest.mock import patch

        from application.trx.analysis_service import TrxAnalysisService

        service = TrxAnalysisService()
        service._load_identity_from_postgres = lambda _cid: None
        service._request_tsec = lambda: ""
        with patch.dict(os.environ, {"TRX_SALESFORCE_SOURCE": "aso",
                                     "TRX_SALESFORCE_MOCK_FILE": ""}), \
             patch("infrastructure.persistence.aso_client.TrxAsoClient.salesforce_issues") as llamada, \
             self.assertLogs("application.trx.analysis_service", level="WARNING") as logs:
            resultado = service._mock_salesforce_recurrence(self._caso())
        llamada.assert_not_called()
        self.assertEqual(resultado["source_used"], "aso_fallback_sin_identidad")
        self.assertTrue(any("sin identidad" in m for m in logs.output))

    def test_fuente_mock_no_toca_la_costura(self) -> None:
        import os
        from unittest.mock import patch

        service = self._servicio_con_identidad()
        with patch.dict(os.environ, {"TRX_SALESFORCE_SOURCE": "mock"}), \
             patch("infrastructure.persistence.aso_client.TrxAsoClient.salesforce_issues") as llamada:
            service._mock_salesforce_recurrence(self._caso())
        llamada.assert_not_called()

    def test_tsec_reportado_es_el_que_se_uso(self) -> None:
        """tsec_requested tiene que reflejar el ticket REAL de la llamada.

        Reportaba el TSEC legacy (TRX_TICKET_URL, vacio en el configmap) y
        salia False aunque el granting ticket se pidiera y se usara.
        """

        import os
        from unittest.mock import patch

        respuesta = {"data": []}
        from application.trx.analysis_service import TrxAnalysisService

        service = TrxAnalysisService()
        service._load_identity_from_postgres = lambda _cid: ("1", "1013634958")
        service._request_tsec = lambda: ""          # legacy vacio, como en dev
        with patch.dict(os.environ, {"TRX_SALESFORCE_SOURCE": "aso"}), \
             patch("infrastructure.persistence.aso_client.TrxAsoClient.get_tsec",
                   return_value="TSEC-DEL-CLIENTE"), \
             patch("infrastructure.persistence.aso_client.TrxAsoClient.salesforce_issues",
                   return_value=respuesta):
            resultado = service._mock_salesforce_recurrence(self._caso())
        self.assertTrue(resultado["tsec_requested"])

    def test_sin_tsec_el_campo_sigue_en_false(self) -> None:
        import os
        from unittest.mock import patch

        from application.trx.analysis_service import TrxAnalysisService

        service = TrxAnalysisService()
        service._load_identity_from_postgres = lambda _cid: ("1", "1013634958")
        service._request_tsec = lambda: ""
        with patch.dict(os.environ, {"TRX_SALESFORCE_SOURCE": "aso"}), \
             patch("infrastructure.persistence.aso_client.TrxAsoClient.get_tsec",
                   return_value=""), \
             patch("infrastructure.persistence.aso_client.TrxAsoClient.salesforce_issues",
                   return_value={"data": []}):
            resultado = service._mock_salesforce_recurrence(self._caso())
        self.assertFalse(resultado["tsec_requested"])


class CacheOperacionesTests(unittest.TestCase):
    """El detalle del dia se pide una vez, no una por movimiento elegido.

    /cards/v2/operations devuelve TODAS las operaciones de la fecha; el flujo
    pedia una por cada movimiento que el cliente seleccionaba y el caso admite
    hasta 3 transacciones.
    """

    def setUp(self) -> None:
        from infrastructure.persistence import aso_client

        aso_client._OPERATIONS_CACHE.clear()

    def test_misma_tarjeta_y_fecha_llama_una_sola_vez(self) -> None:
        from unittest.mock import patch

        from infrastructure.persistence.aso_client import TrxAsoClient

        cliente = TrxAsoClient()
        with patch.object(TrxAsoClient, "_get", return_value={"data": [{"id": "T1"}]}) as get:
            for _ in range(3):
                cliente.operations("4912680517940060", operation_date="20260806")
        self.assertEqual(get.call_count, 1)

    def test_otra_fecha_vuelve_a_consultar(self) -> None:
        from unittest.mock import patch

        from infrastructure.persistence.aso_client import TrxAsoClient

        cliente = TrxAsoClient()
        with patch.object(TrxAsoClient, "_get", return_value={"data": []}) as get:
            cliente.operations("4912680517940060", operation_date="20260806")
            cliente.operations("4912680517940060", operation_date="20260805")
        self.assertEqual(get.call_count, 2)

    def test_otra_tarjeta_vuelve_a_consultar(self) -> None:
        from unittest.mock import patch

        from infrastructure.persistence.aso_client import TrxAsoClient

        cliente = TrxAsoClient()
        with patch.object(TrxAsoClient, "_get", return_value={"data": []}) as get:
            cliente.operations("4912680517940060", operation_date="20260806")
            cliente.operations("5512340000001234", operation_date="20260806")
        self.assertEqual(get.call_count, 2)

    def test_una_respuesta_vacia_del_aso_no_se_cachea(self) -> None:
        """None es fallo, no dato: cachearlo perpetuaria una caida transitoria."""

        from unittest.mock import patch

        from infrastructure.persistence.aso_client import TrxAsoClient

        cliente = TrxAsoClient()
        with patch.object(TrxAsoClient, "_get", return_value=None) as get:
            cliente.operations("4912680517940060", operation_date="20260806")
            cliente.operations("4912680517940060", operation_date="20260806")
        self.assertEqual(get.call_count, 2)

class ExtraerCardIdPrefiereFormatsTests(unittest.TestCase):
    """Fix 31/08 (tercera copia de la asuncion 'el id ES el PAN'): al localizar
    el contrato, extraer_card_id debe devolver el PAN de formats[].number y no
    el id (token). El resolvedor de PAN del agente pisaba los productos
    correctos con el token que salia de aqui via /v1/trx/card-id."""

    def _contrato(self) -> dict:
        return {
            "id": "tok-4979-ZZZZ",
            "number": "0063",
            "productType": "CARD",
            "formats": [{"number": "4912680517944979",
                         "numberType": {"id": "PAN"}}],
        }

    def test_match_por_number_devuelve_el_pan_de_formats(self):
        fo = {"data": {"contracts": [self._contrato()]}}
        self.assertEqual(
            extraer_card_id(fo, match_value="0063"),
            "4912680517944979",
        )

    def test_sin_formats_devuelve_el_id_como_antes(self):
        c = self._contrato(); c.pop("formats")
        fo = {"data": {"contracts": [c]}}
        self.assertEqual(extraer_card_id(fo, match_value="0063"), "tok-4979-ZZZZ")

