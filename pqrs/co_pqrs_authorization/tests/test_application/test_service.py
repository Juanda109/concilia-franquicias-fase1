"""Creacion idempotente y consulta (puntos 1, 2, 12 del pliego)."""

from application.authorization.service import AuthorizationService
from domain.authorization.models import PENDING

from tests.fakes import StoreEnMemoria


async def test_crear_persiste_pending_con_deadline():
    service = AuthorizationService(StoreEnMemoria())
    job, creada = await service.crear(
        conversation_id="123_20260903", workflow="trx_no_reconocida",
        step="2.4.0.1.17.1", challenge="CH-1",
    )
    assert creada is True
    assert job.status == PENDING
    assert job.deadline > job.created_at
    assert job.deadline - job.created_at == 180.0


async def test_creacion_es_idempotente():
    store = StoreEnMemoria()
    service = AuthorizationService(store)
    a, creada_a = await service.crear(
        conversation_id="c", workflow="w", step="s", challenge="CH-1"
    )
    b, creada_b = await service.crear(
        conversation_id="c", workflow="w", step="s", challenge="CH-1"
    )
    assert creada_a is True and creada_b is False
    assert a.authorization_id == b.authorization_id
    assert len(await store.buscar_por_conversacion("c")) == 1


async def test_idempotency_key_explicita_manda():
    service = AuthorizationService(StoreEnMemoria())
    a, _ = await service.crear(
        conversation_id="c", workflow="w", step="s", challenge="CH-1",
        idempotency_key="clave-fija",
    )
    b, creada = await service.crear(
        conversation_id="OTRA", workflow="w", step="s", challenge="CH-2",
        idempotency_key="clave-fija",
    )
    assert creada is False
    assert a.authorization_id == b.authorization_id
