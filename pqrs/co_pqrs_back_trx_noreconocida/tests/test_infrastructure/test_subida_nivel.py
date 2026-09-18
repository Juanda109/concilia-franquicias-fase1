"""Subida de nivel: notificacion push previa al bloqueo de tarjeta.

Ceremonia de 4 llamadas contra el ASO antes de bloquear:
  1. GET  /security/v0/user-status      -> deviceId activo
  2. POST /cards/v2/operations          -> 403 + authenticationtype=241
  3. POST /cards/v2/operations (+data)  -> 401 + challenge/state, ENVIA el push
  4. GET  /security/v0/order-chanel/... -> pending | accepted
y solo para el bloqueo DEFINITIVO:
  5. POST /cards/v2/operations (+state) -> 200, ejecuta la cancelacion

El test mas importante de este fichero es
`TemporalNoCancelaTests.test_temporal_nunca_llama_a_operations`: el paso 5
cancela la tarjeta y pide reexpedicion, asi que ejecutarlo en el caso temporal le
cancelaria la tarjeta a un cliente que solo queria apagarla.
"""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

import httpx

os.environ.setdefault("ASO_BASE_URL", "https://aso.test")

from infrastructure.entrypoint.api.router.v0 import trx_router as R  # noqa: E402
from infrastructure.persistence import aso_client as ac  # noqa: E402


class _AsoFalso:
    """ASO de prueba que registra cada llamada y modela la ceremonia."""

    def __init__(self, *, device_status="ACTIVE", auth_type="241",
                 challenge="CH-1", estado_orden="accepted", status_final=200,
                 estado_http=200):
        self.estado_http = estado_http
        self.llamadas: list[str] = []
        self.cabeceras_recibidas: list[dict] = []
        self.device_status = device_status
        self.auth_type = auth_type
        self.challenge = challenge
        self.estado_orden = estado_orden
        self.status_final = status_final

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def get(self, url, params=None, headers=None):
        req = httpx.Request("GET", url, params=params)
        if "user-status" in url:
            self.llamadas.append("GET user-status")
            return httpx.Response(200, request=req, json={"data": [{
                "device": {"id": "BB-04-DEV",
                           "softToken": {"status": {"id": self.device_status}}},
                "channel": {"status": {"id": "ACTIVE"}}}]})
        self.llamadas.append("GET order-chanel")
        if self.estado_http == 204:
            return httpx.Response(204, request=req)
        if self.estado_http != 200:
            return httpx.Response(self.estado_http, request=req, json={})
        return httpx.Response(200, request=req,
                              json={"data": {"status": {"id": self.estado_orden}}})

    def post(self, url, headers=None, json=None):
        self.llamadas.append("POST operations")
        self.cabeceras_recibidas.append({k.lower(): v for k, v in (headers or {}).items()})
        req = httpx.Request("POST", url)
        cab = {k.lower(): v for k, v in (headers or {}).items()}
        if cab.get("authenticationstate"):
            return httpx.Response(self.status_final, request=req, json={})
        if cab.get("authenticationdata"):
            return httpx.Response(401, request=req, json={}, headers={
                "authenticationChallenge": self.challenge,
                "authenticationstate": "ST-1"})
        return httpx.Response(403, request=req, json={},
                              headers={"authenticationtype": self.auth_type})

    def patch(self, url, headers=None, json=None):
        self.llamadas.append("PATCH activations")
        return httpx.Response(200, request=httpx.Request("PATCH", url), json={})


def _con_aso(aso):
    """Parchea el cliente ASO y silencia las trazas."""

    def _account_id_falso(**_k):
        # get_trx_identity_by_card es sincrono (se corre via asyncio.to_thread);
        # el fake termina en 8952 para las aserciones product=cuenta-8952.
        return {"account_id": "00130136005099008952", "personal_id": "123"}

    return (
        mock.patch.object(ac, "schedule_trace_event", lambda **k: None),
        mock.patch.object(ac.TrxAsoClient, "_client", lambda self: aso),
        mock.patch.object(ac.TrxAsoClient, "get_tsec", lambda self: "TSEC"),
        mock.patch.object(
            R._analysis_service, "get_trx_identity_by_card", _account_id_falso
        ),
    )


def _ejecutar(corutina, aso):
    parches = _con_aso(aso)
    for p in parches:
        p.start()
    try:
        resultado = corutina()
        # subida_nivel_estado es sincrono (threadpool); el resto sigue async.
        if asyncio.iscoroutine(resultado):
            return asyncio.run(resultado)
        return resultado
    finally:
        for p in parches:
            p.stop()


class UserStatusTests(unittest.TestCase):
    def test_toma_el_primer_dispositivo_activo(self):
        aso = _AsoFalso()
        parches = _con_aso(aso)
        for p in parches:
            p.start()
        try:
            resultado = ac.TrxAsoClient().user_status("CC1", tsec="T")
        finally:
            for p in parches:
                p.stop()
        self.assertTrue(resultado["activo"])
        self.assertEqual(resultado["device_id"], "BB-04-DEV")

    def test_dispositivo_bloqueado_no_sirve(self):
        aso = _AsoFalso(device_status="BLOCKED")
        parches = _con_aso(aso)
        for p in parches:
            p.start()
        try:
            resultado = ac.TrxAsoClient().user_status("CC1", tsec="T")
        finally:
            for p in parches:
                p.stop()
        self.assertFalse(resultado["activo"])
        self.assertEqual(resultado["device_id"], "")


class SubidaNivelTests(unittest.TestCase):
    def test_camino_feliz_envia_el_push(self):
        aso = _AsoFalso()
        r = _ejecutar(
            lambda: R.subida_nivel(card_id="C1", personal_id="123", account_last_four="8952"), aso
        )
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["enviado"])
        self.assertEqual(r["challenge"], "CH-1")
        self.assertEqual(r["authentication_state"], "ST-1")
        # CC + cedula rellenada con ceros a 15 digitos (contrato ASO 28/08)
        self.assertEqual(r["profile_id"], "CC000000000000123")
        # user-status + los DOS primeros POST (403 y 401). Nada mas.
        self.assertEqual(aso.llamadas, ["GET user-status", "POST operations", "POST operations"])

    def test_sin_dispositivo_no_intenta_el_reto(self):
        aso = _AsoFalso(device_status="BLOCKED")
        r = _ejecutar(lambda: R.subida_nivel(card_id="C1", personal_id="123", account_last_four="8952"), aso)
        self.assertEqual(r["status"], "sin_dispositivo")
        self.assertEqual(r["etapa"], "user_status")
        self.assertEqual(aso.llamadas, ["GET user-status"])

    def test_tipo_de_autenticacion_inesperado_corta(self):
        aso = _AsoFalso(auth_type="999")
        r = _ejecutar(lambda: R.subida_nivel(card_id="C1", personal_id="123", account_last_four="8952"), aso)
        self.assertEqual(r["status"], "error")
        self.assertEqual(r["etapa"], "challenge_iniciar")
        # No se envia el push si el reto no es el esperado.
        self.assertEqual(aso.llamadas.count("POST operations"), 1)

    def test_authentication_data_del_push(self):
        """Paso 3: sin authenticationstate y con los campos fijos del contrato."""

        aso = _AsoFalso()
        _ejecutar(lambda: R.subida_nivel(card_id="C1", personal_id="123", account_last_four="8952"), aso)
        datos = aso.cabeceras_recibidas[1]["authenticationdata"]
        self.assertIn("deviceId=BB-04-DEV", datos)
        self.assertIn("profileId=CC000000000000123", datos)
        self.assertIn("channel=12000035", datos)
        self.assertIn("operation=NMONETARY", datos)
        self.assertIn("smc=SMGG20210970", datos)
        self.assertIn("product=cuenta-8952", datos)
        self.assertIn("amount=", datos)
        self.assertNotIn("authenticationstate=", datos)

    def test_limpia_sufijos_del_challenge(self):
        aso = _AsoFalso(challenge="CH-1;;")
        resultado = _ejecutar(
            lambda: ac.TrxAsoClient().challenge_enviar_push(
                "C1",
                device_id="DEV",
                profile_id="CC1",
                account_last_four="8952",
                tsec="TSEC",
            ),
            aso,
        )
        self.assertEqual(resultado["challenge"], "CH-1")

    def test_limpia_dos_puntos_del_challenge_como_contingencia(self):
        aso = _AsoFalso(challenge="CH-1::")
        resultado = _ejecutar(
            lambda: ac.TrxAsoClient().challenge_enviar_push(
                "C1",
                device_id="DEV",
                profile_id="CC1",
                account_last_four="8952",
                tsec="TSEC",
            ),
            aso,
        )
        self.assertEqual(resultado["challenge"], "CH-1")


class EstadoAutorizacionTests(unittest.TestCase):
    def test_aceptado(self):
        aso = _AsoFalso(estado_orden="accepted")
        r = _ejecutar(lambda: R.subida_nivel_estado(challenge="CH-1", intentos=4, espera=0.01), aso)
        self.assertTrue(r["aceptado"])
        self.assertEqual(r["sondeos"], 1)

    def test_approved_tambien_es_aceptado(self):
        aso = _AsoFalso(estado_orden="approved")
        resultado = _ejecutar(
            lambda: R.subida_nivel_estado(
                challenge="CH-1", intentos=1, espera=0.01
            ),
            aso,
        )
        self.assertTrue(resultado["aceptado"])

    def test_pendiente_consulta_una_sola_vez(self):
        """Sin sondeo interno: una consulta por peticion, aunque pidan mas."""

        aso = _AsoFalso(estado_orden="pending")
        r = _ejecutar(lambda: R.subida_nivel_estado(challenge="CH-1", intentos=3, espera=0.01), aso)
        self.assertFalse(r["aceptado"])
        self.assertTrue(r["pendiente"])
        self.assertEqual(r["sondeos"], 1)
        self.assertEqual(aso.llamadas.count("GET order-chanel"), 1)

    def test_el_sondeo_esta_acotado(self):
        """No puede exceder el presupuesto de 10 s del agente."""

        import inspect

        firma = inspect.signature(R.subida_nivel_estado)
        # Los defaults son objetos Query() de FastAPI: el valor va en .default.
        intentos = firma.parameters["intentos"].default
        espera = firma.parameters["espera"].default
        maximo = intentos.default * espera.default
        self.assertLessEqual(
            maximo, 8.0,
            f"el sondeo puede tardar {maximo}s y el agente abandona a los 10s",
        )


class TemporalNoCancelaTests(unittest.TestCase):
    """El bloqueo temporal NUNCA debe ejecutar el POST que cancela la tarjeta."""

    def test_temporal_nunca_llama_a_operations(self):
        aso = _AsoFalso()
        r = _ejecutar(
            lambda: R.bloqueo(
                card_id="C1", tipo="temporal", challenge="", authentication_state="",
                device_id="", profile_id="",
            ),
            aso,
        )
        self.assertTrue(r["ok"])
        self.assertEqual(r["via"], "patch_on_off")
        self.assertEqual(aso.llamadas, ["PATCH activations"])
        self.assertEqual(
            aso.llamadas.count("POST operations"), 0,
            "el bloqueo temporal ejecuto el POST que CANCELA la tarjeta",
        )

    def test_temporal_ignora_la_autorizacion_si_llega(self):
        """Aunque le pasen el reto, el temporal sigue siendo un PATCH."""

        aso = _AsoFalso()
        r = _ejecutar(
            lambda: R.bloqueo(
                card_id="C1", tipo="temporal", challenge="CH-1",
                authentication_state="ST-1", device_id="DEV", profile_id="CC1",
            ),
            aso,
        )
        self.assertEqual(r["via"], "patch_on_off")
        self.assertEqual(aso.llamadas.count("POST operations"), 0)


class PermanenteExigeAutorizacionTests(unittest.TestCase):
    def test_con_autorizacion_ejecuta(self):
        aso = _AsoFalso(status_final=200)
        r = _ejecutar(
            lambda: R.bloqueo(
                card_id="C1", tipo="permanente", challenge="CH-1",
                authentication_state="ST-1", device_id="DEV", profile_id="CC1",
                account_last_four="8952",
            ),
            aso,
        )
        self.assertTrue(r["ok"])
        self.assertEqual(r["via"], "challenge_confirmar")
        self.assertEqual(aso.llamadas, ["POST operations"])

    def test_sin_autorizacion_no_toca_el_aso(self):
        for faltante, kwargs in (
            ("challenge", dict(challenge="", authentication_state="ST-1",
                               device_id="DEV", profile_id="CC1")),
            ("state", dict(challenge="CH-1", authentication_state="",
                           device_id="DEV", profile_id="CC1")),
            ("device", dict(challenge="CH-1", authentication_state="ST-1",
                            device_id="", profile_id="CC1")),
            ("profile", dict(challenge="CH-1", authentication_state="ST-1",
                             device_id="DEV", profile_id="")),
        ):
            with self.subTest(falta=faltante):
                aso = _AsoFalso()
                r = _ejecutar(
                    lambda: R.bloqueo(card_id="C1", tipo="permanente",
                                      **kwargs),
                    aso,
                )
                self.assertFalse(r["ok"])
                self.assertIn("falta la autorizacion", r["detalle"])
                self.assertEqual(len(aso.llamadas), 0)

    def test_cliente_rechaza_devuelve_400(self):
        aso = _AsoFalso(status_final=400)
        r = _ejecutar(
            lambda: R.bloqueo(
                card_id="C1", tipo="permanente", challenge="CH-1",
                authentication_state="ST-1", device_id="DEV", profile_id="CC1",
                account_last_four="8952",
            ),
            aso,
        )
        self.assertFalse(r["ok"])
        self.assertTrue(r["rechazado_por_cliente"])

    def test_authentication_data_del_paso_final(self):
        """Paso 5: el estado viaja en header y los datos empiezan con deviceId."""

        aso = _AsoFalso()
        _ejecutar(
            lambda: R.bloqueo(
                card_id="C1", tipo="permanente", challenge="CH-1",
                authentication_state="ST-1", device_id="DEV", profile_id="CC1",
                account_last_four="8952",
            ),
            aso,
        )
        datos = aso.cabeceras_recibidas[0]["authenticationdata"]
        self.assertTrue(datos.startswith("deviceId=DEV,"))
        self.assertIn("product=cuenta-8952", datos)
        self.assertNotIn("authenticationstate=", datos)
        self.assertNotIn("operationId=", datos)
        self.assertNotIn("correlationToken=", datos)
        self.assertEqual(aso.cabeceras_recibidas[0]["authenticationstate"], "ST-1")


class TipoInvalidoTests(unittest.TestCase):
    def test_tipo_desconocido_no_hace_nada(self):
        aso = _AsoFalso()
        r = _ejecutar(lambda: R.bloqueo(card_id="C1", tipo="otro"), aso)
        self.assertFalse(r["ok"])
        self.assertEqual(len(aso.llamadas), 0)


class TxnrIdentityEndpointTests(unittest.TestCase):
    def test_identity_by_card_expone_solo_la_identidad_necesaria(self):
        with mock.patch.object(
            R._analysis_service,
            "get_trx_identity_by_card",
            return_value={"account_id": "ACC-2156", "personal_id": "1010223694"},
        ) as lookup:
            result = asyncio.run(
                R.identity_by_card(
                    customer_id="1010223694", last_four="4979", origin_flag="TDC"
                )
            )

        lookup.assert_called_once_with(
            customer_id="1010223694", last_four="4979", origin_flag="TDC"
        )
        self.assertEqual(result["account_id"], "ACC-2156")
        self.assertEqual(result["personal_id"], "1010223694")
        self.assertTrue(result["found"])

    def test_customer_address_se_resuelve_fuera_del_event_loop(self):
        with mock.patch.object(
            R._analysis_service,
            "resolve_customer_address_from_postgres",
            return_value="Calle 151 b 58-99",
        ) as lookup:
            result = asyncio.run(R.customer_address(customer_id="1010223694"))

        lookup.assert_called_once_with("1010223694")
        self.assertEqual(result["customer_address"], "Calle 151 b 58-99")
        self.assertTrue(result["found"])


class UnaSolaConsultaTests(unittest.TestCase):
    """Regresion 14/09: /subida-nivel NO consulta Postgres.

    La unica consulta es la de /identity-by-card (el agente, por customer_id).
    La segunda, dentro de /subida-nivel, pasaba la cedula como customer_id y
    moria en etapa "account_id" con clientes reales. Caso de dev: ada_info_detail
    customer_id=98782372, personal_id=000001001198091, last_four_pan_id=2274,
    account_id terminado en 0677.
    """

    def _subida(self, **kwargs):
        aso = _AsoFalso()
        identidad = mock.Mock(return_value={"account_id": "X", "personal_id": "X"})
        parches = _con_aso(aso)
        for p in parches:
            p.start()
        try:
            with mock.patch.object(
                R._analysis_service, "get_trx_identity_by_card", identidad
            ):
                r = asyncio.run(
                    R.subida_nivel(
                        card_id="4916555198782274",
                        personal_id="000001001198091",
                        **kwargs,
                    )
                )
        finally:
            for p in parches:
                p.stop()
        return r, aso, identidad

    def test_usa_el_account_last_four_del_agente_sin_consultar_postgres(self):
        r, aso, identidad = self._subida(account_last_four="0677")
        self.assertEqual(r["status"], "ok")
        identidad.assert_not_called()
        self.assertEqual(r["profile_id"], "CC000001001198091")
        self.assertIn("product=cuenta-0677", aso.cabeceras_recibidas[1]["authenticationdata"])
        self.assertEqual(
            aso.llamadas, ["GET user-status", "POST operations", "POST operations"]
        )

    def test_sin_account_last_four_corta_sin_llamar_al_aso(self):
        r, aso, identidad = self._subida()
        self.assertEqual(r["status"], "error")
        self.assertEqual(r["etapa"], "account_id")
        identidad.assert_not_called()
        self.assertEqual(aso.llamadas, [])

    def test_account_last_four_invalido_corta_sin_llamar_al_aso(self):
        for invalido in ("23a", "123", "12345", "    "):
            with self.subTest(account_last_four=invalido):
                r, aso, identidad = self._subida(account_last_four=invalido)
                self.assertEqual(r["etapa"], "account_id")
                identidad.assert_not_called()
                self.assertEqual(aso.llamadas, [])


class SubidaNivelNoBloqueaEventLoopTests(unittest.TestCase):
    def test_llamadas_al_aso_fuera_del_hilo_del_event_loop(self):
        import threading

        aso = _AsoFalso()
        hilos_aso: list[int] = []
        get_original, post_original = aso.get, aso.post

        def get(url, params=None, headers=None):
            hilos_aso.append(threading.get_ident())
            return get_original(url, params=params, headers=headers)

        def post(url, headers=None, json=None):
            hilos_aso.append(threading.get_ident())
            return post_original(url, headers=headers, json=json)

        aso.get, aso.post = get, post
        hilo_loop: list[int] = []

        async def correr():
            hilo_loop.append(threading.get_ident())
            return await R.subida_nivel(card_id="C1", personal_id="123", account_last_four="8952")

        r = _ejecutar(correr, aso)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(len(hilos_aso), 3)
        self.assertNotIn(hilo_loop[0], hilos_aso)


class EstadoErrorTecnicoTests(unittest.TestCase):
    """Un fallo tecnico no puede quedar como "pendiente" hasta vencer el plazo."""

    def test_error_del_aso_no_es_pendiente(self):
        aso = _AsoFalso(estado_http=500)
        r = _ejecutar(lambda: R.subida_nivel_estado(challenge="CH-1", intentos=1, espera=0.2), aso)
        self.assertEqual(r["status"], "error")
        self.assertEqual(r["estado"], "error")
        self.assertFalse(r["aceptado"])
        self.assertFalse(r["pendiente"])

    def test_sin_contenido_sigue_pendiente(self):
        aso = _AsoFalso(estado_http=204)
        r = _ejecutar(lambda: R.subida_nivel_estado(challenge="CH-1", intentos=1, espera=0.2), aso)
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["pendiente"])
        self.assertFalse(r["aceptado"])

    def test_sin_tsec_no_consulta_el_aso(self):
        aso = _AsoFalso()
        parches = _con_aso(aso)
        for p in parches:
            p.start()
        try:
            with mock.patch.object(ac.TrxAsoClient, "get_tsec", lambda self: ""):
                r = R.subida_nivel_estado(challenge="CH-1", intentos=1, espera=0.2)
        finally:
            for p in parches:
                p.stop()
        self.assertEqual(r["status"], "error")
        self.assertEqual(r["estado"], "error")
        self.assertFalse(r["pendiente"])
        self.assertEqual(aso.llamadas, [])


class CeremoniaUrlCompletaTests(unittest.TestCase):
    """Cada etapa que llama al ASO deja en la traza su URL completa."""

    def test_cada_etapa_trae_metodo_y_url_completa(self):
        from infrastructure.observability import ceremonia_subida_nivel as cer

        aso = _AsoFalso()
        eventos: list[dict] = []
        parches = _con_aso(aso)
        for p in parches:
            p.start()
        try:
            cliente = ac.TrxAsoClient()
            base_reto = cliente._challenge_base()
            base_consultas = cliente._base()
            with mock.patch.object(
                cer, "schedule_trace_event", lambda **k: eventos.append(k)
            ):
                r = asyncio.run(
                    R.subida_nivel(
                        card_id="4916555198782274",
                        personal_id="000001001198091",
                        account_last_four="0677",
                    )
                )
        finally:
            for p in parches:
                p.stop()

        self.assertEqual(r["status"], "ok")
        por_etapa = {e["operation"]: e for e in eventos}
        self.assertEqual(
            [e["operation"] for e in eventos],
            [
                "subida_nivel.tsec",
                "subida_nivel.user_status",
                "subida_nivel.challenge_iniciar",
                "subida_nivel.challenge_enviar_push",
                "subida_nivel.ceremonia",
            ],
        )

        tsec = por_etapa["subida_nivel.tsec"]["request_summary"]
        self.assertEqual(tsec["method"], "POST")
        self.assertEqual(
            tsec["url_completa"], f"{base_consultas}/TechArchitecture/co/grantingTicket/V02"
        )

        # Mismo formato que financial_overview: target = url sin query y
        # request_summary con method, url, url_completa y params.
        user_status = por_etapa["subida_nivel.user_status"]
        peticion = user_status["request_summary"]
        self.assertEqual(peticion["method"], "GET")
        self.assertEqual(peticion["url"], f"{base_reto}/security/v0/user-status")
        self.assertEqual(
            peticion["url_completa"],
            f"{base_reto}/security/v0/user-status?profileId=CC000001001198091",
        )
        self.assertEqual(peticion["params"], {"profileId": "CC000001001198091"})
        self.assertEqual(user_status["target"], peticion["url"])

        for nombre in ("subida_nivel.challenge_iniciar", "subida_nivel.challenge_enviar_push"):
            with self.subTest(etapa=nombre):
                self.assertEqual(
                    por_etapa[nombre]["request_summary"]["url_completa"],
                    f"{base_reto}/cards/v2/operations",
                )
        self.assertEqual(por_etapa["subida_nivel.challenge_iniciar"]["response_summary"]["status_code"], 403)
        self.assertEqual(por_etapa["subida_nivel.challenge_enviar_push"]["response_summary"]["status_code"], 401)

        resumen = por_etapa["subida_nivel.ceremonia"]["response_summary"]
        self.assertEqual(
            resumen["secuencia"],
            ["tsec", "user_status", "challenge_iniciar", "challenge_enviar_push"],
        )
        self.assertTrue(all(etapa.get("url_completa") for etapa in resumen["etapas"]))


class TrazasFormatoFinancialOverviewTests(unittest.TestCase):
    """Estado y bloqueos trazan su llamada al ASO igual que financial_overview.

    Un evento por llamada (TrxAsoClient._emit) con: event_type "aso", target =
    URL, status_code, elapsed_ms y request_summary con params, method, url,
    url_completa, headers, huella del tsec (tsec_enviado, tsec_longitud,
    tsec_prefijo, tsec_sufijo, tsec_sha256, tsec_termina_en_padding) y
    aso_chain_id. Nunca el valor del tsec.
    """

    _CLAVES_PETICION = {
        "params", "method", "url", "url_completa", "headers", "tsec_enviado",
        "tsec_longitud", "tsec_prefijo", "tsec_sufijo", "tsec_sha256",
        "tsec_termina_en_padding", "aso_chain_id",
    }

    def _eventos(self, aso, llamada):
        eventos: list[dict] = []
        parches = _con_aso(aso)
        for p in parches:
            p.start()
        try:
            base_reto = ac.TrxAsoClient()._challenge_base()
            base = ac.TrxAsoClient()._base()
            with mock.patch.object(
                ac, "schedule_trace_event", lambda **k: eventos.append(k)
            ):
                r = llamada()
                if asyncio.iscoroutine(r):
                    r = asyncio.run(r)
        finally:
            for p in parches:
                p.stop()
        return r, eventos, base_reto, base

    def _como_financial_overview(self, evento, operation, method, url):
        self.assertEqual(evento["event_type"], "aso")
        self.assertEqual(evento["operation"], operation)
        self.assertEqual(evento["target"], url)
        self.assertIsNotNone(evento["elapsed_ms"])
        peticion = evento["request_summary"]
        self.assertTrue(self._CLAVES_PETICION.issubset(peticion), peticion.keys())
        self.assertEqual(peticion["method"], method)
        self.assertEqual(peticion["url"], url)
        self.assertEqual(peticion["url_completa"], url)
        self.assertTrue(peticion["tsec_enviado"])
        self.assertNotIn("tsec", peticion["headers"])
        self.assertIn("status_code", evento["response_summary"])

    def test_estado_un_evento_como_financial_overview(self):
        r, eventos, base_reto, _ = self._eventos(
            _AsoFalso(estado_orden="pending"),
            lambda: R.subida_nivel_estado(challenge="sim-2274-challenge", intentos=1, espera=0.2),
        )
        self.assertTrue(r["pendiente"])
        self.assertEqual(len(eventos), 1)
        self._como_financial_overview(
            eventos[0], "order_channel_status", "GET",
            f"{base_reto}/security/v0/order-chanel/sim-2274-challenge",
        )
        self.assertEqual(eventos[0]["outcome"], "ok")
        self.assertEqual(eventos[0]["status_code"], 200)

    def test_estado_error_del_aso(self):
        _, eventos, _, _ = self._eventos(
            _AsoFalso(estado_http=500),
            lambda: R.subida_nivel_estado(challenge="CH-1", intentos=1, espera=0.2),
        )
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["outcome"], "error")
        self.assertEqual(eventos[0]["status_code"], 500)
        self.assertEqual(eventos[0]["error_type"], "HTTPStatusError")

    def test_bloqueo_definitivo_un_evento_como_financial_overview(self):
        _, eventos, base_reto, _ = self._eventos(
            _AsoFalso(status_final=201),
            lambda: R.bloqueo(
                card_id="4916555198782274", tipo="permanente", challenge="sim-2274-challenge",
                authentication_state="sim-state-2274", device_id="DEV",
                profile_id="CC000001001198091", account_last_four="0677",
            ),
        )
        self.assertEqual(len(eventos), 1)
        self._como_financial_overview(
            eventos[0], "challenge_confirmar", "POST", f"{base_reto}/cards/v2/operations"
        )
        self.assertEqual(eventos[0]["outcome"], "ok")
        self.assertEqual(eventos[0]["status_code"], 201)
        self.assertEqual(
            eventos[0]["request_summary"]["headers"]["authenticationstate"], "sim-state-2274"
        )

    def test_bloqueo_temporal_un_evento_como_financial_overview(self):
        _, eventos, _, base = self._eventos(
            _AsoFalso(),
            lambda: R.bloqueo(card_id="4916555198782274", tipo="temporal"),
        )
        self.assertEqual(len(eventos), 1)
        self._como_financial_overview(
            eventos[0], "block_temporary", "PATCH",
            f"{base}/cards/v1/cards/4916555198782274/activations",
        )
        self.assertEqual(eventos[0]["outcome"], "ok")
        self.assertEqual(eventos[0]["status_code"], 200)


class ErrorExplicitoYHuellaTsecTests(unittest.TestCase):
    """400 del bloqueo definitivo con error_type y ceremonia con huella del TSEC."""

    def _eventos_aso(self, aso, llamada):
        eventos: list[dict] = []
        parches = _con_aso(aso)
        for p in parches:
            p.start()
        try:
            with mock.patch.object(
                ac, "schedule_trace_event", lambda **k: eventos.append(k)
            ):
                r = llamada()
                if asyncio.iscoroutine(r):
                    r = asyncio.run(r)
        finally:
            for p in parches:
                p.stop()
        return r, eventos

    def test_bloqueo_definitivo_400_trae_error_type_y_mensaje(self):
        r, eventos = self._eventos_aso(
            _AsoFalso(status_final=400),
            lambda: R.bloqueo(
                card_id="C1", tipo="permanente", challenge="CH-1",
                authentication_state="ST-1", device_id="DEV", profile_id="CC1",
            ),
        )
        self.assertTrue(r["rechazado_por_cliente"])
        evento = eventos[0]
        self.assertEqual(evento["operation"], "challenge_confirmar")
        self.assertEqual(evento["outcome"], "http_400")
        self.assertEqual(evento["status_code"], 400)
        self.assertEqual(evento["error_type"], "HTTPStatusError")
        self.assertEqual(
            evento["error_message"], "ASO respondio 400: el cliente no autorizo la operacion"
        )

    def test_403_y_401_esperados_del_reto_no_se_marcan_como_error(self):
        _, eventos = self._eventos_aso(
            _AsoFalso(),
            lambda: R.subida_nivel(
                card_id="C1", personal_id="123", account_last_four="8952"
            ),
        )
        reto = {e["operation"]: e for e in eventos if e["operation"].startswith("challenge_")}
        self.assertEqual(reto["challenge_iniciar"]["outcome"], "http_403")
        self.assertEqual(reto["challenge_enviar_push"]["outcome"], "http_401")
        for evento in reto.values():
            self.assertIsNone(evento.get("error_type"))
            self.assertIsNone(evento.get("error_message"))

    def test_ceremonia_trae_huella_del_tsec_y_aso_chain_id(self):
        import json

        from infrastructure.observability import ceremonia_subida_nivel as cer

        aso = _AsoFalso()
        eventos: list[dict] = []
        parches = _con_aso(aso)
        for p in parches:
            p.start()
        try:
            with mock.patch.object(
                cer, "schedule_trace_event", lambda **k: eventos.append(k)
            ):
                asyncio.run(
                    R.subida_nivel(card_id="C1", personal_id="123", account_last_four="8952")
                )
        finally:
            for p in parches:
                p.stop()

        etapas = [e for e in eventos if e["operation"] != "subida_nivel.ceremonia"]
        self.assertEqual(
            [e["operation"] for e in etapas],
            [
                "subida_nivel.tsec",
                "subida_nivel.user_status",
                "subida_nivel.challenge_iniciar",
                "subida_nivel.challenge_enviar_push",
            ],
        )
        huellas = {e["request_summary"]["tsec_sha256"] for e in etapas}
        cadenas = {e["request_summary"]["aso_chain_id"] for e in etapas}
        self.assertEqual(len(huellas), 1, "todas las etapas usan el mismo TSEC")
        self.assertEqual(len(cadenas), 1)
        for evento in etapas:
            self.assertTrue(evento["request_summary"]["tsec_enviado"])
            self.assertEqual(evento["request_summary"]["tsec_longitud"], 4)
        # Nunca el valor del TSEC ("TSEC" en la prueba) fuera de su huella.
        resumen = next(e for e in eventos if e["operation"] == "subida_nivel.ceremonia")
        self.assertTrue(
            all(etapa.get("tsec_sha256") for etapa in resumen["response_summary"]["etapas"])
        )
        self.assertNotIn('"tsec": "TSEC"', json.dumps(eventos))


if __name__ == "__main__":
    unittest.main()
