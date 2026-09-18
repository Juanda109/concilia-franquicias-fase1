"""Tests for matching a choice option by the label the customer actually sees.

Los pasos de productos y movimientos reescriben sus etiquetas en tiempo de
ejecucion (`dynamic_option_labels_<step>`). Antes se comparaba solo contra las
del YAML ("Producto 1"), que ya nadie ve, asi que devolver la etiqueta mostrada
no avanzaba el paso: el bot repetia la pregunta indefinidamente.
"""

import json
import unittest

from domain.conversation.models import Conversation, ConversationStatus
from domain.workflow.models import WorkflowStepOption
from domain.workflow.workflow_engine import WorkflowEngine

PASO = "2.4.0.2"
ETIQUETAS = [
    "Tarjeta de Crédito *4979",
    "Tarjeta de Crédito *1234",
    "Cuenta de Ahorros *6677",
]


def _conversacion_trx() -> Conversation:
    return Conversation(
        conversation_id="1013634958_20260812",
        status=ConversationStatus.ACTIVE,
        current_step=PASO,
        general_workflow="Transaccion no reconocida",
        workflow="trx_no_reconocida",
        flow_version=1,
        user_id="1013634958",
    )


class DynamicOptionLabelMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = WorkflowEngine()
        cls.opciones = [
            WorkflowStepOption(key=str(i), label=f"Producto {i}", next_step=PASO)
            for i in range(1, 6)
        ]

    def _conversacion(self, etiquetas: object) -> Conversation:
        conversacion = _conversacion_trx()
        if etiquetas is not None:
            conversacion.captured_data[f"dynamic_option_labels_{PASO}"] = etiquetas
        return conversacion

    def _casar(self, entrada: str, etiquetas: list[str] | None = ETIQUETAS):
        conversacion = self._conversacion(
            json.dumps(etiquetas) if etiquetas is not None else None
        )
        opcion, _key = self.engine._match_step_option(
            self.opciones,
            self.engine._normalize_text(entrada),
            self.engine._dynamic_option_labels(conversacion, PASO),
        )
        return opcion

    def test_casa_por_la_etiqueta_visible(self) -> None:
        self.assertEqual(self._casar("Cuenta de Ahorros *6677").key, "3")

    def test_ignora_acentos_y_mayusculas(self) -> None:
        self.assertEqual(self._casar("tarjeta de credito *1234").key, "2")

    def test_la_key_sigue_funcionando(self) -> None:
        """La UI manda la key; no puede dejar de valer."""

        self.assertEqual(self._casar("1").key, "1")

    def test_la_etiqueta_del_yaml_sigue_funcionando(self) -> None:
        self.assertEqual(self._casar("Producto 2").key, "2")

    def test_una_etiqueta_ajena_no_casa(self) -> None:
        self.assertIsNone(self._casar("Tarjeta de Crédito *0000"))

    def test_sin_etiquetas_dinamicas_se_comporta_como_antes(self) -> None:
        self.assertIsNone(self._casar("Cuenta de Ahorros *6677", etiquetas=None))
        self.assertEqual(self._casar("Producto 1", etiquetas=None).key, "1")


class DynamicOptionLabelReadingTests(unittest.TestCase):
    """El lector no puede romper el turno por un dato mal guardado."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = WorkflowEngine()

    def _leer(self, crudo: object):
        conversacion = _conversacion_trx()
        if crudo is not None:
            conversacion.captured_data[f"dynamic_option_labels_{PASO}"] = crudo
        return self.engine._dynamic_option_labels(conversacion, PASO)

    def test_sin_dato(self) -> None:
        self.assertIsNone(self._leer(None))

    def test_json_ilegible(self) -> None:
        self.assertIsNone(self._leer("{no es json"))

    def test_json_que_no_es_lista(self) -> None:
        self.assertIsNone(self._leer(json.dumps({"a": 1})))

    def test_lista_valida(self) -> None:
        self.assertEqual(self._leer(json.dumps(ETIQUETAS)), ETIQUETAS)


if __name__ == "__main__":
    unittest.main()

class DynamicOptionKeysRoutingTests(unittest.TestCase):
    """Paginacion (03/09): el destino lo manda la key DINAMICA cuando coincide
    con una key del YAML. En la ultima pagina, "no_encuentro" cae en la
    posicion de una casilla de movimiento: sin esto, ruteaba al detalle."""

    def setUp(self) -> None:
        self.engine = WorkflowEngine()
        self.opciones = [
            WorkflowStepOption(key="movimiento_1", label="Movimiento 1", next_step="detalle"),
            WorkflowStepOption(key="movimiento_2", label="Movimiento 2", next_step="detalle"),
            WorkflowStepOption(key="movimiento_3", label="Movimiento 3", next_step="detalle"),
            WorkflowStepOption(key="mas_movimientos", label="Ver más", next_step="selector"),
            WorkflowStepOption(key="no_encuentro", label="No encuentro", next_step="salida"),
        ]

    def test_no_encuentro_desplazado_rutea_a_su_destino(self) -> None:
        # ultima pagina con 2 movimientos: no_encuentro queda en la posicion 3
        keys_dinamicas = ["movimiento_6", "movimiento_7", "no_encuentro"]
        opcion, key = self.engine._match_step_option(
            self.opciones,
            self.engine._normalize_text("no_encuentro"),
            None,
            keys_dinamicas,
        )
        self.assertEqual(opcion.next_step, "salida")   # no "detalle"
        self.assertEqual(key, "no_encuentro")

    def test_movimiento_absoluto_conserva_su_key(self) -> None:
        keys_dinamicas = ["movimiento_6", "movimiento_7", "no_encuentro"]
        opcion, key = self.engine._match_step_option(
            self.opciones,
            self.engine._normalize_text("movimiento_7"),
            None,
            keys_dinamicas,
        )
        self.assertEqual(opcion.next_step, "detalle")
        self.assertEqual(key, "movimiento_7")          # la ABSOLUTA se guarda

    def test_por_numero_tambien_lleva_la_key_absoluta(self) -> None:
        keys_dinamicas = ["movimiento_6", "movimiento_7", "no_encuentro"]
        opcion, key = self.engine._match_step_option(
            self.opciones, "2", None, keys_dinamicas,
        )
        self.assertEqual(key, "movimiento_7")

