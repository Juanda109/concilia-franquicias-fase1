from app.api.reporte_maestro_diagnostico import router as reporte_maestro_router
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
app.include_router(reporte_maestro_router)


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

# INC47: endpoint aditivo Credibanco, no altera el endpoint INC33
from app.api.reporte_credibanco_inc47 import router as reporte_credibanco_inc47_router
app.include_router(reporte_credibanco_inc47_router)

# INC50: reporte diagnostico Host, no homologado
from app.api.reporte_host_inc50 import router as reporte_host_inc50_router
app.include_router(reporte_host_inc50_router)

# INC51: diagnostico monetario CAET/CANT, sin homologacion
from app.api.reporte_credibanco_inc51 import router as reporte_credibanco_inc51_router
app.include_router(reporte_credibanco_inc51_router)

# CONCILIA_SYNC3976_API: synthetic read-only fixture, never certified.
from app.api.credibanco_sync3976_api import router as sync3976_router
app.include_router(sync3976_router)

# CONCILIA_V22_RUTA_INDEPENDIENTE
from app.api.reporte_maestro_diagnostico import router_ensayo_v22
app.include_router(router_ensayo_v22)

# CONCILIA_V24_AUDITORIA_PERSISTIDA
from app.api.router_v24 import router as auditoria_v24_router
app.include_router(auditoria_v24_router)


# CONCILIA_V26_ROUTER
from app.api.router_v26 import router as motor_v26_router
app.include_router(motor_v26_router)

# CONCILIA_V27_CRITERIOS_ACEPTACION
from app.api.router_criterios_v27 import router as criterios_v27_router
app.include_router(criterios_v27_router)

# CONCILIA_V67_CIERRE_CREDIBANCO_SOLO_LECTURA
from app.api.cierre_credibanco_v67 import router as cierre_credibanco_v67_router
app.include_router(cierre_credibanco_v67_router)

# CONCILIA_V71_QA_PANTALLA_BEGIN
# CONCILIA_V71_QA_PANTALLA_END

from app.api.reporte_credibanco_productivo import router as reporte_credibanco_productivo_router
app.include_router(reporte_credibanco_productivo_router)

# F2 5683: endpoint opt-in, aislado del catalogo productivo
import os
if os.getenv("CONCILIA_F2_DIAGNOSTICO_TEST") == "1":
    from app.api.credibanco_f2_prueba_5683 import router as f2_prueba_5683_router
    app.include_router(f2_prueba_5683_router)
