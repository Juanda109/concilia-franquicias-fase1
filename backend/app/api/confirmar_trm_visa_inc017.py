"""Confirmacion TRM local: solo loopback y base de pruebas, opt-in."""
import os
import ipaddress
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from psycopg import Error as PsycopgError

from app.api.propuesta_trm_visa_inc017 import consultar_fecha_contable
from app.repositories.trm_visa_inc017 import registrar_confirmacion_trm
from app.services.fase2.trm_visa_inc017 import validar_trm

router = APIRouter(prefix="/api/v1/jornadas", tags=["TRM Visa Fase 2"])


class IdentidadAutorizada(BaseModel):
    usuario: str
    permiso: str


def exigir_autorizacion_trm(request: Request) -> IdentidadAutorizada:
    # Solo pruebas locales. No confiar en X-Forwarded-For ni en identidades del cliente.
    host = request.client.host if request.client else ""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if not (
        os.getenv("DB_NAME") == "concilia_test"
        and os.getenv("CONCILIA_TRM_LOCAL_SIN_AUTH") == "1"
        and loopback
    ):
        raise HTTPException(503, "Confirmacion TRM local no habilitada")
    return IdentidadAutorizada(usuario="PRUEBA_LOCAL_SIN_AUTENTICACION", permiso="TRM_CONFIRMAR")


class SolicitudConfirmacion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modo: str
    trm_aplicada: Decimal | None = None


@router.post("/{id_jornada}/trm-visa/confirmar")
def confirmar_trm(
    id_jornada: int,
    solicitud: SolicitudConfirmacion,
    identidad: Annotated[IdentidadAutorizada, Depends(exigir_autorizacion_trm)],
):
    if identidad.permiso != "TRM_CONFIRMAR":
        raise HTTPException(403, "Sin permiso para confirmar TRM")
    if id_jornada <= 0:
        raise HTTPException(422, "Jornada invalida")
    if solicitud.modo != "manual":
        raise HTTPException(422, "Solo se permite ingreso manual de TRM")
    if solicitud.trm_aplicada is None:
        raise HTTPException(422, "TRM obligatoria")
    try:
        aplicada = validar_trm(solicitud.trm_aplicada)
        # La persistencia valida la jornada y evita una segunda confirmacion
        # bajo bloqueo transaccional de con_jornada.
        return registrar_confirmacion_trm(
            id_jornada=id_jornada,
            trm_aplicada=aplicada,
            trm_oficial=None,
            fuente="MANUAL_USUARIO",
            referencia_fuente=None,
            modificada_manualmente=True,
            justificacion=None,
            usuario_autenticado=identidad.usuario,
        )
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(404, "Jornada inexistente") from exc
    except PsycopgError as exc:
        raise HTTPException(503, "Base de datos no disponible") from exc
    except ValueError as exc:
        raise HTTPException(409, "TRM o estado de jornada inconsistente") from exc
