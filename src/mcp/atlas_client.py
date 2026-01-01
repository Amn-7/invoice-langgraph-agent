from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List


class AtlasClient:
    def __init__(self, server_name: str = "ATLAS") -> None:
        self.server_name = server_name

    def execute_ability(self, ability: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        handler = {
            "ocr_extract": self._ocr_extract,
            "enrich_vendor": self._enrich_vendor,
            "fetch_po": self._fetch_po,
            "fetch_grn": self._fetch_grn,
            "fetch_history": self._fetch_history,
            "apply_invoice_approval_policy": self._apply_invoice_approval_policy,
            "post_to_erp": self._post_to_erp,
            "schedule_payment": self._schedule_payment,
            "notify_vendor": self._notify_vendor,
            "notify_finance_team": self._notify_finance_team,
        }.get(ability)

        result = handler(payload) if handler else {}
        result["_meta"] = {"server": self.server_name, "ability": ability}
        return result

    def _ocr_extract(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        attachments = payload.get("attachments") or []
        text = " ".join(f"OCR({name})" for name in attachments) or "OCR(NO_ATTACHMENTS)"
        return {
            "invoice_text": text,
            "currency": payload.get("currency", "USD"),
        }

    def _enrich_vendor(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = payload.get("vendor_name") or "Unknown Vendor"
        return {
            "vendor_name": name,
            "credit_score": 0.72,
            "risk_score": 0.28,
            "enrichment_ts": datetime.now(timezone.utc).isoformat(),
        }

    def _fetch_po(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        amount = float(payload.get("amount") or 0)
        po_amount = payload.get("po_amount")
        if po_amount is None and payload.get("force_mismatch"):
            po_amount = amount * 0.7
        if po_amount is None:
            po_amount = amount
        try:
            po_amount = float(po_amount)
        except (TypeError, ValueError):
            po_amount = amount
        return {
            "matched_pos": [
                {
                    "po_id": f"PO-{uuid.uuid4().hex[:6].upper()}",
                    "amount": po_amount,
                    "currency": payload.get("currency", "USD"),
                }
            ]
        }

    def _fetch_grn(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "matched_grns": [
                {
                    "grn_id": f"GRN-{uuid.uuid4().hex[:6].upper()}",
                    "status": "RECEIVED",
                }
            ]
        }

    def _fetch_history(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "history": [
                {
                    "invoice_id": f"HIST-{uuid.uuid4().hex[:6].upper()}",
                    "amount": payload.get("amount"),
                    "status": "PAID",
                }
            ]
        }

    def _apply_invoice_approval_policy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        amount = float(payload.get("amount") or 0)
        if amount <= 10000:
            return {"approval_status": "APPROVED", "approver_id": "AUTO"}
        return {"approval_status": "ESCALATED", "approver_id": "FINANCE_LEAD"}

    def _post_to_erp(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "posted": True,
            "erp_txn_id": f"ERP-{uuid.uuid4().hex[:8].upper()}",
        }

    def _schedule_payment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "scheduled_payment_id": f"PAY-{uuid.uuid4().hex[:8].upper()}",
            "scheduled_for": payload.get("due_date"),
        }

    def _notify_vendor(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "notify_status": {"vendor": "SENT"},
            "notified_parties": [payload.get("vendor_name", "vendor")],
        }

    def _notify_finance_team(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "notify_status": {"finance_team": "SENT"},
            "notified_parties": ["finance_team"],
        }
