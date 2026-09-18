"""Traza de la ceremonia de subida de nivel, paso a paso.

Vive aparte del router porque no es lógica de transporte: es observabilidad de un
protocolo de varios pasos, y el router ya tiene 1.000 líneas.

POR QUE EXISTE
--------------
El cliente del ASO ya traza cada petición por separado: `_get`, `_post_operations`
y `_emit` cubren las once operaciones. Pero en MinIO quedaban como eventos sin
relación entre sí: se veía que hubo un `challenge_iniciar` y un `user_status`, y no
se podía reconstruir la ceremonia ni saber en qué etapa murió.

Peor: las etapas que **no** llaman al ASO —validar el `card_id`, el `personal_id`,
resolver el `account_id` en Postgres— no dejaban rastro ninguno. Y son justo donde
la ceremonia se cae más a menudo, porque dependen de datos del cliente.
"""

from __future__ import annotations

import os
import time
from typing import Any

from infrastructure.core.logger import get_logger
from infrastructure.observability.trace_audit import (
    resumen_peticion,
    schedule_trace_event,
)

logger = get_logger(__name__)


def entorno_del_aso() -> dict[str, Any]:
    """A QUÉ ASO se está llamando de verdad, no a cuál se cree.

    Replica la resolución de `TrxAsoClient` (config._resolve_aso_base_url y
    aso_client._challenge_base):

    * las consultas (`user-status`, `financial-overview`, `operations`) van a
      `ASO_BASE_URL` si está definida; si no, a `ASO_REAL_URL` con
      `ASO_SOURCE=real` o al simulador en cualquier otro caso;
    * el challenge usa `ASO_CHALLENGE_BASE_URL` SOLO con `ASO_SOURCE=real`; con
      otra fuente sigue a la base de las consultas, aunque la variable apunte al
      ASO real. Leer solo la variable daba "real" en dev cuando el reto salía al
      simulador.

    Registrarlo evita la conversación de "no veo consumos en el ASO" cuando las
    llamadas nunca salieron hacia allí.
    """

    fuente = (os.getenv("ASO_SOURCE") or "simulator").strip().casefold()
    base_manual = (os.getenv("ASO_BASE_URL") or "").strip()
    real_url = (os.getenv("ASO_REAL_URL") or os.getenv("TRX_ASO_BASE_URL") or "").strip()
    challenge_url = (os.getenv("ASO_CHALLENGE_BASE_URL") or "").strip()
    simulador_url = (
        os.getenv("ASO_SIMULATOR_URL")
        or "http://co-pqrs-back-trx-aso-simulator.pqr-genai-dev.svc.cluster.local:8050"
    ).strip()

    if base_manual:
        consultas_url = base_manual
    elif fuente == "real":
        consultas_url = real_url
    else:
        consultas_url = simulador_url
    if fuente == "real" and challenge_url:
        reto_url = challenge_url
    else:
        reto_url = consultas_url

    return {
        "aso_source": fuente,
        # `ASO_BASE_URL` gana sobre ASO_SOURCE para las consultas si está definida.
        "aso_base_url": base_manual or None,
        "aso_real_url": real_url or None,
        "aso_challenge_base_url": challenge_url or None,
        "consultas_url": consultas_url or None,
        "challenge_url": reto_url or None,
        "consultas_van_al": _destino(consultas_url, fuente),
        "challenge_va_al": _destino(reto_url, fuente),
    }


def _destino(url: str, fuente: str) -> str:
    """`real` si la URL es de la pasarela BBVA (nextgen); si no, `simulador`.

    Sin URL resuelta (variable vacía) se decide por `ASO_SOURCE`.
    """

    if url:
        return "real" if "nextgen" in url.casefold() else "simulador"
    return "real" if fuente == "real" else "simulador"


class CeremoniaDeSubidaDeNivel:
    """Registra la subida de nivel COMO UNA SECUENCIA, no como llamadas sueltas.

    Anota cada etapa con su resultado y, al terminar, un evento de resumen con la
    secuencia completa. Es lo que responde a las tres preguntas de siempre: a qué
    ASO se llamó, cómo, y dónde se rompió.

    Nunca lanza: una traza no puede tumbar una subida de nivel.
    """

    def __init__(self, *, card_id: str, personal_id: str) -> None:
        self.card_id = str(card_id or "")
        self.personal_id = str(personal_id or "")
        self.etapas: list[dict[str, Any]] = []
        self.inicio = time.perf_counter()

    # ── Datos que se pueden trazar sin exponer al cliente ──
    #
    # Nunca el card_id completo ni el documento: solo los últimos cuatro y un
    # booleano. Una traza que hay que censurar después ya nació mal.
    def _identidad(self) -> dict[str, Any]:
        return {
            "card_id_ultimos4": self.card_id[-4:] if self.card_id else None,
            "personal_id_presente": bool(self.personal_id),
        }

    def etapa(
        self,
        nombre: str,
        resultado: str,
        *,
        method: str | None = None,
        url: str | None = None,
        params: dict[str, Any] | None = None,
        peticion: dict[str, Any] | None = None,
        **detalle: Any,
    ) -> None:
        """Anota una etapa. `resultado` es `ok`, `error` u `omitida`.

        Si la etapa llama al ASO, `method`, `url` y `params` dejan en la traza la
        petición con el MISMO formato que las trazas del cliente ASO (financial
        overview): `target` = URL, y `request_summary` con method, url,
        url_completa y params.
        """

        transcurrido = round((time.perf_counter() - self.inicio) * 1000, 2)
        # `peticion` agrega datos de la llamada con el formato de las trazas del
        # ASO: la huella del TSEC (tsec_enviado, tsec_sha256...) y aso_chain_id,
        # para ver QUE token uso cada etapa y cruzarla con esos eventos.
        llamada = {**resumen_peticion(method, url, params), **(peticion or {})}
        registro = {
            "orden": len(self.etapas) + 1,
            "etapa": nombre,
            "resultado": resultado,
            "ms_desde_el_inicio": transcurrido,
            **llamada,
            **detalle,
        }
        self.etapas.append(registro)

        try:
            schedule_trace_event(
                event_type="subida_nivel",
                operation=f"subida_nivel.{nombre}",
                outcome=resultado,
                elapsed_ms=transcurrido,
                target=llamada.get("url"),
                request_summary={
                    **self._identidad(),
                    "orden": registro["orden"],
                    **llamada,
                },
                response_summary=dict(detalle),
                extra_context=entorno_del_aso(),
                tags=["trx", "subida_nivel", nombre, resultado],
            )
        except Exception:  # noqa: BLE001 - la traza nunca rompe la ceremonia
            logger.debug("no pude trazar la etapa %s", nombre)

    def cerrar(self, resultado: str, detalle: str | None = None) -> None:
        """Evento de RESUMEN con la secuencia completa.

        Es el que permite leer la ceremonia de un tirón en lugar de reconstruirla
        cruzando eventos por marca temporal, que es lo que había que hacer antes.
        """

        murio_en = next(
            (e["etapa"] for e in reversed(self.etapas) if e["resultado"] == "error"),
            None,
        )
        try:
            schedule_trace_event(
                event_type="subida_nivel",
                operation="subida_nivel.ceremonia",
                outcome=resultado,
                elapsed_ms=round((time.perf_counter() - self.inicio) * 1000, 2),
                request_summary={
                    **self._identidad(),
                    "etapas_recorridas": len(self.etapas),
                },
                response_summary={
                    "secuencia": [e["etapa"] for e in self.etapas],
                    "murio_en": murio_en,
                    "detalle": detalle,
                    "etapas": self.etapas,
                },
                extra_context=entorno_del_aso(),
                tags=["trx", "subida_nivel", "ceremonia", resultado],
            )
        except Exception:  # noqa: BLE001
            logger.debug("no pude trazar el cierre de la ceremonia")

        # También al log de stdout, porque cuando el error-handler no está
        # configurado -y en local no lo está- esta es la única huella que queda.
        logger.info(
            "subida_nivel ceremonia=%s etapas=%s murio_en=%s aso=%s",
            resultado,
            " -> ".join(e["etapa"] for e in self.etapas),
            murio_en or "-",
            entorno_del_aso()["consultas_van_al"],
        )
