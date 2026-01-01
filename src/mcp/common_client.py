from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List


class CommonClient:
    def __init__(self, server_name: str = "COMMON") -> None:
        self.server_name = server_name

    def execute_ability(self, ability: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        handler = {
            "accept_invoice_payload": self._accept_invoice_payload,
            "parse_line_items": self._parse_line_items,
            "normalize_vendor": self._normalize_vendor,
            "compute_flags": self._compute_flags,
            "compute_match_score": self._compute_match_score,
            "build_accounting_entries": self._build_accounting_entries,
            "output_final_payload": self._output_final_payload,
        }.get(ability)

        result = handler(payload) if handler else {}
        result["_meta"] = {"server": self.server_name, "ability": ability}
        return result

    def _accept_invoice_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        invoice = payload.get("invoice", payload)
        required = [
            "invoice_id",
            "vendor_name",
            "invoice_date",
            "amount",
            "currency",
        ]
        validated = all(invoice.get(field) for field in required)
        return {
            "raw_id": f"raw_{uuid.uuid4().hex[:12]}",
            "ingest_ts": datetime.now(timezone.utc).isoformat(),
            "validated": validated,
        }

    def _parse_line_items(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        line_items = payload.get("line_items") or payload.get("parsed_line_items") or []
        return {
            "parsed_line_items": line_items,
            "detected_pos": payload.get("detected_pos", []),
        }

    def _normalize_vendor(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = payload.get("vendor_name", "").strip()
        return {
            "normalized_name": " ".join(part.capitalize() for part in name.split()),
            "tax_id": payload.get("vendor_tax_id"),
        }

    def _compute_flags(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        missing: List[str] = []
        if not payload.get("vendor_tax_id"):
            missing.append("vendor_tax_id")
        if not payload.get("line_items"):
            missing.append("line_items")
        if not payload.get("amount"):
            missing.append("amount")

        risk_score = 0.1 + 0.15 * len(missing)
        return {"missing_info": missing, "risk_score": round(min(risk_score, 0.95), 2)}

    def _compute_match_score(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        invoice_amount = float(payload.get("invoice_amount") or 0)
        po_amount = float(payload.get("po_amount") or 0)
        tolerance_pct = float(payload.get("tolerance_pct") or 0)
        if po_amount == 0:
            score = 0.0
        else:
            delta = abs(invoice_amount - po_amount) / po_amount * 100
            score = max(0.0, 1.0 - (delta / max(tolerance_pct or 1.0, 1.0)))
        return {
            "match_score": round(score, 3),
            "tolerance_pct": tolerance_pct,
            "match_evidence": {
                "invoice_amount": invoice_amount,
                "po_amount": po_amount,
            },
        }

    def _build_accounting_entries(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        amount = float(payload.get("amount") or 0)
        currency = payload.get("currency") or "USD"
        return {
            "accounting_entries": [
                {
                    "type": "DEBIT",
                    "account": "Expense",
                    "amount": amount,
                    "currency": currency,
                },
                {
                    "type": "CREDIT",
                    "account": "Accounts Payable",
                    "amount": amount,
                    "currency": currency,
                },
            ]
        }

    def _output_final_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "final_payload": payload.get("final_payload", payload),
            "status": payload.get("status", "COMPLETED"),
        }
