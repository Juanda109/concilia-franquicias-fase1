"""Persistencia durable de autorizaciones en OpenSearch.

Concurrencia (pliego, seccion 11): el claim de los jobs usa la concurrencia
optimista de OpenSearch (`if_seq_no` + `if_primary_term`). Dos workers pueden
leer el mismo job vencido, pero solo UNO logra escribir el lease: el otro
recibe 409 y lo suelta. Nada depende de memoria local: un reinicio del pod
solo pierde el lease, que expira y otro worker retoma el job.

El indice se crea con mapping EXPLICITO (regla del repo: nunca dynamic
mapping para campos que se agregan o filtran).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from domain.authorization.models import AuthorizationJob
from infrastructure.core.config import load_opensearch_settings

logger = logging.getLogger(__name__)

_MAPPING = {
    "mappings": {
        "properties": {
            "authorization_id": {"type": "keyword"},
            "conversation_id": {"type": "keyword"},
            "workflow": {"type": "keyword"},
            "step": {"type": "keyword"},
            "challenge": {"type": "keyword"},
            "idempotency_key": {"type": "keyword"},
            "status": {"type": "keyword"},
            "technical_status": {"type": "keyword"},
            "created_at": {"type": "double"},
            "deadline": {"type": "double"},
            "next_check_at": {"type": "double"},
            "attempts": {"type": "integer"},
            "resolved_at": {"type": "double"},
            "result_published": {"type": "boolean"},
            "last_error": {"type": "text"},
            "lease_until": {"type": "double"},
            "metadata": {"type": "object", "enabled": False},
        }
    }
}


class ConflictoDeVersion(Exception):
    """Otro proceso modifico el job entre la lectura y la escritura."""


class AuthorizationsStore:
    def __init__(self) -> None:
        self._settings = load_opensearch_settings()

    def _cliente(self) -> httpx.AsyncClient:
        s = self._settings
        return httpx.AsyncClient(
            base_url=s.base_url,
            auth=(s.username, s.password),
            verify=s.verify_ssl,
            timeout=8.0,
        )

    @property
    def _indice(self) -> str:
        return self._settings.indice

    async def asegurar_indice(self) -> None:
        """Crea el indice con su mapping si no existe (arranque del servicio)."""

        async with self._cliente() as cliente:
            resp = await cliente.head(f"/{self._indice}")
            if resp.status_code == 200:
                return
            resp = await cliente.put(f"/{self._indice}", json=_MAPPING)
            if resp.status_code not in (200, 201):
                # resource_already_exists en una carrera de arranque es benigno
                if "resource_already_exists" not in resp.text:
                    logger.error(
                        "No se pudo crear el indice %s: %s %s",
                        self._indice, resp.status_code, resp.text[:200],
                    )

    async def crear_si_no_existe(self, job: AuthorizationJob) -> tuple[AuthorizationJob, bool]:
        """Create-if-absent por authorization_id (que deriva de la idempotency_key).

        Devuelve (job_persistido, creado). Si ya existia, devuelve el EXISTENTE:
        dos POST equivalentes -> un solo push registrado (pliego, seccion 11).
        """

        async with self._cliente() as cliente:
            resp = await cliente.put(
                f"/{self._indice}/_create/{job.authorization_id}",
                params={"refresh": "true"},
                json=job.a_documento(),
            )
            if resp.status_code in (200, 201):
                return job, True
            if resp.status_code == 409:
                existente = await self.obtener(job.authorization_id)
                if existente is not None:
                    return existente, False
            resp.raise_for_status()
            raise RuntimeError("creacion no confirmada")  # inalcanzable

    async def obtener(self, authorization_id: str) -> AuthorizationJob | None:
        async with self._cliente() as cliente:
            resp = await cliente.get(f"/{self._indice}/_doc/{authorization_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return AuthorizationJob.desde_documento(resp.json().get("_source") or {})

    async def obtener_con_version(
        self, authorization_id: str
    ) -> tuple[AuthorizationJob, int, int] | None:
        """Job + (_seq_no, _primary_term) para escrituras con claim."""

        async with self._cliente() as cliente:
            resp = await cliente.get(
                f"/{self._indice}/_doc/{authorization_id}",
                params={"_source": "true"},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            cuerpo = resp.json()
            return (
                AuthorizationJob.desde_documento(cuerpo.get("_source") or {}),
                int(cuerpo["_seq_no"]),
                int(cuerpo["_primary_term"]),
            )

    async def guardar_si_version(
        self,
        job: AuthorizationJob,
        seq_no: int,
        primary_term: int,
        lease_until: float | None = None,
    ) -> None:
        """Escribe el job SOLO si nadie lo toco desde la lectura (claim)."""

        doc = job.a_documento()
        if lease_until is not None:
            doc["lease_until"] = lease_until
        async with self._cliente() as cliente:
            resp = await cliente.put(
                f"/{self._indice}/_doc/{job.authorization_id}",
                params={
                    "if_seq_no": seq_no,
                    "if_primary_term": primary_term,
                    "refresh": "true",
                },
                json=doc,
            )
            if resp.status_code == 409:
                raise ConflictoDeVersion(job.authorization_id)
            resp.raise_for_status()

    async def buscar_por_conversacion(
        self, conversation_id: str
    ) -> list[AuthorizationJob]:
        consulta = {
            "query": {"term": {"conversation_id": conversation_id}},
            "sort": [{"created_at": {"order": "desc"}}],
            "size": 10,
        }
        async with self._cliente() as cliente:
            resp = await cliente.post(f"/{self._indice}/_search", json=consulta)
            resp.raise_for_status()
            hits = (resp.json().get("hits") or {}).get("hits") or []
            return [AuthorizationJob.desde_documento(h.get("_source") or {}) for h in hits]

    async def pendientes_para_revisar(self, ahora: float, lote: int) -> list[str]:
        """Ids de jobs PENDING con next_check_at vencido y sin lease vigente."""

        consulta = {
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"status": "PENDING"}},
                        {"range": {"next_check_at": {"lte": ahora}}},
                    ],
                    "must_not": [
                        {"range": {"lease_until": {"gt": ahora}}},
                    ],
                }
            },
            # unmapped_type: si el indice existiera sin nuestro mapping (p. ej.
            # auto-creado durante un bloqueo del cluster), la busqueda degrada
            # en vez de romper el tick completo.
            "sort": [{"next_check_at": {"order": "asc", "unmapped_type": "double"}}],
            "size": lote,
            "_source": ["authorization_id"],
        }
        async with self._cliente() as cliente:
            resp = await cliente.post(f"/{self._indice}/_search", json=consulta)
            if resp.status_code != 200:
                logger.warning(
                    "Busqueda de pendientes fallo: %s %s",
                    resp.status_code, resp.text[:200],
                )
                return []
            hits = (resp.json().get("hits") or {}).get("hits") or []
            return [
                str((h.get("_source") or {}).get("authorization_id") or h.get("_id"))
                for h in hits
            ]
