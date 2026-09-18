"""Pruebas de la traza de la ceremonia de subida de nivel.

Lo que se protege aquí es la capacidad de DIAGNOSTICAR. Una ceremonia de ocho pasos
que falla sin dejar dicho en cuál se rompió obliga a reconstruirla cruzando eventos
por marca temporal, y eso son horas cada vez.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from infrastructure.observability.ceremonia_subida_nivel import (
    CeremoniaDeSubidaDeNivel,
    entorno_del_aso,
)


class EntornoDelAsoTests(unittest.TestCase):
    """A qué ASO se llama de verdad, que no es obvio."""

    def test_por_defecto_las_consultas_van_al_simulador(self) -> None:
        """`ASO_SOURCE` no definido significa simulador, no real.

        Es la causa más probable de "no veo consumos en el ASO": el despliegue
        consulta el simulador y nadie lo ha declarado en ningún sitio visible.
        """

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(entorno_del_aso()["consultas_van_al"], "simulador")

    def test_con_source_real_las_consultas_van_al_real(self) -> None:
        with patch.dict(os.environ, {"ASO_SOURCE": "real"}, clear=True):
            self.assertEqual(entorno_del_aso()["consultas_van_al"], "real")

    def test_con_simulador_el_challenge_no_va_al_real(self) -> None:
        """`ASO_CHALLENGE_BASE_URL` solo aplica con `ASO_SOURCE=real`.

        Es el caso de dev: la variable apunta a nextgen, pero TrxAsoClient manda el
        reto al simulador. La traza decía "real" y hacía buscar el push donde nunca
        salió (evento 98782372_20260914).
        """

        with patch.dict(
            os.environ,
            {
                "ASO_SOURCE": "simulator",
                "ASO_SIMULATOR_URL": "http://co-pqrs-back-trx-aso-simulator:8050",
                "ASO_CHALLENGE_BASE_URL": "https://aso-dev-co.work-02.nextgen.igrupobbva",
            },
            clear=True,
        ):
            entorno = entorno_del_aso()
        self.assertEqual(entorno["consultas_van_al"], "simulador")
        self.assertEqual(entorno["challenge_va_al"], "simulador")
        self.assertEqual(
            entorno["challenge_url"], "http://co-pqrs-back-trx-aso-simulator:8050"
        )

    def test_con_source_real_el_challenge_usa_su_propia_base(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ASO_SOURCE": "real",
                "ASO_REAL_URL": "https://aus-arqaso.work.co.nextgen.igrupobbva:8050",
                "ASO_CHALLENGE_BASE_URL": "https://aso-reto.nextgen.igrupobbva",
            },
            clear=True,
        ):
            entorno = entorno_del_aso()
        self.assertEqual(entorno["consultas_van_al"], "real")
        self.assertEqual(entorno["challenge_va_al"], "real")
        self.assertEqual(entorno["challenge_url"], "https://aso-reto.nextgen.igrupobbva")

    def test_base_manual_gana_para_las_consultas(self) -> None:
        """Con `ASO_BASE_URL` y fuente simulador, consultas y reto salen a esa base."""

        with patch.dict(
            os.environ,
            {
                "ASO_SOURCE": "simulator",
                "ASO_BASE_URL": "https://aus-arqaso.work.co.nextgen.igrupobbva:8050",
            },
            clear=True,
        ):
            entorno = entorno_del_aso()
        self.assertEqual(entorno["consultas_van_al"], "real")
        self.assertEqual(entorno["challenge_va_al"], "real")

    def test_el_override_manual_se_registra(self) -> None:
        """`ASO_BASE_URL` gana sobre todo. En el IaC está comentada."""

        with patch.dict(
            os.environ, {"ASO_BASE_URL": "https://manual.example"}, clear=True
        ):
            self.assertEqual(
                entorno_del_aso()["aso_base_url"], "https://manual.example"
            )


class CeremoniaTests(unittest.TestCase):
    def _ceremonia(self) -> CeremoniaDeSubidaDeNivel:
        return CeremoniaDeSubidaDeNivel(
            card_id="4912680517940062", personal_id="1013634962"
        )

    def test_conserva_el_orden_de_las_etapas(self) -> None:
        """Sin orden no hay ceremonia, solo un montón de eventos."""

        c = self._ceremonia()
        for nombre in ("tsec", "user_status", "account_id", "challenge_iniciar"):
            c.etapa(nombre, "ok")
        self.assertEqual([e["orden"] for e in c.etapas], [1, 2, 3, 4])
        self.assertEqual(
            [e["etapa"] for e in c.etapas],
            ["tsec", "user_status", "account_id", "challenge_iniciar"],
        )

    def test_dice_en_que_etapa_murio(self) -> None:
        """Es el dato que se busca primero cuando algo falla."""

        c = self._ceremonia()
        c.etapa("tsec", "ok")
        c.etapa("user_status", "ok")
        c.etapa("account_id", "error", detalle="sin fila en Postgres")

        capturado: dict = {}

        def _capturar(**kwargs):
            capturado.update(kwargs)

        with patch(
            "infrastructure.observability.ceremonia_subida_nivel.schedule_trace_event",
            _capturar,
        ):
            c.cerrar("error", "fallo en account_id")

        self.assertEqual(capturado["response_summary"]["murio_en"], "account_id")
        self.assertEqual(
            capturado["response_summary"]["secuencia"],
            ["tsec", "user_status", "account_id"],
        )

    def test_no_expone_el_documento_ni_la_tarjeta_completa(self) -> None:
        """Una traza que hay que censurar después ya nació mal.

        Se envían los últimos cuatro de la tarjeta y un booleano del documento; el
        número completo y la cédula no salen nunca.
        """

        c = self._ceremonia()
        capturado: dict = {}

        with patch(
            "infrastructure.observability.ceremonia_subida_nivel.schedule_trace_event",
            lambda **k: capturado.update(k),
        ):
            c.etapa("tsec", "ok")

        serializado = repr(capturado)
        self.assertNotIn("4912680517940062", serializado)
        self.assertNotIn("1013634962", serializado)
        self.assertIn("0062", serializado)

    def test_una_traza_que_falla_no_rompe_la_ceremonia(self) -> None:
        """La observabilidad no puede tumbar una subida de nivel."""

        c = self._ceremonia()

        def _explota(**_kwargs):
            raise RuntimeError("el error-handler no responde")

        with patch(
            "infrastructure.observability.ceremonia_subida_nivel.schedule_trace_event",
            _explota,
        ):
            c.etapa("tsec", "ok")
            c.cerrar("ok")

        # La etapa se registró en memoria aunque el envío fallara.
        self.assertEqual(len(c.etapas), 1)

    def test_el_exito_no_significa_autorizado(self) -> None:
        """`ok` es "push enviado", no "el cliente aprobó".

        Confundirlo es un malentendido caro: se daría por autorizado un bloqueo que
        el cliente todavía no ha aceptado.
        """

        c = self._ceremonia()
        capturado: dict = {}
        with patch(
            "infrastructure.observability.ceremonia_subida_nivel.schedule_trace_event",
            lambda **k: capturado.update(k),
        ):
            c.cerrar("ok", "push enviado; pendiente de que el cliente autorice")
        self.assertIn("pendiente", capturado["response_summary"]["detalle"])

    def test_cada_etapa_emite_su_propio_evento(self) -> None:
        """Las etapas que NO llaman al ASO también dejan rastro.

        Antes, validar el card_id o resolver el account_id no producía nada, y son
        justo donde la ceremonia se cae más a menudo porque dependen de datos del
        cliente.
        """

        c = self._ceremonia()
        eventos: list[dict] = []
        with patch(
            "infrastructure.observability.ceremonia_subida_nivel.schedule_trace_event",
            lambda **k: eventos.append(k),
        ):
            c.etapa("card_id", "error", detalle="card_id es obligatorio")
            c.etapa("account_id", "ok")

        self.assertEqual(len(eventos), 2)
        self.assertEqual(eventos[0]["operation"], "subida_nivel.card_id")
        self.assertEqual(eventos[1]["operation"], "subida_nivel.account_id")
        # El entorno del ASO viaja en TODOS, para poder filtrar por él en MinIO.
        for evento in eventos:
            self.assertIn("aso_source", evento["extra_context"])


if __name__ == "__main__":
    unittest.main()
