"""Resolver de escenarios para el simulador de ASOs de TXNR.

Carga respuestas JSON por llave (customer_id / card_id / documentNumber) desde el
directorio `data/`, con fallback determinístico. Sin estado global mutable: cada
petición lee del disco, por lo que es seguro para múltiples usuarios en paralelo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TrxAsoResolver:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    # --- utilidades -------------------------------------------------------
    def _read(self, *parts: str) -> dict[str, Any] | None:
        path = self.data_dir.joinpath(*parts)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)

    @staticmethod
    def _doc_number_from_target(target_user_id: str) -> str:
        """`01-1013634958` -> `1013634958` (parte tras el guion)."""
        raw = (target_user_id or "").strip()
        if "-" in raw:
            return raw.split("-", 1)[1].strip()
        return raw

    # --- ASOs -------------------------------------------------------------
    def salesforce_issues(self, target_user_id: str) -> dict[str, Any]:
        doc = self._doc_number_from_target(target_user_id)
        payload = self._read("salesforce", f"{doc}.json")
        if payload is None:
            return {"data": []}
        return payload

    def financial_overview(self, customer_id: str) -> dict[str, Any]:
        payload = self._read("financial_overview", f"{customer_id}.json")
        if payload is None:
            return {"data": {"contracts": []}}
        return payload

    def financial_overview_by_contract(
        self,
        *,
        contract_id: str,
        customer_id: str = "",
    ) -> dict[str, Any]:
        """Return financial-overview payload that contains the requested contract.

        Keeps backward response shape by returning the full ASO payload file where
        the contract exists, instead of building a synthetic filtered response.
        """

        expected = str(contract_id or "").strip()
        if not expected:
            return {"data": {"contracts": []}}

        normalized_customer = str(customer_id or "").strip()

        if normalized_customer:
            payload = self._read("financial_overview", f"{normalized_customer}.json")
            if isinstance(payload, dict):
                contracts = ((payload.get("data") or {}).get("contracts") or [])
                for contract in contracts:
                    if str((contract or {}).get("id", "")).strip() == expected:
                        return payload

        folder = self.data_dir / "financial_overview"
        if not folder.exists() or not folder.is_dir():
            return {"data": {"contracts": []}}

        for file_path in folder.glob("*.json"):
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            contracts = ((payload or {}).get("data", {}) or {}).get("contracts", [])
            if not isinstance(contracts, list):
                continue

            for contract in contracts:
                if str((contract or {}).get("id", "")).strip() == expected:
                    return payload

        return {"data": {"contracts": []}}

    def transactions(self, card_id: str) -> dict[str, Any]:
        payload = self._read("transactions", f"{card_id}.json")
        if payload is None:
            return {"data": [], "pagination": {"page": 0, "totalPages": 1, "totalElements": 0}}
        return payload

    def operations(self, card_id: str) -> dict[str, Any]:
        payload = self._read("operations", f"{card_id}.json")
        if payload is None:
            return {"data": [], "pagination": {"page": 1, "totalPages": 1, "totalElements": 0}}
        return payload

    def block_should_fail(self, card_id: str) -> bool:
        """Tarjetas cuyo bloqueo (temporal/permanente) simula fallo (no-200)."""
        fails = self._read("block_failures.json") or {"card_ids": []}
        return str(card_id) in {str(c) for c in fails.get("card_ids", [])}

    def notification_should_accept(self, card_id: str) -> bool:
        """Tarjetas que rechazan autorizacion de notificacion (200 con accepted=false)."""
        denied = self._read("notification_denied.json") or {"card_ids": []}
        denied_ids = {str(c) for c in denied.get("card_ids", [])}
        return str(card_id) not in denied_ids
