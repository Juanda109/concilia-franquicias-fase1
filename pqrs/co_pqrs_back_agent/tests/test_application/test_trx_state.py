import unittest
from types import SimpleNamespace

from application.chat.trx_state import (
    TRX_STATE_KEY,
    get_trx_state,
    reset_per_tx,
    trx_snapshot,
    update_trx_state,
)


def _conv() -> SimpleNamespace:
    return SimpleNamespace(captured_data={})


class TrxStateTests(unittest.TestCase):
    def test_get_crea_estado_vacio(self) -> None:
        conv = _conv()
        state = get_trx_state(conv)
        self.assertEqual(state, {})
        self.assertIn(TRX_STATE_KEY, conv.captured_data)

    def test_update_merge(self) -> None:
        conv = _conv()
        update_trx_state(conv, cantidad=2, tx_index=1)
        update_trx_state(conv, card_id="4912...4979")
        state = get_trx_state(conv)
        self.assertEqual(state["cantidad"], 2)
        self.assertEqual(state["tx_index"], 1)
        self.assertEqual(state["card_id"], "4912...4979")

    def test_reset_per_tx_conserva_globales(self) -> None:
        conv = _conv()
        update_trx_state(
            conv,
            cantidad=3,
            tx_index=1,
            producto={"contract_id": "x"},
            fecha="06/08/2026",
            card_id="4912",
            movimiento={"id": "TX1"},
        )
        reset_per_tx(conv)
        state = get_trx_state(conv)
        # globales se conservan
        self.assertEqual(state["cantidad"], 3)
        self.assertEqual(state["tx_index"], 1)
        # por-transacción se limpian
        self.assertNotIn("producto", state)
        self.assertNotIn("fecha", state)
        self.assertNotIn("card_id", state)
        self.assertNotIn("movimiento", state)

    def test_snapshot_es_copia(self) -> None:
        conv = _conv()
        update_trx_state(conv, cantidad=1)
        snap = trx_snapshot(conv)
        snap["cantidad"] = 999
        self.assertEqual(get_trx_state(conv)["cantidad"], 1)


if __name__ == "__main__":
    unittest.main()
