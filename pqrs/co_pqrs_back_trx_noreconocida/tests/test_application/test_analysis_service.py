import unittest

from application.trx.analysis_service import TrxAnalysisService
from domain.trx.models import TrxCase


class TrxFase1Tests(unittest.TestCase):
    """Fase 1: movimientos mock por producto+fecha, vigencia y regla de valor."""

    def setUp(self) -> None:
        import os
        from pathlib import Path

        self.service = TrxAnalysisService()
        mock_file = (
            Path(__file__).resolve().parents[2] / "data" / "movimientos_mock.json"
        )
        self._prev = {
            "TRX_MOVEMENTS_SOURCE": os.environ.get("TRX_MOVEMENTS_SOURCE"),
            "TRX_MOVEMENTS_MOCK_FILE": os.environ.get("TRX_MOVEMENTS_MOCK_FILE"),
        }
        os.environ["TRX_MOVEMENTS_SOURCE"] = "mock"
        os.environ["TRX_MOVEMENTS_MOCK_FILE"] = str(mock_file)

    def tearDown(self) -> None:
        import os

        for key, value in self._prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _mov_case(self, fecha: str, franquicia: str = "VISA") -> TrxCase:
        return TrxCase(
            customer_id="1013634958",
            product_id="4912680517944979",
            data={
                "contract_id": "4912680517944979",
                "fecha": fecha,
                "card_franchise": franquicia,
            },
        )

    def test_movimientos_visa_dentro_de_vigencia_lista(self) -> None:
        result = self.service.consultar_movimientos_aso(self._mov_case("15/07/2026"))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.id_message, 204)
        self.assertEqual(len(result.data["movimientos"]), 3)

    def test_movimientos_fecha_vencida_visa(self) -> None:
        # >180 días atrás para VISA
        result = self.service.consultar_movimientos_aso(self._mov_case("01/01/2025"))
        self.assertEqual(result.status, "not_found")
        self.assertEqual(result.id_message, 203)
        self.assertTrue(result.data["vencida"])

    def test_movimientos_sin_datos_en_la_fecha(self) -> None:
        result = self.service.consultar_movimientos_aso(self._mov_case("20/07/2026"))
        self.assertEqual(result.status, "not_found")
        self.assertEqual(result.data["movimientos"], [])
        self.assertFalse(result.data["vencida"])

    def test_movimientos_fecha_invalida(self) -> None:
        result = self.service.consultar_movimientos_aso(self._mov_case("2026/07/15"))
        self.assertEqual(result.status, "not_found")
        self.assertTrue(result.data.get("invalid_date"))

    def test_valor_menor_a_35000_redirige_pqr(self) -> None:
        r = self.service.evaluar_transaccion_individual(20000)
        self.assertEqual(r.status, "REDIRECT_PQR")
        self.assertEqual(r.data["rule"], "monto_menor_minimo")

    def test_valor_en_rango_aprobado(self) -> None:
        r = self.service.evaluar_transaccion_individual(50000)
        self.assertEqual(r.status, "APPROVED")
        self.assertTrue(r.data["in_range"])

    def test_valor_mayor_a_500000_redirige_pqr(self) -> None:
        r = self.service.evaluar_transaccion_individual(600000)
        self.assertEqual(r.status, "REDIRECT_PQR")
        self.assertEqual(r.data["rule"], "monto_mayor_maximo")

    # --- Recurrencia Salesforce (2.4.0.1) -----------------------------------
    def test_recurrencia_mock_file_tiene_default(self) -> None:
        # Regresion: sin default, salesforce_mock_file queda vacio, el aso mock
        # nunca se carga (matched_total=0) y un cliente CON historial terminaba
        # en el flujo normal en vez de redirigir a PQR.
        from infrastructure.core.config import load_trx_source_settings

        self.assertTrue(
            load_trx_source_settings().salesforce_mock_file.endswith(
                "aso_salesforce.json"
            )
        )

    def _sf_case(
        self,
        doc: str,
        creation_date: str,
        subject: str = "Usuario reporta que no reconoce la transaccion",
        casos: int = 1,
    ) -> TrxCase:
        payload = {
            "data": [
                {
                    "subject": subject,
                    "creationDate": creation_date,
                    "issuer": {"identityDocument": {"documentNumber": doc}},
                }
                for _ in range(casos)
            ]
        }
        return TrxCase(customer_id=doc, data={"salesforce_mock": payload})

    def test_recurrencia_reciente_redirige_pqr(self) -> None:
        # Politica IT4.6: maximo 3 solicitudes por tipologia en 6 meses. Con tres
        # casos recientes el cliente ya agoto el tope y se le desvia.
        from datetime import datetime, timezone

        reciente = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")
        r = self.service.consultar_recurrencia_salesforce(
            self._sf_case("80425247", reciente, casos=3)
        )
        self.assertEqual(r.status, "REDIRECT_PQR")
        self.assertTrue(r.data["identificacion_6_meses"])
        self.assertGreaterEqual(r.data["recent_total"], 3)

    def test_recurrencia_un_solo_caso_reciente_no_redirige(self) -> None:
        # Un caso previo no agota el tope: el cliente puede radicar otra solicitud.
        from datetime import datetime, timezone

        reciente = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")
        r = self.service.consultar_recurrencia_salesforce(
            self._sf_case("80425247", reciente, casos=1)
        )
        self.assertNotEqual(r.status, "REDIRECT_PQR")
        self.assertEqual(r.data["recent_total"], 1)

    def test_recurrencia_antigua_no_redirige(self) -> None:
        # subject TXNR pero fuera de los 6 meses -> matched pero no recent -> no redirige.
        r = self.service.consultar_recurrencia_salesforce(
            self._sf_case("80425247", "2020-01-01T00:00:00.000+0000")
        )
        self.assertEqual(r.status, "ok")
        self.assertFalse(r.data["identificacion_6_meses"])
        self.assertEqual(r.data["matched_total"], 1)
        self.assertEqual(r.data["recent_total"], 0)

    def test_recurrencia_sin_subject_txnr_no_redirige(self) -> None:
        # subject reciente pero NO relacionado a TXNR -> no cuenta como recurrencia.
        from datetime import datetime, timezone

        reciente = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")
        r = self.service.consultar_recurrencia_salesforce(
            self._sf_case("80425247", reciente, subject="Bloqueo de productos - radicaciones iniciales")
        )
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.data["matched_total"], 0)


if __name__ == "__main__":
    unittest.main()