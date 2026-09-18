"""OpenSearch client for client-control updates."""

import time
from datetime import date, datetime, timezone
from typing import Any

import httpx

from infrastructure.core.config import (
    OpenSearchSettings,
    load_env_constants,
    load_opensearch_settings,
)
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.observability.trace_audit import schedule_trace_event

logger = get_logger(__name__)


class OpenSearchClient:
    """Persist generated data into an existing OpenSearch document."""

    def __init__(self, settings: OpenSearchSettings | None = None) -> None:
        self.settings = settings or load_opensearch_settings()
        constants = load_env_constants()
        self.enabled = _parse_bool_env(
            constants.get("OPENSEARCH_ENABLED"),
            default=True,
        )

    @log_execution
    async def update_client_control_data(
        self,
        *,
        customer_id: str,
        workflow: str,
        data: dict[str, Any] | None = None,
        status: str = "ok",
        run_id: str | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        """Write the workflow back-data envelope (status + run_id + data|error).

        Stores an envelope under ``monthly[YYYY-MM].workflows[<wf>]`` so the
        agent can tell a FRESH SUCCESSFUL result apart from an error/stale one:
          - back_data_status:    ok | error
          - back_data_run_id:    correlation id of the triggering request
          - back_data_updated_at: ISO timestamp
          - data:                present only when status == ok
          - back_data_error:     present only when status == error
        """

        if not self.enabled:
            logger.info(
                "Skipping OpenSearch update because OPENSEARCH_ENABLED=false "
                "customer_id=%s workflow=%s status=%s",
                customer_id,
                workflow,
                status,
            )
            return

        url = (
            f"{self.settings.base_url}/"
            f"{self.settings.control_index}/_update/"
            f"{customer_id}"
        )

        is_ok = status == "ok"
        # C2: mes destino unico. El agente lee el mes en curso, calculado con la
        # misma regla (``%Y-%m``), asi que este es el unico destino que puede
        # encontrar.
        target_period = date.today().strftime("%Y-%m")
        fields: dict[str, Any] = {
            "back_data_status": status,
            "back_data_run_id": run_id,
            "back_data_updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if is_ok:
            fields["data"] = data or {}
            fields["back_data_error"] = None
        else:
            # On failure we intentionally DO NOT write `data` and remove any
            # stale `data` so the agent never serves an old "no reports" result.
            fields["back_data_error"] = error or {}

        payload = {
            # C4 REVERTIDO (02/09, tras el despliegue): se habia anadido
            # ``scripted_upsert``+``upsert`` para tolerar un documento
            # inexistente. En produccion eso hizo que OpenSearch devolviera
            # 400 Bad Request en TODAS las escrituras (verificado: antes del
            # despliegue outcome=ok, despues outcome=error con el mismo
            # cliente e indice). El caso que pretendia cubrir -documento
            # borrado por el TTL de 30 dias- era una hipotesis nunca
            # observada; el 400 era real y rompia el camino que funcionaba.
            # Si vuelve a hacer falta, hay que probarlo antes contra un
            # OpenSearch de la MISMA version que produccion.
            "script": {
                "lang": "painless",
                "source": """
                    ctx._source.remove('data');

                    if (ctx._source.monthly == null) {
                        ctx._source.monthly = [:];
                    }

                    // C2 (02/09): el sobre se escribe SIEMPRE en el mes en curso.
                    //
                    // Antes se recorrian los meses del registro y se actualizaba
                    // el primero que ya contuviera el workflow -sin break, o sea
                    // TODOS los que casaran-; si no habia ninguno, se usaba el mes
                    // de ``last_interaction_at``. El agente, en cambio, lee el mes
                    // en curso.
                    //
                    // CONFIRMADO en produccion el 02/09 con el diagnostico de la
                    // traza de timeout: el registro del cliente tenia los meses
                    // 2026-07 y 2026-08 con el sobre (updated_at de ESE dia) y NO
                    // tenia 2026-09, que es el que el agente consultaba. De ahi el
                    // "En este momento no puedo validar el estado de tus
                    // productos".
                    def period = params.default_period;

                    if (!ctx._source.monthly.containsKey(period)) {
                        ctx._source.monthly[period] = [:];
                    }

                    if (ctx._source.monthly[period].workflows == null) {
                        ctx._source.monthly[period].workflows = [:];
                    }

                    if (!ctx._source.monthly[period].workflows.containsKey(params.workflow)) {
                        ctx._source.monthly[period].workflows[params.workflow] = [:];
                    }

                    def wf = ctx._source.monthly[period].workflows[params.workflow];
                    for (entry in params.fields.entrySet()) {
                        wf[entry.getKey()] = entry.getValue();
                    }
                    if (params.remove_data) { wf.remove('data'); }
                """,
                "params": {
                    "workflow": workflow,
                    "fields": fields,
                    "remove_data": not is_ok,
                    "default_period": target_period,
                },
            }
        }

        logger.info(
            "Updating OpenSearch workflow envelope index=%s doc_id=%s workflow=%s status=%s run_id=%s url=%s",
            self.settings.control_index,
            customer_id,
            workflow,
            status,
            run_id,
            url,
        )

        schedule_trace_event(
            event_type="opensearch",
            operation="update_client_control_data",
            outcome="started",
            target=self.settings.control_index,
            customer_id=customer_id,
            request_summary={
                "workflow": workflow,
                "index": self.settings.control_index,
                "status": status,
                "run_id": run_id,
                # F0b (02/09): el mes destino en la traza. Sin esto no se podia
                # saber si el sobre habia caido en el mes que el agente lee.
                "mes_destino": target_period,
            },
            tags=["opensearch", "control_table"],
        )
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                verify=self.settings.verify_ssl,
                timeout=self.settings.timeout,
                auth=(self.settings.user, self.settings.password),
            ) as client:
                response = await client.post(url, json=payload)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            if response.is_error:
                logger.error(
                    "OpenSearch update failed status=%s body=%s",
                    response.status_code,
                    response.text,
                )
                response.raise_for_status()
            schedule_trace_event(
                event_type="opensearch",
                operation="update_client_control_data",
                outcome="ok",
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
                target=self.settings.control_index,
                customer_id=customer_id,
                request_summary={
                    "workflow": workflow,
                    "mes_destino": target_period,
                },
                tags=["opensearch", "control_table"],
            )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            # El cuerpo de la respuesta va A LA TRAZA, no solo al log del pod.
            # Leccion del 02/09: un 400 de OpenSearch dejo la traza con
            # ``response_summary`` vacio y el motivo real -que estaba en el
            # cuerpo- solo quedo en el log del contenedor, al que no siempre
            # hay acceso. Truncado a 600 caracteres; el cuerpo de error de
            # OpenSearch describe la causa en los primeros.
            cuerpo_error: dict[str, Any] = {}
            respuesta_del_error = getattr(exc, "response", None)
            if respuesta_del_error is not None:
                try:
                    cuerpo_error = {
                        "status_code": respuesta_del_error.status_code,
                        "body": str(respuesta_del_error.text)[:600],
                    }
                except Exception:  # pragma: no cover - la traza nunca rompe
                    cuerpo_error = {}
            schedule_trace_event(
                event_type="opensearch",
                operation="update_client_control_data",
                outcome="error",
                status_code=cuerpo_error.get("status_code"),
                elapsed_ms=elapsed_ms,
                target=self.settings.control_index,
                customer_id=customer_id,
                request_summary={
                    "workflow": workflow,
                    "mes_destino": target_period,
                },
                response_summary=cuerpo_error,
                error_type=type(exc).__name__,
                error_message=str(exc),
                tags=["opensearch", "control_table"],
            )
            raise


def _parse_bool_env(value: str | None, *, default: bool) -> bool:
    """Parse boolean-like values from environment variables."""

    if value is None:
        return default
    normalized = value.strip().casefold()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}
