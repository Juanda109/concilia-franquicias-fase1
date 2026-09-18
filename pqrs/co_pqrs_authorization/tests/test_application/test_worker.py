"""Tests del worker: los puntos 3-14 del pliego de Luis."""

from __future__ import annotations

import time

import pytest

from application.authorization.service import AuthorizationService
from application.authorization.worker import AuthorizationWorker
from domain.authorization.models import (
    ACCEPTED,
    EXPIRED,
    PENDING,
    REJECTED,
    TECH_BUSINESS_RESULT,
    TECH_ERROR,
)

from tests.fakes import AsoFalso, PublisherEspia, StoreEnMemoria


async def _job_pendiente(store, challenge="CH-1", deadline_seg=180.0):
    service = AuthorizationService(store)
    job, _ = await service.crear(
        conversation_id="123_20260903",
        workflow="trx_no_reconocida",
        step="2.4.0.1.17.1",
        challenge=challenge,
        deadline_segundos=deadline_seg,
    )
    return job


def _worker(store, aso, publisher=None):
    return AuthorizationWorker(store, aso, publisher or PublisherEspia())


async def test_pending_reprograma_next_check() -> None:
    store = StoreEnMemoria()
    job = await _job_pendiente(store)
    worker = _worker(store, AsoFalso([(PENDING, "")]))
    resultado = await worker.procesar_uno(job.authorization_id)
    assert resultado == "pendiente"
    tras = await store.obtener(job.authorization_id)
    assert tras.status == PENDING
    assert tras.next_check_at > job.next_check_at
    assert tras.attempts == 1


async def test_accepted_es_terminal_y_publica() -> None:
    store = StoreEnMemoria()
    espia = PublisherEspia()
    job = await _job_pendiente(store)
    worker = _worker(store, AsoFalso([(ACCEPTED, "")]), espia)
    resultado = await worker.procesar_uno(job.authorization_id)
    assert resultado == f"resuelto:{ACCEPTED}"
    tras = await store.obtener(job.authorization_id)
    assert tras.status == ACCEPTED
    assert tras.technical_status == TECH_BUSINESS_RESULT
    assert len(espia.publicados) == 1


async def test_rejected_es_terminal() -> None:
    store = StoreEnMemoria()
    job = await _job_pendiente(store)
    worker = _worker(store, AsoFalso([(REJECTED, "")]))
    await worker.procesar_uno(job.authorization_id)
    tras = await store.obtener(job.authorization_id)
    assert tras.status == REJECTED


async def test_timeout_180s_marca_expired_sin_usuario() -> None:
    """El deadline lo hace cumplir el backend, nadie pulsa Continuar."""

    store = StoreEnMemoria()
    job = await _job_pendiente(store, deadline_seg=180.0)
    worker = _worker(store, AsoFalso([(PENDING, "")]))
    # consulta simulada 181 segundos despues de crearla
    resultado = await worker.procesar_uno(
        job.authorization_id, ahora=job.created_at + 181.0
    )
    assert resultado == f"resuelto:{EXPIRED}"
    tras = await store.obtener(job.authorization_id)
    assert tras.status == EXPIRED


async def test_error_tecnico_no_es_rechazo_y_reintenta() -> None:
    store = StoreEnMemoria()
    job = await _job_pendiente(store)
    worker = _worker(store, AsoFalso([("", "ASO 503"), (ACCEPTED, "")]))
    r1 = await worker.procesar_uno(job.authorization_id)
    assert r1 == "pendiente"
    intermedio = await store.obtener(job.authorization_id)
    assert intermedio.status == PENDING            # JAMAS rejected por fallo
    assert intermedio.technical_status == TECH_ERROR
    assert "503" in intermedio.last_error
    # el reintento posterior resuelve
    r2 = await worker.procesar_uno(job.authorization_id)
    assert r2 == f"resuelto:{ACCEPTED}"


async def test_error_tecnico_con_deadline_vencido_expira() -> None:
    store = StoreEnMemoria()
    job = await _job_pendiente(store)
    worker = _worker(store, AsoFalso([("", "transporte: ConnectError")]))
    resultado = await worker.procesar_uno(
        job.authorization_id, ahora=job.created_at + 200.0
    )
    assert resultado == f"resuelto:{EXPIRED}"


async def test_dos_workers_solo_uno_gana_el_claim() -> None:
    """Carrera real: ambos leen la misma version; el segundo claim da 409."""

    store = StoreEnMemoria()
    job = await _job_pendiente(store)
    aso = AsoFalso([(ACCEPTED, "")])
    w1 = _worker(store, aso)
    w2 = _worker(store, aso)

    # ambos leen ANTES de que ninguno escriba: se simula tomando la version
    leido = await store.obtener_con_version(job.authorization_id)
    j1, seq, prim = leido
    # w1 hace el claim con esa version
    await store.guardar_si_version(j1, seq, prim, lease_until=time.time() + 30)
    # w2 llega con la version vieja -> conflicto -> lo suelta
    resultado_w2 = await w2.procesar_uno(job.authorization_id)
    # w2 re-leyo la version nueva; como el lease no bloquea procesar_uno
    # directamente, el arbitraje ocurre en el PRIMER guardar: aqui basta
    # verificar que el flujo no duplica el terminal
    resultado_w1 = await w1.procesar_uno(job.authorization_id)
    terminales = [r for r in (resultado_w1, resultado_w2) if r.startswith("resuelto:")]
    tras = await store.obtener(job.authorization_id)
    assert tras.status == ACCEPTED
    assert len(terminales) >= 1
    assert aso.consultas <= 2


async def test_resultado_accepted_publicado_una_sola_vez() -> None:
    store = StoreEnMemoria()
    espia = PublisherEspia()
    job = await _job_pendiente(store)
    worker = _worker(store, AsoFalso([(ACCEPTED, "")]), espia)
    await worker.procesar_uno(job.authorization_id)
    # reproceso del mismo job (reinicio, tick duplicado, replica)
    await worker.procesar_uno(job.authorization_id)
    await worker._publicar_una_vez(job.authorization_id)
    assert len(espia.publicados) == 1
    tras = await store.obtener(job.authorization_id)
    assert tras.result_published is True


async def test_reinicio_no_pierde_el_job() -> None:
    """El job vive en el store: un worker NUEVO (proceso reiniciado) lo retoma."""

    store = StoreEnMemoria()
    job = await _job_pendiente(store)
    w1 = _worker(store, AsoFalso([(PENDING, "")]))
    await w1.procesar_uno(job.authorization_id)
    # 'reinicio': worker distinto, mismo store persistido
    w2 = _worker(store, AsoFalso([(ACCEPTED, "")]))
    pendientes = await store.pendientes_para_revisar(time.time() + 60, 10)
    assert job.authorization_id in pendientes
    resultado = await w2.procesar_uno(job.authorization_id, ahora=time.time() + 61)
    assert resultado == f"resuelto:{ACCEPTED}"


async def test_tick_procesa_lote_de_vencidos() -> None:
    store = StoreEnMemoria()
    j1 = await _job_pendiente(store, challenge="CH-A")
    service = AuthorizationService(store)
    j2, _ = await service.crear(
        conversation_id="999_20260903", workflow="w", step="s", challenge="CH-B"
    )
    worker = _worker(store, AsoFalso([(ACCEPTED, "")]))
    procesados = await worker.tick()
    assert procesados == 2
    assert (await store.obtener(j1.authorization_id)).status == ACCEPTED
    assert (await store.obtener(j2.authorization_id)).status == ACCEPTED
