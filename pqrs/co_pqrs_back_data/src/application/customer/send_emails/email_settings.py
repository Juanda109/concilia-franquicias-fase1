"""SMTP settings for the central-risk extract email.

Replica la configuración SMTP de ``pqr_iron/Src/enviar_comunicado.py`` (la
réplica en Python de la macro VBA ``EnviarCorreos``) pero cargándola desde el
``.env`` de ``co_pqrs_back_data`` con el mismo patrón Pydantic que usa
``infrastructure/core/config.py``.

Las variables se leen con ``load_env_constants`` del core para respetar la
precedencia del proyecto: ``.env`` -> ``config/{env}/config.cfg`` -> entorno.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from infrastructure.core.config import load_env_constants


class SmtpSettings(BaseModel):
    """Configuración del envío SMTP de un único correo de extracto."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # --- Conexión SMTP (defaults = los de la macro: relay interno, sin TLS/auth) ---
    host: str = Field(default="mailB.bbva.com.co", description="Servidor SMTP relay.")
    port: int = Field(default=25, ge=1, description="Puerto SMTP.")
    use_tls: bool = Field(default=False, description="Usar STARTTLS.")
    user: str | None = Field(default=None, description="Usuario SMTP (si requiere auth).")
    password: str | None = Field(default=None, description="Password SMTP.")
    timeout: float = Field(default=10.0, ge=1.0, description="Timeout de conexión (s).")

    # --- Cabeceras del mensaje ---
    mail_from: str = Field(
        default="bbva-valores-colombia@bbva.com",
        description="Remitente del correo.",
    )
    mail_from_name: str = Field(
        default="BBVA",
        description="Nombre visible del remitente.",
    )
    bcc: str | None = Field(
        default=None,
        description="Copia oculta opcional.",
    )
    subject: str = Field(
        default="Tu documento soporte ya está listo - BBVA",
        description="Asunto del correo.",
    )

    # --- Control de envío / modo mock ---
    enabled: bool = Field(
        default=False,
        description=(
            "Si es False NO se abre conexión SMTP: solo se renderiza y registra "
            "el correo (modo mock/dry-run). Poner en True para enviar de verdad."
        ),
    )
    test_mode: bool = Field(
        default=False,
        description="Si es True, redirige el destinatario real a 'test_to'.",
    )
    test_to: str | None = Field(
        default=None,
        description="Correo de pruebas usado cuando test_mode=True.",
    )


def _parse_bool(value: str | None, *, default: bool) -> bool:
    """Parse a boolean-like environment value (igual criterio que core/config)."""

    if value is None:
        return default

    return value.strip().casefold() not in {"0", "false", "no", "off"}


def load_smtp_settings(env_path: str | Path = ".env") -> SmtpSettings:
    """Carga la configuración SMTP del entorno (.env / config.cfg / os.environ)."""

    constants = load_env_constants(env_path)

    return SmtpSettings(
        host=constants.get("SMTP_HOST", "mailB.bbva.com.co"),
        port=int(constants.get("SMTP_PORT", "25")),
        use_tls=_parse_bool(constants.get("SMTP_USE_TLS"), default=False),
        user=constants.get("SMTP_USER") or None,
        password=constants.get("SMTP_PASSWORD") or None,
        timeout=float(constants.get("SMTP_TIMEOUT", "10")),
        mail_from=constants.get("MAIL_FROM", "bbva-valores-colombia@bbva.com"),
        mail_from_name=constants.get("MAIL_FROM_NAME", "BBVA"),
        bcc=constants.get("MAIL_BCC") or None,
        subject=constants.get(
            "MAIL_SUBJECT",
            "Tu documento soporte ya está listo - BBVA",
        ),
        enabled=_parse_bool(constants.get("MAIL_ENABLED"), default=False),
        test_mode=_parse_bool(constants.get("MAIL_TEST_MODE"), default=False),
        test_to=constants.get("MAIL_TEST_TO") or None,
    )
