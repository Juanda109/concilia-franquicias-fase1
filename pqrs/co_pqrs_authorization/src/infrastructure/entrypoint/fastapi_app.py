"""Entrypoint FastAPI del servicio de autorizacion (puerto 8005)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from application.authorization.service import AuthorizationService
from application.authorization.worker import AuthorizationWorker
from infrastructure.core.config import load_worker_settings
from infrastructure.messaging.result_publisher import LogResultPublisher
from infrastructure.persistence.aso_client import AsoAuthorizationClient
from infrastructure.persistence.authorizations_store import AuthorizationsStore
from infrastructure.entrypoint.api.router.v1.authorizations_router import (
    construir_router,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    store = AuthorizationsStore()
    try:
        await store.asegurar_indice()
    except Exception:
        # El servicio arranca igual: el primer create reintentara y el
        # healthcheck delata el problema de fondo.
        logger.exception("No se pudo asegurar el indice de autorizaciones")

    worker = AuthorizationWorker(store, AsoAuthorizationClient(), LogResultPublisher())
    tarea = None
    if load_worker_settings().habilitado:
        # El loop es una tarea del proceso, pero los JOBS viven en OpenSearch:
        # un reinicio no pierde nada (pliego, secciones 4 y 11). Con N replicas
        # hay N workers compitiendo y el claim optimista arbitra.
        tarea = asyncio.create_task(worker.correr())
    yield
    worker.parar()
    if tarea is not None:
        try:
            await asyncio.wait_for(tarea, timeout=5)
        except asyncio.TimeoutError:
            tarea.cancel()


app = FastAPI(
    title="co_pqrs_authorization",
    version="0.1.0",
    lifespan=_lifespan,
)

_store = AuthorizationsStore()
_service = AuthorizationService(_store)
app.include_router(construir_router(_service))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "co_pqrs_authorization"}
