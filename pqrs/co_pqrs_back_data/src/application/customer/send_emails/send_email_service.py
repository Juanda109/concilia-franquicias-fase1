"""Servicio de envío del correo de extracto de centrales.

Reutiliza el núcleo de ``pqr_iron/Src/enviar_comunicado.py`` (smtplib + email)
pero para el caso de un único destinatario y usando como cuerpo el template
``templates/extracto_centrales.html`` (el formato corporativo BBVA).

Función pública pensada para ser llamada desde cualquier parte del flujo:

    enviar_correo_extracto(
        nombre_cliente="PABLO MOSQUERA",
        producto="Tarjeta de Crédito",
        fecha="11/05/2026",
        correo="cliente@correo.com",
        adjunto_base64="<base64 del PDF soporte | None>",
    )

Todos los datos llegan desde el flujo del agente. El ``adjunto`` es opcional
(lo genera otro servicio y se entrega en base64). El envío real solo ocurre si
``MAIL_ENABLED=true``; de lo contrario corre en modo mock/dry-run (renderiza y
registra, sin abrir conexión SMTP), lo que lo hace seguro para pruebas y para
no romper el flujo.
"""

from __future__ import annotations

import base64
import binascii
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from pathlib import Path

from infrastructure.core.logger import get_logger, log_execution

from application.customer.send_emails.email_settings import (
    SmtpSettings,
    load_smtp_settings,
)

logger = get_logger(__name__)

_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "extracto_centrales.html"

# Marcadores presentes en el HTML corporativo.
_PLACEHOLDER_NOMBRE = "[Nombre de cliente]"
_PLACEHOLDER_PRODUCTO = "[Tipo de producto]"
_PLACEHOLDER_FECHA = "[DD/MM/AAAA]"


def _load_template() -> str:
    """Lee el template HTML del extracto desde disco."""

    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def render_html(*, nombre_cliente: str, producto: str, fecha: str) -> str:
    """Renderiza el cuerpo HTML reemplazando los marcadores del template."""

    html = _load_template()
    html = html.replace(_PLACEHOLDER_NOMBRE, nombre_cliente or "")
    html = html.replace(_PLACEHOLDER_PRODUCTO, producto or "")
    html = html.replace(_PLACEHOLDER_FECHA, fecha or "")
    return html


def _decode_attachment(adjunto_base64: str | None) -> bytes | None:
    """Decodifica el adjunto base64 a bytes. Devuelve None si no hay adjunto."""

    if not adjunto_base64:
        return None

    try:
        return base64.b64decode(adjunto_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"Adjunto base64 inválido: {exc}") from exc


def _attachment_subtype(filename: str) -> str:
    """Resuelve el subtipo MIME del adjunto a partir de su extensión."""

    return "pdf" if filename.lower().endswith(".pdf") else "octet-stream"


def build_message(
    settings: SmtpSettings,
    *,
    to: str,
    html: str,
    adjunto_bytes: bytes | None,
    adjunto_filename: str,
) -> EmailMessage:
    """Construye el ``EmailMessage`` (texto plano de respaldo + HTML + adjunto)."""

    msg = EmailMessage()
    msg["Subject"] = settings.subject
    msg["From"] = formataddr((settings.mail_from_name, settings.mail_from))
    msg["To"] = to
    if settings.bcc:
        msg["Bcc"] = settings.bcc

    # Respaldo para clientes sin HTML.
    msg.set_content(
        "El documento que nos solicitaste ya está listo. "
        "Este correo requiere un cliente compatible con HTML para visualizarse. "
        "BBVA Colombia."
    )
    msg.add_alternative(html, subtype="html")

    if adjunto_bytes is not None:
        msg.add_attachment(
            adjunto_bytes,
            maintype="application",
            subtype=_attachment_subtype(adjunto_filename),
            filename=adjunto_filename,
        )

    return msg


@log_execution
def enviar_correo_extracto(
    *,
    nombre_cliente: str,
    producto: str,
    fecha: str,
    correo: str,
    adjunto_base64: str | None = None,
    adjunto_filename: str = "soporte_contratacion.pdf",
    settings: SmtpSettings | None = None,
) -> bool:
    """Envía el correo de extracto a un cliente.

    Parámetros (todos llegan desde el flujo del agente):
        nombre_cliente: nombre que se inyecta en el saludo del HTML.
        producto: tipo de producto contratado.
        fecha: fecha de la consulta/contratación (formato DD/MM/AAAA).
        correo: destinatario.
        adjunto_base64: PDF soporte en base64 (opcional; lo genera otro servicio).
        adjunto_filename: nombre del archivo adjunto.
        settings: configuración SMTP; si es None se carga del entorno.

    Devuelve True si el correo se envió (o se simuló en modo mock) y False si
    hubo un error. No levanta excepciones, para no romper el flujo que lo invoca.
    """

    settings = settings or load_smtp_settings()

    # Destinatario efectivo (modo test redirige a un buzón de pruebas).
    destinatario = correo
    if settings.test_mode and settings.test_to:
        logger.info(
            "MAIL_TEST_MODE activo: redirigiendo %s -> %s",
            correo or "(vacío)",
            settings.test_to,
        )
        destinatario = settings.test_to

    if not parseaddr(destinatario)[1]:
        logger.warning("Correo destino inválido o vacío: %r", destinatario)
        return False

    try:
        html = render_html(
            nombre_cliente=nombre_cliente,
            producto=producto,
            fecha=fecha,
        )
        adjunto_bytes = _decode_attachment(adjunto_base64)
        message = build_message(
            settings,
            to=destinatario,
            html=html,
            adjunto_bytes=adjunto_bytes,
            adjunto_filename=adjunto_filename,
        )
    except Exception:  # noqa: BLE001 - registrar y no romper el flujo
        logger.exception("Fallo construyendo el correo de extracto to=%s", destinatario)
        return False

    tiene_adjunto = adjunto_bytes is not None

    # Modo mock / dry-run: no se abre conexión SMTP.
    if not settings.enabled:
        logger.info(
            "[MOCK] Correo de extracto NO enviado (MAIL_ENABLED=false). "
            "to=%s subject=%r adjunto=%s host=%s:%s",
            destinatario,
            settings.subject,
            "sí" if tiene_adjunto else "no",
            settings.host,
            settings.port,
        )
        return True

    try:
        with smtplib.SMTP(settings.host, settings.port, timeout=settings.timeout) as server:
            if settings.use_tls:
                server.starttls(context=ssl.create_default_context())
            if settings.user:
                server.login(settings.user, settings.password or "")
            server.send_message(message)
        logger.info("Correo de extracto enviado to=%s adjunto=%s", destinatario, tiene_adjunto)
        return True
    except smtplib.SMTPException as exc:  # noqa: BLE001 - no debe romper el flujo
        smtp_code = getattr(exc, "smtp_code", None)
        logger.warning(
            "Correo de extracto NO enviado (SMTP %s) host=%s:%s to=%s — el flujo continúa. detalle=%s",
            smtp_code if smtp_code is not None else "error",
            settings.host,
            settings.port,
            destinatario,
            exc,
        )
        logger.debug("Detalle del fallo SMTP", exc_info=True)
        return False
    except Exception:  # noqa: BLE001 - un fallo de envío no debe romper el flujo
        logger.exception(
            "Fallo enviando el correo de extracto host=%s:%s to=%s — el flujo continúa",
            settings.host,
            settings.port,
            destinatario,
        )
        return False


def enviar_correo_extracto_prueba(
    correo_prueba: str = "tu.correo.personal@gmail.com",
) -> bool:
    """Envía un correo de PRUEBA (datos de test) a un correo de testing.

    Pensado para validar el correo al llegar a esta parte del flujo, usando un
    correo personal de pruebas. Usa datos ficticios y sin adjunto.

    Importante: para que el correo salga de verdad debe estar MAIL_ENABLED=true
    en el .env (de lo contrario solo se renderiza y se registra en modo mock).
    """

    return enviar_correo_extracto(
        nombre_cliente="Cliente de Prueba",
        producto="Cuenta de Ahorros",
        fecha="10/06/2026",
        correo=correo_prueba,
        adjunto_base64=None,
    )


def enviar_correo_extracto_demo() -> bool:
    """Demo/mock con datos de prueba para validar el render y el flujo de envío.

    Útil para correr manualmente:
        python -m application.customer.send_emails.send_email_service

    Respeta MAIL_ENABLED / MAIL_TEST_MODE / MAIL_TEST_TO del entorno, por lo que
    por defecto solo renderiza y registra (no envía).
    """

    return enviar_correo_extracto(
        nombre_cliente="PABLO EDUARDO MOSQUERA",
        producto="Tarjeta de Crédito",
        fecha="11/05/2026",
        correo="cliente.prueba@example.com",
        adjunto_base64=base64.b64encode(b"%PDF-1.4 demo soporte").decode("ascii"),
        adjunto_filename="soporte_demo.pdf",
    )


if __name__ == "__main__":
    enviar_correo_extracto_demo()
