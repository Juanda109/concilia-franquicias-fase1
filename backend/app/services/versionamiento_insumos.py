"""Politica pura para recepcion y versionamiento de insumos por jornada.

La version nueva nunca modifica ni elimina el archivo/detalle anterior. La
referencia vigente se cambia desde la transaccion de recepcion de la API.
"""
from __future__ import annotations


class VersionamientoInsumoError(ValueError):
    """La solicitud de recepcion contradice la politica de versionamiento."""


def decidir_recepcion(
    *,
    estado_insumo: str,
    estado_archivo: str | None,
    id_archivo_actual: int | None,
    nueva_version: bool = False,
    motivo_version: str | None = None,
) -> str:
    """Devuelve INICIAL, REEMPLAZO_RECIBIDO o NUEVA_VERSION.

    Un archivo ya procesado solo se puede sustituir mediante una nueva
    version explicita y con motivo. Un archivo RECIBIDO conserva la politica
    anterior de reemplazo, salvo que el cliente solicite versionarlo.
    """
    estado_insumo = (estado_insumo or "").strip().upper()
    estado_archivo = (estado_archivo or "").strip().upper() or None
    motivo = (motivo_version or "").strip()

    if id_archivo_actual is None:
        if estado_insumo != "PENDIENTE" or estado_archivo is not None:
            raise VersionamientoInsumoError(
                "Insumo sin archivo con estado incompatible."
            )
        if nueva_version or motivo:
            raise VersionamientoInsumoError(
                "No se puede solicitar nueva version para un insumo sin archivo previo."
            )
        return "INICIAL"

    if estado_archivo != estado_insumo:
        raise VersionamientoInsumoError(
            "Estados de archivo e insumo incompatibles; requiere regularizacion."
        )

    if estado_insumo == "PROCESADO":
        if not nueva_version:
            raise VersionamientoInsumoError(
                "El insumo ya esta procesado. Para sustituirlo, enviar "
                "nueva_version=true y motivo_version."
            )
        if not motivo:
            raise VersionamientoInsumoError(
                "motivo_version es obligatorio para sustituir un archivo procesado."
            )
        if len(motivo) > 500:
            raise VersionamientoInsumoError(
                "motivo_version no puede superar 500 caracteres."
            )
        return "NUEVA_VERSION"

    if estado_insumo == "RECIBIDO":
        if nueva_version:
            if not motivo:
                raise VersionamientoInsumoError(
                    "motivo_version es obligatorio para crear una nueva version."
                )
            if len(motivo) > 500:
                raise VersionamientoInsumoError(
                    "motivo_version no puede superar 500 caracteres."
                )
            return "NUEVA_VERSION"
        return "REEMPLAZO_RECIBIDO"

    raise VersionamientoInsumoError(
        f"No se permite recibir sobre un insumo en estado {estado_insumo or 'DESCONOCIDO'}."
    )
