from fastapi import FastAPI
from src.infrastructure.entrypoint.api.router.v0.trx_router import router as trx_router

app = FastAPI()

# Endpoint para la prueba de salud de Kubernetes / OpenShift
@app.get("/health")
async def health_check():
    return {"status": "ok"}

app.include_router(trx_router)