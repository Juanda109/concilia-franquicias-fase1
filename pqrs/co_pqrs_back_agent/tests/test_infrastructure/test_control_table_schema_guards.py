"""Guardas del esquema de la control-table y de la traza de sus fallos.

Contexto (03/09/2026). El indice ``client-control-table`` de produccion se quedo
sin sitio en su esquema y OpenSearch empezo a rechazar TODA escritura con

    400 illegal_argument_exception: Limit of total fields [1000] has been exceeded

La causa: la tabla usa FECHAS como nombre de campo
(``daily_categories.<YYYYMMDD>.<categoria>.count``,
``monthly.<YYYY-MM>.workflows.<wf>.back_data_run_id``), asi que con mapping
dinamico cada dia y cada mes anaden rutas NUEVAS al esquema.

Consecuencia visible: el agente no podia crear el bucket del mes en curso, el
sondeo de back-data no encontraba nada y el cliente recibia "En este momento no
puedo validar el estado de tus productos en las centrales de riesgo".

Tardo dos dias en diagnosticarse porque el agente capturaba el fallo con
``logger.exception`` y el rastro quedaba SOLO en el log del contenedor.

Este fichero fija las dos piezas que cierran el caso:

  * ``TemplateProtegeElEsquema``: el index template no puede volver a permitir
    que las ramas indexadas por fecha crezcan.
  * ``FalloDeEscrituraDejaTraza``: cuando una escritura del agente en la
    control-table falla, el motivo llega al bucket de auditoria y el turno NO
    se rompe.

Ejecutar:
    PYTHONPATH=src:tests uv run python -m unittest \
        test_infrastructure.test_control_table_schema_guards -v
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any

import application.chat.chat_service as cs

RAIZ = Path(__file__).resolve().parents[3]
TEMPLATE = RAIZ / "IaC" / "BD" / "opensearch" / "11-configmap-index-templates.yaml"

# Ramas cuyo NOMBRE DE CAMPO es una fecha (o contiene una): si se indexan
# dinamicamente, el esquema crece para siempre.
RAMAS_POR_FECHA = ("daily_categories", "monthly", "daily", "workflows")


def _cargar_template() -> dict[str, Any]:
    """Extrae el JSON del template del ConfigMap sin depender de PyYAML."""

    texto = TEMPLATE.read_text(encoding="utf-8")
    marca = "client-control-table-template.json: |"
    i = texto.index(marca)
    cuerpo = texto[i + len(marca):].split("\n", 1)[1]
    lineas: list[str] = []
    for linea in cuerpo.split("\n"):
        if linea.strip() and not linea.startswith("    "):
            break
        lineas.append(linea[4:] if linea.startswith("    ") else linea)
    return json.loads("\n".join(lineas))


class TemplateProtegeElEsquema(unittest.TestCase):
    """El molde con el que nace un indice nuevo no puede repetir el fallo."""

    @classmethod
    def setUpClass(cls) -> None:
        if not TEMPLATE.exists():  # pragma: no cover - checkout parcial
            raise unittest.SkipTest("el template no esta en este checkout")
        cls.template = _cargar_template()

    def test_las_ramas_por_fecha_no_se_indexan(self) -> None:
        props = self.template["template"]["mappings"]["properties"]
        for rama in RAMAS_POR_FECHA:
            with self.subTest(rama=rama):
                self.assertIn(rama, props, f"'{rama}' debe estar declarada")
                self.assertIs(
                    props[rama].get("dynamic"),
                    False,
                    f"'{rama}' se indexa por fecha: sin dynamic:false el esquema "
                    f"crece cada dia hasta agotar el limite de campos",
                )

    def test_ninguna_rama_por_fecha_queda_con_enabled_true(self) -> None:
        """'enabled: true' sin 'dynamic: false' era el estado que fallo."""

        props = self.template["template"]["mappings"]["properties"]
        for rama in RAMAS_POR_FECHA:
            cfg = props.get(rama, {})
            if cfg.get("enabled") is True and cfg.get("dynamic") is not False:
                self.fail(
                    f"'{rama}' vuelve a estar indexada dinamicamente: es el "
                    f"estado que agoto los 1000 campos en produccion"
                )

    def test_declara_un_techo_de_campos_holgado(self) -> None:
        settings = self.template["template"]["settings"]
        limite = settings.get("index.mapping.total_fields.limit")
        self.assertIsNotNone(
            limite,
            "sin limite declarado se usa el default de 1000, que es el que se agoto",
        )
        self.assertGreaterEqual(int(limite), 2000)

    def test_los_data_blob_siguen_desactivados(self) -> None:
        """La proteccion de los 'data' es anterior y no debe perderse."""

        dts = self.template["template"]["mappings"]["dynamic_templates"]
        nombres = {n for dt in dts for n in dt}
        self.assertIn("monthly_workflow_data_blob", nombres)
        self.assertIn("daily_workflow_data_blob", nombres)

    def test_el_desplegable_de_saneo_existe(self) -> None:
        """El template solo cubre indices nuevos; uno existente se sanea aparte."""

        modulo = (
            RAIZ / "IaC" / "backend"
            / "co_pqrs_back_control_table_maintenance" / "00-cronjob.yaml"
        )
        self.assertTrue(
            modulo.exists(),
            "falta el desplegable que sanea un indice YA existente",
        )
        texto = modulo.read_text(encoding="utf-8")
        self.assertIn("suspend: true", texto, "debe lanzarse a demanda, no por horario")
        self.assertIn("total_fields.limit", texto)
        for rama in RAMAS_POR_FECHA:
            self.assertIn(rama, texto, f"el saneo debe cubrir '{rama}'")


class _ErrorHttpFalso(Exception):
    """Imita un httpx.HTTPStatusError: lleva la respuesta con el motivo real."""

    class _Resp:
        status_code = 400
        text = (
            '{"error":{"root_cause":[{"type":"illegal_argument_exception",'
            '"reason":"Limit of total fields [1000] has been exceeded"}]},'
            '"status":400}'
        )

    def __init__(self) -> None:
        super().__init__("Client error '400 Bad Request' for url '...'")
        self.response = self._Resp()


class FalloDeEscrituraDejaTraza(unittest.TestCase):
    """El motivo del fallo tiene que salir del pod y llegar a la auditoria."""

    def setUp(self) -> None:
        self.eventos: list[dict[str, Any]] = []
        self._orig = cs.schedule_trace_event
        cs.schedule_trace_event = lambda **kw: self.eventos.append(kw)

    def tearDown(self) -> None:
        cs.schedule_trace_event = self._orig

    def test_emite_traza_con_el_cuerpo_del_error(self) -> None:
        cs._trace_control_table_write_failure(
            conversation_id="13083558_20260903",
            client_id="13083558",
            momento="auto_start",
            error=_ErrorHttpFalso(),
            workflow_id="centrales_de_riesgo",
        )
        self.assertEqual(len(self.eventos), 1)
        e = self.eventos[0]
        self.assertEqual(e["operation"], "control_table_write")
        self.assertEqual(e["outcome"], "error")
        self.assertEqual(e["customer_id"], "13083558")
        self.assertEqual(e["status_code"], 400)
        req = e["request_summary"]
        self.assertEqual(req["momento"], "auto_start")
        self.assertEqual(req["workflow_id"], "centrales_de_riesgo")
        self.assertIn(
            "Limit of total fields",
            req["body"],
            "el cuerpo lleva el motivo real; sin el hay que deducirlo",
        )

    def test_funciona_sin_respuesta_http(self) -> None:
        """Un fallo de red no trae respuesta: la traza se emite igual."""

        cs._trace_control_table_write_failure(
            conversation_id="c1",
            client_id="1",
            momento="record_category_interaction",
            error=RuntimeError("connection reset"),
            category="centrales_de_riesgo:reporte_no_reconocido",
        )
        self.assertEqual(len(self.eventos), 1)
        e = self.eventos[0]
        self.assertIsNone(e["status_code"])
        self.assertEqual(e["error_type"], "RuntimeError")
        self.assertEqual(
            e["request_summary"]["category"],
            "centrales_de_riesgo:reporte_no_reconocido",
        )

    def test_nunca_propaga_una_excepcion(self) -> None:
        """Fail-open: la observabilidad no puede tumbar el turno del cliente."""

        def _explota(**_kw: Any) -> None:
            raise RuntimeError("el bucket de trazas no responde")

        cs.schedule_trace_event = _explota
        cs._trace_control_table_write_failure(
            conversation_id="c1",
            client_id="1",
            momento="auto_start",
            error=RuntimeError("x"),
        )  # no debe levantar

    def test_los_cuatro_puntos_de_fallo_estan_cableados(self) -> None:
        """Si aparece un quinto punto que se traga el fallo, esto avisa."""

        fuente = Path(cs.__file__).read_text(encoding="utf-8")
        momentos = set(re.findall(r'momento="([a-z_]+)"', fuente))
        self.assertEqual(
            momentos,
            {
                "workflow_entry",
                "auto_start",
                "fallback_al_cerrar",
                "record_category_interaction",
            },
        )
        # Cada 'Control-table ... failed' debe tener su traza al lado.
        fallos = fuente.count("Control-table write failed")
        fallos += fuente.count("Control-table fallback write also failed")
        fallos += fuente.count("Failed to record category interaction")
        self.assertEqual(
            fuente.count("_trace_control_table_write_failure(") - 1,  # -1: la def
            fallos,
            "hay un fallo de escritura sin traza: volveria a ser invisible",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
