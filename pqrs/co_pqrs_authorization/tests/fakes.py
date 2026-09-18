"""Dobles de prueba compartidos: store en memoria con semantica de versiones
identica a OpenSearch (seq_no + conflicto 409) y ASO/publisher falsos."""

from __future__ import annotations

from typing import Any

from domain.authorization.models import AuthorizationJob
from infrastructure.persistence.authorizations_store import ConflictoDeVersion


class StoreEnMemoria:
    """Replica la semantica de concurrencia del store real: cada escritura
    incrementa seq_no; guardar con un seq_no viejo lanza ConflictoDeVersion."""

    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}
        self._seq: dict[str, int] = {}

    async def crear_si_no_existe(self, job: AuthorizationJob):
        if job.authorization_id in self._docs:
            return (
                AuthorizationJob.desde_documento(self._docs[job.authorization_id]),
                False,
            )
        self._docs[job.authorization_id] = job.a_documento()
        self._seq[job.authorization_id] = 0
        return job, True

    async def obtener(self, authorization_id: str):
        doc = self._docs.get(authorization_id)
        return AuthorizationJob.desde_documento(doc) if doc else None

    async def obtener_con_version(self, authorization_id: str):
        doc = self._docs.get(authorization_id)
        if doc is None:
            return None
        return (
            AuthorizationJob.desde_documento(doc),
            self._seq[authorization_id],
            1,
        )

    async def guardar_si_version(self, job, seq_no, primary_term, lease_until=None):
        actual = self._seq.get(job.authorization_id)
        if actual is None or actual != seq_no:
            raise ConflictoDeVersion(job.authorization_id)
        doc = job.a_documento()
        if lease_until is not None:
            doc["lease_until"] = lease_until
        self._docs[job.authorization_id] = doc
        self._seq[job.authorization_id] = actual + 1

    async def buscar_por_conversacion(self, conversation_id: str):
        return [
            AuthorizationJob.desde_documento(d)
            for d in self._docs.values()
            if d.get("conversation_id") == conversation_id
        ]

    async def pendientes_para_revisar(self, ahora: float, lote: int):
        ids = []
        for d in self._docs.values():
            if d.get("status") != "PENDING":
                continue
            if float(d.get("next_check_at") or 0) > ahora:
                continue
            if float(d.get("lease_until") or 0) > ahora:
                continue
            ids.append(d["authorization_id"])
        return ids[:lote]


class AsoFalso:
    """Respuestas programables: lista de (estado, error) que se consumen en orden."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.consultas = 0

    async def consultar_estado(self, challenge: str):
        self.consultas += 1
        if not self.respuestas:
            return "PENDING", ""
        if len(self.respuestas) == 1:
            return self.respuestas[0]
        return self.respuestas.pop(0)


class PublisherEspia:
    def __init__(self) -> None:
        self.publicados: list[Any] = []

    async def publicar(self, job) -> None:
        self.publicados.append(job)
