from fastapi import APIRouter

from infrastructure.entrypoint.api.router.healthcheck.healthcheck_router import router as health_router
from infrastructure.entrypoint.api.router.logging.log_router import loggers_router
from infrastructure.entrypoint.api.router.v0.chat_router import router as chat_router

router = APIRouter()
router.include_router(healthcheck_routes)
router.include_router(backend_llm_v0_router)
router.include_router(loggers_router)
