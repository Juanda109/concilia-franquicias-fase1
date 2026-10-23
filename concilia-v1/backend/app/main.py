from app.api.procesamiento_franquicias import router as franquicias_router
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.consolidacion import router as consolidacion_router
from fastapi import Request
from fastapi.responses import JSONResponse
from psycopg.errors import LockNotAvailable

from app.services.bloqueo_jornada import BloqueoJornadaError

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI

from app.api.jornadas import router as jornadas_router
from app.api.archivos import router as archivos_router

from app.api.detalle_archivos import router as detalle_archivos_router

app = FastAPI(
    title="Concilia V1 - Conciliacion Franquicias",
    version="1.0.0",
    description="Backend MVP1 de conciliacion de franquicias"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)



@app.exception_handler(BloqueoJornadaError)
async def manejar_error_bloqueo_jornada(
    request: Request,
    exc: BloqueoJornadaError,
):
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "codigo": "CONFLICTO_JORNADA",
                "mensaje": str(exc),
            }
        },
    )


@app.exception_handler(LockNotAvailable)
async def manejar_timeout_bloqueo(
    request: Request,
    exc: LockNotAvailable,
):
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": "5"},
        content={
            "detail": {
                "codigo": "BLOQUEO_TEMPORAL",
                "mensaje": (
                    "Recurso temporalmente bloqueado. "
                    "Intente nuevamente."
                ),
            }
        },
    )

app.include_router(jornadas_router)

app.mount("/concilia-ui", StaticFiles(directory="frontend"), name="concilia-ui")

@app.get("/concilia", include_in_schema=False)
def pagina_concilia():
    return FileResponse("frontend/index.html")

app.include_router(consolidacion_router)
app.include_router(archivos_router)
app.include_router(franquicias_router)
app.include_router(detalle_archivos_router)


@app.get("/health")
def health():
    return {
        "status": "UP",
        "service": "concilia-backend",
        "version": "1.0.0"
    }

from app.api.confirmacion_sin_movimientos import router as confirmacion_sin_movimientos_router
app.include_router(confirmacion_sin_movimientos_router)

from app.api.excepciones_cant import router as excepciones_cant_router
app.include_router(excepciones_cant_router)
