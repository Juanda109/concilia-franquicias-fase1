"""Configuracion del cliente ASO y manejo del TSEC.

El cliente de Doble Cobro es hermano del de Transaccion No Reconocida y consume
la MISMA pasarela. Nacio como una copia que perdio por el camino tres cosas
--``verify_ssl``, ``timeout`` y la traza sin token-- y el sintoma era mudo:
contra el ASO real el handshake del grantingTicket moria, el TSEC quedaba vacio,
las dos llamadas salian sin autenticar y el flujo acababa en el formulario PQR
como si el cliente no tuviera productos.

Estos tests fijan que esas tres cosas se sigan leyendo del entorno.
"""

from __future__ import annotations

import asyncio
import logging
import unittest
from unittest.mock import patch

from infrastructure.core.config import load_doble_cobro_aso_settings
from infrastructure.persistence import doble_cobro_aso_client as aso_module
from infrastructure.persistence.doble_cobro_aso_client import (
    DobleCobroAsoClient,
    _tsec_debug,
)

_ASO_ENV = (
    "DC_ASO_BASE_URL",
    "DC_ASO_REAL_URL",
    "DC_ASO_SIMULATOR_URL",
    "DC_ASO_TICKET_URL",
    "DC_ASO_API_VERIFY_SSL",
    "DC_ASO_API_TIMEOUT",
    "DC_ASO_API_USER_ID",
    "DC_ASO_API_PASSWORD",
    "DC_ASO_API_CONSUMER_ID",
    "DC_ASO_API_AUTHENTICATION_TYPE",
    "ASO_SOURCE",
    "ASO_TRACE_TSEC_FULL",
)


def _env(**overrides: str):
    """Entorno limpio de variables ASO, con solo lo que pide el test.

    El ``.env`` del servicio ya esta cargado en ``os.environ`` cuando corren los
    tests, asi que hay que borrarlo o el caso mide la maquina, no el codigo.
    """

    base = {name: "" for name in _ASO_ENV}
    base.update(overrides)
    return patch.dict("os.environ", base, clear=False)


class AsoSettingsTests(unittest.TestCase):
    def test_verify_ssl_is_read_from_the_environment(self) -> None:
        """El ASO real usa certificado corporativo: hay que poder desactivarlo."""

        with _env(DC_ASO_API_VERIFY_SSL="false"):
            self.assertFalse(load_doble_cobro_aso_settings().api_verify_ssl)

        for verdadero in ("true", "1", "yes", "on"):
            with _env(DC_ASO_API_VERIFY_SSL=verdadero):
                self.assertTrue(
                    load_doble_cobro_aso_settings().api_verify_ssl,
                    verdadero,
                )

    def test_verify_ssl_defaults_to_true(self) -> None:
        """Sin configurar se verifica: desactivarlo tiene que ser deliberado."""

        with _env():
            self.assertTrue(load_doble_cobro_aso_settings().api_verify_ssl)

    def test_timeout_is_read_from_the_environment(self) -> None:
        with _env(DC_ASO_API_TIMEOUT="45"):
            self.assertEqual(load_doble_cobro_aso_settings().api_timeout, 45.0)

    def test_a_broken_timeout_falls_back_instead_of_crashing(self) -> None:
        with _env(DC_ASO_API_TIMEOUT="ni-idea"):
            self.assertEqual(load_doble_cobro_aso_settings().api_timeout, 30.0)

    def test_the_client_applies_both_to_its_http_client(self) -> None:
        """Que las settings existan no basta: tienen que llegar a httpx."""

        with _env(DC_ASO_API_VERIFY_SSL="false", DC_ASO_API_TIMEOUT="45"):
            client = DobleCobroAsoClient()

        self.assertEqual(client.timeout, 45.0)
        self.assertFalse(client.settings.api_verify_ssl)

        with patch.object(aso_module.httpx, "AsyncClient") as fake:
            client._client()

        fake.assert_called_once_with(verify=False, timeout=45.0)


class AsoBaseUrlTests(unittest.TestCase):
    def test_source_real_uses_the_real_url(self) -> None:
        with _env(ASO_SOURCE="real", DC_ASO_REAL_URL="https://aso.real:8050"):
            self.assertEqual(
                load_doble_cobro_aso_settings().base_url,
                "https://aso.real:8050",
            )

    def test_source_simulator_uses_the_simulator_url(self) -> None:
        with _env(ASO_SOURCE="simulator", DC_ASO_SIMULATOR_URL="http://sim:8050"):
            self.assertEqual(
                load_doble_cobro_aso_settings().base_url,
                "http://sim:8050",
            )

    def test_the_manual_override_wins_over_the_switch(self) -> None:
        """Documenta la trampa: con DC_ASO_BASE_URL puesta, ASO_SOURCE no hace nada.

        Es deliberado (es el override manual), pero se presta a creer que se
        probo el ASO real cuando la peticion fue al simulador.
        """

        with _env(
            ASO_SOURCE="real",
            DC_ASO_REAL_URL="https://aso.real:8050",
            DC_ASO_BASE_URL="http://127.0.0.1:8050",
        ):
            settings = load_doble_cobro_aso_settings()

        self.assertEqual(settings.source, "real")
        self.assertEqual(settings.base_url, "http://127.0.0.1:8050")


class TsecDebugTests(unittest.TestCase):
    _TSEC = "TSEC-REAL-SIMULADO-abc123=="

    def test_a_missing_tsec_says_the_request_goes_unauthenticated(self) -> None:
        debug = _tsec_debug("")
        self.assertFalse(debug["tsec_enviado"])
        self.assertIn("SIN autenticar", debug["tsec_motivo"])

    def test_the_fingerprint_never_leaks_the_token(self) -> None:
        with _env():
            debug = _tsec_debug(self._TSEC)

        self.assertNotIn("tsec_completo", debug)
        self.assertEqual(debug["tsec_longitud"], len(self._TSEC))
        self.assertTrue(debug["tsec_termina_en_padding"])
        self.assertEqual(len(debug["tsec_sha256"]), 64)

    def test_the_full_token_never_appears_even_behind_the_old_flag(self) -> None:
        """KYNS IT 3: la huella basta para correlacionar; el token completo no se persiste."""

        with _env(ASO_TRACE_TSEC_FULL="true"):
            debug = _tsec_debug(self._TSEC)
        self.assertNotIn("tsec_completo", debug)
        self.assertNotIn(self._TSEC, str(debug))


class AsoRequestTraceTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_request_without_tsec_is_still_traced(self) -> None:
        """Sin token es justo cuando hace falta la traza, y era la que faltaba."""

        with _env(DC_ASO_BASE_URL="http://sim:8050"):
            client = DobleCobroAsoClient()

        with self.assertLogs(aso_module.logger, level=logging.INFO) as registro:
            await client._get(
                "/financial-overview/v0/financial-overview",
                {"customer.id": "13083558"},
                tsec=None,
                operation="financial_overview",
            )

        peticiones = [
            linea for linea in registro.output if "ASO REQUEST" in linea
        ]
        self.assertEqual(len(peticiones), 1)
        self.assertIn("SIN autenticar", peticiones[0])


class TsecFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_failed_granting_ticket_returns_empty_and_never_raises(self) -> None:
        """El fail-open es deliberado, pero deja rastro en el log."""

        with _env(DC_ASO_BASE_URL="http://127.0.0.1:1"):  # puerto cerrado
            client = DobleCobroAsoClient(timeout=0.5)

        with self.assertLogs(aso_module.logger, level=logging.ERROR) as registro:
            tsec = await asyncio.wait_for(client.get_tsec(), timeout=10)

        self.assertEqual(tsec, "")
        self.assertTrue(any("TSEC ERROR" in linea for linea in registro.output))


if __name__ == "__main__":
    unittest.main()
