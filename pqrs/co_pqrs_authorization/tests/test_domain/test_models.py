"""Dominio: normalizacion ASO->negocio y transiciones de resolver_consulta."""

from domain.authorization.models import (
    ACCEPTED, EXPIRED, PENDING, REJECTED,
    TECH_BUSINESS_RESULT, TECH_ERROR, TECH_SUCCESS,
    AuthorizationJob, authorization_id_desde, normalizar_estado_aso,
    resolver_consulta,
)


def _job(deadline=1000.0):
    return AuthorizationJob(
        authorization_id="auth-x", conversation_id="c", workflow="w",
        step="s", challenge="CH", idempotency_key="k",
        created_at=0.0, deadline=deadline, next_check_at=0.0,
    )


def test_normalizacion_cubre_sinonimos():
    assert normalizar_estado_aso("accepted") == ACCEPTED
    assert normalizar_estado_aso("APPROVED") == ACCEPTED
    assert normalizar_estado_aso("denied") == REJECTED
    assert normalizar_estado_aso("timeout") == EXPIRED
    assert normalizar_estado_aso("pending") == PENDING


def test_ok_no_es_aceptado():
    # leccion del 28/08: palabras de sobre no son estados del reto
    assert normalizar_estado_aso("ok") is None
    assert normalizar_estado_aso("success") is None
    assert normalizar_estado_aso("") is None


def test_id_es_determinista():
    assert authorization_id_desde("a:b:c") == authorization_id_desde("a:b:c")
    assert authorization_id_desde("a:b:c") != authorization_id_desde("a:b:d")


def test_accepted_resuelve_terminal():
    job = resolver_consulta(_job(), ACCEPTED, "", ahora=10.0, intervalo_reintento=5.0)
    assert job.status == ACCEPTED
    assert job.technical_status == TECH_BUSINESS_RESULT
    assert job.resolved_at == 10.0


def test_pending_reprograma():
    job = resolver_consulta(_job(), PENDING, "", ahora=10.0, intervalo_reintento=5.0)
    assert job.status == PENDING
    assert job.technical_status == TECH_SUCCESS
    assert job.next_check_at == 15.0


def test_deadline_gana_a_pending():
    job = resolver_consulta(
        _job(deadline=9.0), PENDING, "", ahora=10.0, intervalo_reintento=5.0
    )
    assert job.status == EXPIRED


def test_error_tecnico_no_degrada_a_rechazo():
    job = resolver_consulta(_job(), None, "ASO 500", ahora=10.0, intervalo_reintento=5.0)
    assert job.status == PENDING
    assert job.technical_status == TECH_ERROR
    assert job.next_check_at == 15.0
