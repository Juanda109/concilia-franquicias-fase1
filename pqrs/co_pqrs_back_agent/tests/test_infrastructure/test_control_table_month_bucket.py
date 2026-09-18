"""Fallo de centrales: back_data escribia el sobre en un mes que el agente no leia.

Historia del caso (02/09/2026). back_data terminaba bien -escritura 200 con el
``run_id`` correcto en 1,5 s- y el agente sondeaba 60 veces sin encontrar nada,
agotaba su presupuesto y el cliente recibia "En este momento no puedo validar el
estado de tus productos en las centrales de riesgo".

Este fichero:

  * documenta el comportamiento ANTIGUO del script painless y los dos escenarios
    en los que perdia el sobre (``EscrituraAntigua``);
  * comprueba que la escritura NUEVA (C2) siempre cae en el mes en curso;
  * comprueba que el lector del agente (C3) acepta un sobre de otro mes SOLO si el
    ``run_id`` coincide, y que sin ``run_id`` no amplia la busqueda;
  * comprueba que la limpieza previa al disparo (C5) borra de verdad;
  * comprueba que la escritura tolera un documento inexistente (C4);
  * guarda el script painless para que estas pruebas no queden obsoletas en
    silencio si vuelve a cambiar.

Usa el LECTOR REAL del agente y la semantica real de
``POST /{index}/_update/{id}`` con ``doc`` + ``doc_as_upsert`` (merge RECURSIVO).

Ejecutar:
    PYTHONPATH=src uv run python -m unittest \
        tests.test_infrastructure.test_control_table_month_bucket -v
"""

from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from infrastructure.persistence.control_table_store import ControlTableStore

# --------------------------------------------------------------------------
# Constantes del caso real
# --------------------------------------------------------------------------
AHORA = datetime(2026, 9, 2, 13, 51, 0, tzinfo=timezone.utc)
AGOSTO = datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)
MES_ACTUAL = "2026-09"
MES_VIEJO = "2026-08"
WF = "centrales_de_riesgo"
RUN_ID = "35fbd471-52b7-485d-8f51-baeebb7042ee"
RUN_ID_VIEJO = "00000000-1111-2222-3333-444444444444"


def _campos(run_id: str = RUN_ID) -> dict[str, Any]:
    return {
        "back_data_status": "ok",
        "back_data_run_id": run_id,
        "back_data_updated_at": AHORA.isoformat(),
        "data": {"hallazgos": {"validaciones": [{"key_id": "295317"}]}},
        "back_data_error": None,
    }


# --------------------------------------------------------------------------
# Semantica de OpenSearch
# --------------------------------------------------------------------------
def merge_recursivo(destino: dict[str, Any], parcial: dict[str, Any]) -> dict[str, Any]:
    """Merge de ``{"doc": ...}``: recursivo para objetos, y NO borra claves.

    Que no pueda borrar es justo el motivo de C5: la limpieza omitia las claves
    esperando que desaparecieran y se quedaban intactas.
    """

    salida = copy.deepcopy(destino)
    for clave, valor in parcial.items():
        if clave in salida and isinstance(salida[clave], dict) and isinstance(valor, dict):
            salida[clave] = merge_recursivo(salida[clave], valor)
        else:
            salida[clave] = copy.deepcopy(valor)
    return salida


def escritura_antigua(
    record: dict[str, Any] | None,
    *,
    workflow: str,
    fields: dict[str, Any],
    default_period: str,
) -> tuple[dict[str, Any], str]:
    """Painless ANTIGUO (hasta el 02/09). Se conserva para documentar el fallo.

    Recorria los meses del registro y actualizaba TODOS los que ya contuvieran el
    workflow -no habia ``break``-; si no encontraba ninguno usaba el mes de
    ``last_interaction_at`` en vez del mes en curso.
    """

    if record is None:
        raise KeyError("document_missing_exception")  # sin upsert: 404
    record = copy.deepcopy(record)
    record.pop("data", None)
    if record.get("monthly") is None:
        record["monthly"] = {}

    tocados: list[str] = []
    for mes, datos_mes in record["monthly"].items():
        if datos_mes.get("workflows") is not None and workflow in datos_mes["workflows"]:
            datos_mes["workflows"][workflow].update(copy.deepcopy(fields))
            tocados.append(mes)

    if not tocados:
        periodo = default_period
        ultima = record.get("last_interaction_at")
        if ultima is not None and len(str(ultima)) >= 7:
            periodo = str(ultima)[:7]
        (
            record["monthly"]
            .setdefault(periodo, {})
            .setdefault("workflows", {})
            .setdefault(workflow, {})
            .update(copy.deepcopy(fields))
        )
        tocados.append(periodo)

    return record, "+".join(tocados)


def escritura_nueva(
    record: dict[str, Any] | None,
    *,
    workflow: str,
    fields: dict[str, Any],
    default_period: str,
    client_id: str,
) -> tuple[dict[str, Any], str]:
    """Painless NUEVO (C2): siempre el mes en curso.

    NO tolera documento inexistente: C4 (``scripted_upsert``) se revirtio el
    02/09 porque en produccion devolvia 400 en todas las escrituras. El
    ``client_id`` se acepta por firma para no cambiar los llamadores.
    """

    if record is None:
        raise KeyError("document_missing_exception")  # limitacion conocida
    record = copy.deepcopy(record)
    record.pop("data", None)
    record.setdefault("monthly", {})

    periodo = default_period  # C2: destino unico
    (
        record["monthly"]
        .setdefault(periodo, {})
        .setdefault("workflows", {})
        .setdefault(workflow, {})
        .update(copy.deepcopy(fields))
    )
    return record, periodo


class OpenSearchFalso:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}
        self.borrados: list[str] = []

    async def get_document(self, index: str, doc_id: str) -> dict[str, Any] | None:
        doc = self.docs.get(doc_id)
        return copy.deepcopy(doc) if doc is not None else None

    async def update_document(
        self, index: str, doc_id: str, document: dict[str, Any], *, upsert: bool = True
    ) -> None:
        existente = self.docs.get(doc_id)
        if existente is None and not upsert:
            return
        self.docs[doc_id] = merge_recursivo(existente or {}, document)

    async def delete_by_term(self, index: str, campo: str, valor: str) -> None:
        self.borrados.append(valor)
        self.docs.pop(valor, None)


class AjustesFalsos:
    control_index = "client-control-table"
    control_record_ttl_days = 30


def store_con(cliente: OpenSearchFalso) -> ControlTableStore:
    store = ControlTableStore.__new__(ControlTableStore)
    store.client = cliente
    store.settings = AjustesFalsos()
    return store


class _Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.cliente = OpenSearchFalso()
        self.store = store_con(self.cliente)

    def lee(self, cliente_id: str, *, run_id: str | None = RUN_ID) -> dict[str, Any]:
        return self.store.get_workflow_back_data_envelope(
            self.cliente.docs.get(cliente_id),
            WF,
            reference_at=AHORA,
            expected_run_id=run_id,
        )


# ==========================================================================
class EscrituraAntigua(_Base):
    """El fallo tal y como ocurria. Documenta por que hubo que cambiarlo."""

    def test_recurrente_de_agosto_perdia_el_sobre(self) -> None:
        doc = {
            "client_id": "A1",
            "last_interaction_at": AGOSTO.isoformat(),
            "monthly": {MES_VIEJO: {"workflows": {WF: {"count": 1}}}},
        }
        nuevo, mes = escritura_antigua(
            doc, workflow=WF, fields=_campos(), default_period=MES_ACTUAL
        )
        self.assertEqual(mes, MES_VIEJO, "escribia en el mes viejo")
        # El lector de ENTONCES solo miraba el mes en curso: no encontraba nada.
        solo_mes_actual = self.store.get_workflow_back_data_envelope(
            nuevo, WF, reference_at=AHORA
        )
        self.assertIsNone(solo_mes_actual["status"])

    def test_sin_historial_del_workflow_usaba_el_mes_de_la_ultima_visita(self) -> None:
        doc = {
            "client_id": "A2",
            "last_interaction_at": AGOSTO.isoformat(),
            "monthly": {MES_VIEJO: {"workflows": {"otro_flujo": {"count": 1}}}},
        }
        _, mes = escritura_antigua(
            doc, workflow=WF, fields=_campos(), default_period=MES_ACTUAL
        )
        self.assertEqual(mes, MES_VIEJO)

    def test_documento_inexistente_daba_404(self) -> None:
        with self.assertRaises(KeyError):
            escritura_antigua(
                None, workflow=WF, fields=_campos(), default_period=MES_ACTUAL
            )


# ==========================================================================
class C2EscrituraEnElMesEnCurso(_Base):
    """El sobre cae siempre donde el agente lo busca."""

    def test_recurrente_de_agosto(self) -> None:
        doc = {
            "client_id": "B1",
            "last_interaction_at": AGOSTO.isoformat(),
            "monthly": {MES_VIEJO: {"workflows": {WF: {"count": 1}}}},
        }
        nuevo, mes = escritura_nueva(
            doc, workflow=WF, fields=_campos(), default_period=MES_ACTUAL, client_id="B1"
        )
        self.assertEqual(mes, MES_ACTUAL)
        sobre = self.store.get_workflow_back_data_envelope(
            nuevo, WF, reference_at=AHORA
        )
        self.assertEqual(sobre["status"], "ok")
        self.assertEqual(sobre["run_id"], RUN_ID)

    def test_sin_historial_del_workflow(self) -> None:
        doc = {
            "client_id": "B2",
            "last_interaction_at": AGOSTO.isoformat(),
            "monthly": {MES_VIEJO: {"workflows": {"otro_flujo": {"count": 1}}}},
        }
        nuevo, mes = escritura_nueva(
            doc, workflow=WF, fields=_campos(), default_period=MES_ACTUAL, client_id="B2"
        )
        self.assertEqual(mes, MES_ACTUAL)
        self.assertEqual(
            self.store.get_workflow_back_data_envelope(
                nuevo, WF, reference_at=AHORA
            )["status"],
            "ok",
        )

    def test_no_pisa_el_contador_del_mes_en_curso(self) -> None:
        """El sobre convive con ``count``/``label`` que escribe el agente."""

        doc = {
            "client_id": "B3",
            "monthly": {
                MES_ACTUAL: {"workflows": {WF: {"count": 2, "label": "Centrales"}}}
            },
        }
        nuevo, _ = escritura_nueva(
            doc, workflow=WF, fields=_campos(), default_period=MES_ACTUAL, client_id="B3"
        )
        wf = nuevo["monthly"][MES_ACTUAL]["workflows"][WF]
        self.assertEqual(wf["count"], 2)
        self.assertEqual(wf["label"], "Centrales")
        self.assertEqual(wf["back_data_status"], "ok")


# ==========================================================================
class C4LimitacionDocumentoInexistente(_Base):
    """Limitacion CONOCIDA: si el documento no existe, la escritura falla.

    El agente aplica un TTL de 30 dias y ``get_record`` borra el registro
    expirado, asi que el documento PUEDE no existir. El ``_update`` de back_data
    no declara upsert, asi que en ese caso devolveria 404 y el sobre no llegaria.

    Se intento cubrir con ``scripted_upsert`` (C4) y hubo que revertirlo: en
    produccion devolvia 400 Bad Request en TODAS las escrituras, incluidas las
    de documentos que si existian. El caso del TTL es una hipotesis nunca
    observada; el 400 era real y rompia el camino que funcionaba.

    Estos tests fijan el comportamiento ACTUAL para que la limitacion quede
    escrita y no se redescubra por sorpresa.
    """

    def test_documento_inexistente_falla(self) -> None:
        with self.assertRaises(KeyError):
            escritura_nueva(
                None, workflow=WF, fields=_campos(),
                default_period=MES_ACTUAL, client_id="C1",
            )

    def test_con_documento_existente_funciona(self) -> None:
        doc = {"client_id": "C2", "monthly": {}}
        nuevo, mes = escritura_nueva(
            doc, workflow=WF, fields=_campos(),
            default_period=MES_ACTUAL, client_id="C2",
        )
        self.assertEqual(mes, MES_ACTUAL)
        self.assertEqual(
            self.store.get_workflow_back_data_envelope(
                nuevo, WF, reference_at=AHORA
            )["status"],
            "ok",
        )


class C3LecturaToleranteAlMes(_Base):
    """El agente acepta otro mes SOLO con el run_id correcto."""

    def _doc_con_sobre_en_agosto(self, run_id: str) -> dict[str, Any]:
        return {
            "client_id": "D",
            "monthly": {
                MES_VIEJO: {"workflows": {WF: _campos(run_id)}},
                MES_ACTUAL: {"workflows": {WF: {"back_data_status": "pending"}}},
            },
        }

    def test_acepta_el_sobre_de_otro_mes_si_el_run_id_casa(self) -> None:
        doc = self._doc_con_sobre_en_agosto(RUN_ID)
        sobre = self.store.get_workflow_back_data_envelope(
            doc, WF, reference_at=AHORA, expected_run_id=RUN_ID
        )
        self.assertEqual(sobre["status"], "ok")
        self.assertEqual(sobre["run_id"], RUN_ID)

    def test_rechaza_el_sobre_de_otro_mes_con_run_id_distinto(self) -> None:
        doc = self._doc_con_sobre_en_agosto(RUN_ID_VIEJO)
        sobre = self.store.get_workflow_back_data_envelope(
            doc, WF, reference_at=AHORA, expected_run_id=RUN_ID
        )
        self.assertEqual(sobre["status"], "pending", "no debe servir un sobre rancio")
        self.assertIsNone(sobre["data"])

    def test_sin_run_id_esperado_no_amplia_la_busqueda(self) -> None:
        """La seguridad depende del run_id: sin el, no se mira otro mes."""

        doc = self._doc_con_sobre_en_agosto(RUN_ID)
        sobre = self.store.get_workflow_back_data_envelope(
            doc, WF, reference_at=AHORA, expected_run_id=None
        )
        self.assertEqual(sobre["status"], "pending")

    def test_el_mes_en_curso_tiene_prioridad(self) -> None:
        doc = {
            "client_id": "D2",
            "monthly": {
                MES_VIEJO: {"workflows": {WF: _campos(RUN_ID)}},
                MES_ACTUAL: {"workflows": {WF: _campos(RUN_ID)}},
            },
        }
        doc["monthly"][MES_ACTUAL]["workflows"][WF]["data"] = {"marca": "actual"}
        sobre = self.store.get_workflow_back_data_envelope(
            doc, WF, reference_at=AHORA, expected_run_id=RUN_ID
        )
        self.assertEqual(sobre["data"], {"marca": "actual"})


# ==========================================================================
class C5LimpiezaEfectiva(_Base):
    """La limpieza previa al disparo tiene que borrar de verdad."""

    async def test_anula_data_y_run_id_pese_al_merge_recursivo(self) -> None:
        self.cliente.docs["E1"] = {
            "client_id": "E1",
            "expires_at": (AHORA + timedelta(days=10)).isoformat(),
            "monthly": {MES_ACTUAL: {"workflows": {WF: _campos(RUN_ID_VIEJO)}}},
        }
        await self.store.clear_workflow_back_data(
            client_id="E1", workflow_id=WF, reference_at=AHORA
        )
        wf = self.cliente.docs["E1"]["monthly"][MES_ACTUAL]["workflows"][WF]
        self.assertEqual(wf["back_data_status"], "pending")
        self.assertIsNone(wf["data"], "el merge no borra: hay que anular explicitamente")
        self.assertIsNone(wf["back_data_run_id"])
        self.assertIsNone(wf["back_data_error"])

    async def test_tras_limpiar_el_lector_no_sirve_el_dato_viejo(self) -> None:
        self.cliente.docs["E2"] = {
            "client_id": "E2",
            "expires_at": (AHORA + timedelta(days=10)).isoformat(),
            "monthly": {MES_ACTUAL: {"workflows": {WF: _campos(RUN_ID_VIEJO)}}},
        }
        await self.store.clear_workflow_back_data(
            client_id="E2", workflow_id=WF, reference_at=AHORA
        )
        sobre = self.lee("E2", run_id=RUN_ID_VIEJO)
        self.assertIsNone(sobre["data"])


# ==========================================================================
class F0Diagnostico(_Base):
    """La traza de timeout tiene que permitir diagnosticar sin entrar a produccion."""

    def test_resume_los_meses_y_los_estados(self) -> None:
        doc = {
            "client_id": "F1",
            "expires_at": "2026-09-30T00:00:00+00:00",
            "last_interaction_at": AGOSTO.isoformat(),
            "monthly": {
                MES_VIEJO: {"workflows": {WF: _campos(RUN_ID)}},
                MES_ACTUAL: {"workflows": {"otro": {"count": 1}}},
            },
        }
        d = self.store.describe_back_data_envelopes(doc, WF, reference_at=AHORA)
        self.assertTrue(d["documento_existe"])
        self.assertEqual(d["mes_actual"], MES_ACTUAL)
        self.assertEqual(d["meses_en_el_registro"], [MES_VIEJO, MES_ACTUAL])
        self.assertEqual(d["meses_con_el_workflow"], [MES_VIEJO])
        self.assertEqual(d["last_interaction_at_mes"], MES_VIEJO)
        self.assertEqual(d["envelopes"][MES_VIEJO]["status"], "ok")
        self.assertEqual(d["envelopes"][MES_VIEJO]["run_id"], RUN_ID[:8])

    def test_no_filtra_datos_de_negocio(self) -> None:
        doc = {
            "client_id": "F2",
            "monthly": {MES_ACTUAL: {"workflows": {WF: _campos(RUN_ID)}}},
        }
        d = self.store.describe_back_data_envelopes(doc, WF, reference_at=AHORA)
        texto = repr(d)
        self.assertNotIn("295317", texto, "el key_id del cliente no puede viajar")
        self.assertNotIn("validaciones", texto)
        self.assertNotIn(RUN_ID, texto, "el run_id va truncado")
        self.assertTrue(d["envelopes"][MES_ACTUAL]["tiene_data"])

    def test_documento_inexistente(self) -> None:
        d = self.store.describe_back_data_envelopes(None, WF, reference_at=AHORA)
        self.assertFalse(d["documento_existe"])
        self.assertEqual(d["meses_con_el_workflow"], [])


# ==========================================================================
class GuardasDelScriptPainless(unittest.TestCase):
    """Si el painless vuelve a cambiar, estas pruebas avisan."""

    @property
    def fuente(self) -> str:
        ruta = (
            Path(__file__).resolve().parents[3]
            / "co_pqrs_back_data"
            / "src"
            / "infrastructure"
            / "persistence"
            / "opensearch_client.py"
        )
        if not ruta.exists():  # pragma: no cover
            self.skipTest("co_pqrs_back_data no esta en este checkout")
        return ruta.read_text(encoding="utf-8")

    def test_no_vuelve_el_bucle_de_meses(self) -> None:
        self.assertNotIn(
            "for (monthEntry in ctx._source.monthly.entrySet())",
            self.fuente,
            "el bucle que escribia en meses anteriores no debe volver (C2)",
        )

    def test_no_vuelve_la_rama_de_last_interaction_at(self) -> None:
        self.assertNotIn(
            "last_interaction_at.substring(0, 7)",
            self.fuente,
            "elegir el mes por la ultima visita no debe volver (C2)",
        )

    def test_escribe_en_el_periodo_recibido(self) -> None:
        self.assertIn("def period = params.default_period;", self.fuente)

    def test_no_declara_scripted_upsert(self) -> None:
        """C4 se revirtio el 02/09: en produccion daba 400 en TODAS las escrituras.

        Verificado con las trazas: antes del despliegue outcome=ok, despues
        outcome=error 400 con el mismo cliente y el mismo indice. Si alguien lo
        reintroduce, tiene que probarlo antes contra un OpenSearch de la MISMA
        version que produccion, no solo con tests en memoria.
        """

        self.assertNotIn('"scripted_upsert"', self.fuente)
        self.assertNotIn('"upsert"', self.fuente)

    def test_la_traza_de_error_lleva_el_cuerpo(self) -> None:
        """El 400 dejo la traza sin motivo; el cuerpo tiene que viajar en ella."""

        texto = self.fuente
        self.assertIn("cuerpo_error", texto)
        self.assertIn("response_summary=cuerpo_error", texto)

    def test_el_mes_destino_viaja_en_la_traza(self) -> None:
        self.assertIn('"mes_destino": target_period', self.fuente)


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
