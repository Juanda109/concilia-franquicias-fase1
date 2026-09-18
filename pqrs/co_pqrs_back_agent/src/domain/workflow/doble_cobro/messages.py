"""Catálogo de textos del flujo Doble Cobro.

Separa los mensajes que el agente CONSTRUYE en tiempo de ejecución del árbol de
pasos. El árbol (``doble_cobro.yml``) describe la estructura; este catálogo
(``messages.yml``) describe lo que lee el cliente, para que negocio pueda
cambiarlo sin tocar código.

Se valida al arrancar: si falta una clave o sobra una, el servicio no levanta.
Es preferible a descubrir el hueco a mitad de una conversación.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from infrastructure.entrypoint.api.errors.exceptions import ConfigurationError


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SelectorProductosMessages(_Base):
    """Paso 3.4.0.1: cuentas y tarjetas débito del cliente."""

    pregunta: str


class VigenciaMessages(_Base):
    """Paso 3.4.0.3: días hábiles de conciliación."""

    en_conciliacion: str = Field(description="Admite {dias_habiles}.")


class BotonesSelectorMessages(_Base):
    """Botones fijos del selector de transacciones."""

    pagina_anterior: str
    pagina_siguiente: str
    reportar: str
    reportar_contador: str = Field(description="Admite {cantidad} y {unidad}.")
    unidad_singular: str
    unidad_plural: str
    no_encuentro: str


class SelectorTransaccionesMessages(_Base):
    """Paso 3.4.0.6: listado de movimientos del rango."""

    pregunta: str
    paginacion: str = Field(
        description="Admite {desde}, {hasta}, {total}, {pagina} y {paginas}."
    )
    fecha: str = Field(description="Admite {fecha}.")
    seleccionadas: str = Field(description="Admite {cantidad}.")
    tope_alcanzado: str = Field(description="Admite {tope}.")
    etiqueta: str = Field(description="Admite {marca}, {comercio}, {monto}, {detalle}.")
    etiqueta_sin_detalle: str = Field(
        description="Variante sin hora ni últimos cuatro dígitos."
    )
    marca_seleccionada: str
    marca_sin_seleccionar: str
    sin_comercio: str
    botones: BotonesSelectorMessages


class ValidacionMessages(_Base):
    """Paso 3.4.0.7: qué se le dice al cliente sobre su selección."""

    sin_seleccion: str
    ninguna_pareja: str
    descartadas: str = Field(description="Admite {detalle}.")
    descartada_item: str = Field(description="Admite {comercio} y {monto}.")


class ConfirmacionMessages(_Base):
    """Paso 3.4.0.8: cierre del reporte."""

    registrado: str


class DobleCobroMessages(_Base):
    """Catálogo completo del flujo."""

    selector_productos: SelectorProductosMessages
    vigencia: VigenciaMessages
    selector_transacciones: SelectorTransaccionesMessages
    validacion: ValidacionMessages
    confirmacion: ConfirmacionMessages


@lru_cache(maxsize=1)
def load_doble_cobro_messages(
    messages_path: str | Path | None = None,
) -> DobleCobroMessages:
    """Carga el catálogo de textos de Doble Cobro.

    Se cachea: el catálogo no cambia mientras el proceso vive, así que editar el
    YAML exige reiniciar el servicio.
    """

    path = (
        Path(messages_path)
        if messages_path is not None
        else Path(__file__).with_name("messages.yml")
    )

    if not path.exists():
        raise ConfigurationError(
            "Doble cobro message catalog file not found.",
            details={"messages_path": str(path)},
        )

    raw_messages = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(raw_messages, dict):
        raise ConfigurationError(
            "Doble cobro message catalog file is invalid.",
            details={"messages_path": str(path)},
        )

    return DobleCobroMessages.model_validate(raw_messages)
