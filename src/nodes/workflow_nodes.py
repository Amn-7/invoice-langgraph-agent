from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from src.core.config import Settings
from src.db import (
    get_checkpoint_status,
    load_checkpoint,
    save_checkpoint,
    save_final_result,
    save_human_decision,
    save_raw_invoice,
)
from src.mcp import McpRouter
from src.core.state import InvoiceState, LogEntry
from src.tools import BigtoolPicker, ToolSelection


@dataclass
class NodeDeps:
    settings: Settings
    router: McpRouter
    bigtool: BigtoolPicker
    db_conn: str
    app_url: str
    ability_map: Dict[str, str]


def _append_log(
    logs_or_state: Union[InvoiceState, List[LogEntry]],
    stage: str,
    action: str,
    detail: Dict[str, Any],
) -> List[LogEntry]:
    if isinstance(logs_or_state, dict):
        logs = list(logs_or_state.get("logs", []))
    else:
        logs = list(logs_or_state)
    logs.append({"stage": stage, "action": action, "detail": detail})
    return logs


def _tool_log(selection: ToolSelection) -> Dict[str, Any]:
    return {
        "capability": selection.capability,
        "tool": selection.tool,
        "pool": selection.pool,
        "reason": selection.reason,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "invoice_id": payload.get("invoice_id"),
        "vendor_name": payload.get("vendor_name"),
        "amount": payload.get("amount"),
    }


def _get_first_amount(items: List[Dict[str, Any]]) -> Optional[float]:
    if not items:
        return None
    amount = items[0].get("amount")
    if amount is None:
        return None
    try:
        return float(amount)
    except (TypeError, ValueError):
        return None


def _merge_notify_results(*results: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    status: Dict[str, Any] = {}
    parties: List[str] = []
    for result in results:
        status.update(result.get("notify_status", {}))
        parties.extend(result.get("notified_parties", []))
    return status, parties


class InvoiceNodes:
    def __init__(self, deps: NodeDeps) -> None:
        self.deps = deps

    def _server_for(self, ability: str, default: str) -> str:
        return self.deps.ability_map.get(ability, default)

    def intake(self, state: InvoiceState) -> InvoiceState:
        payload = state.get("input_payload", {})
        selection = self.deps.bigtool.select(
            "storage", context=_extract_context(payload), pool_hint=["s3", "gcs", "local_fs"]
        )
        result = self.deps.router.execute(
            self._server_for("accept_invoice_payload", "COMMON"),
            "accept_invoice_payload",
            {"invoice": payload},
        )
        raw_id = result.get("raw_id")
        if raw_id:
            save_raw_invoice(self.deps.db_conn, raw_id, payload)

        logs = _append_log(state, "INTAKE", "bigtool.select", _tool_log(selection))
        logs = _append_log(logs, "INTAKE", "ability", result)
        if raw_id:
            logs = _append_log(
                logs,
                "INTAKE",
                "persist_raw",
                {"raw_id": raw_id, "stored": True},
            )

        return {
            "raw": result,
            "status": "INGESTED",
            "logs": logs,
        }

    def understand(self, state: InvoiceState) -> InvoiceState:
        payload = state.get("input_payload", {})
        selection = self.deps.bigtool.select(
            "ocr",
            context=_extract_context(payload),
            pool_hint=["google_vision", "tesseract", "aws_textract"],
        )
        ocr_result = self.deps.router.execute(
            self._server_for("ocr_extract", "ATLAS"),
            "ocr_extract",
            {
                "attachments": payload.get("attachments", []),
                "currency": payload.get("currency"),
            },
        )
        parse_result = self.deps.router.execute(
            self._server_for("parse_line_items", "COMMON"),
            "parse_line_items",
            {"line_items": payload.get("line_items", [])},
        )

        parsed_invoice = {
            "invoice_text": ocr_result.get("invoice_text"),
            "parsed_line_items": parse_result.get("parsed_line_items", []),
            "detected_pos": parse_result.get("detected_pos", []),
            "currency": ocr_result.get("currency") or payload.get("currency"),
            "parsed_dates": {
                "invoice_date": payload.get("invoice_date"),
                "due_date": payload.get("due_date"),
            },
        }

        logs = _append_log(state, "UNDERSTAND", "bigtool.select", _tool_log(selection))
        logs = _append_log(logs, "UNDERSTAND", "ability", ocr_result)
        logs = _append_log(logs, "UNDERSTAND", "ability", parse_result)

        return {
            "parsed": parsed_invoice,
            "status": "UNDERSTOOD",
            "logs": logs,
        }

    def prepare(self, state: InvoiceState) -> InvoiceState:
        payload = state.get("input_payload", {})
        selection = self.deps.bigtool.select(
            "enrichment",
            context=_extract_context(payload),
            pool_hint=["clearbit", "people_data_labs", "vendor_db"],
        )
        normalized = self.deps.router.execute(
            self._server_for("normalize_vendor", "COMMON"),
            "normalize_vendor",
            {
                "vendor_name": payload.get("vendor_name"),
                "vendor_tax_id": payload.get("vendor_tax_id"),
            },
        )
        enriched = self.deps.router.execute(
            self._server_for("enrich_vendor", "ATLAS"),
            "enrich_vendor",
            {
                "vendor_name": payload.get("vendor_name"),
            },
        )
        flags = self.deps.router.execute(
            self._server_for("compute_flags", "COMMON"),
            "compute_flags",
            {
                "vendor_tax_id": payload.get("vendor_tax_id"),
                "line_items": payload.get("line_items", []),
                "amount": payload.get("amount"),
            },
        )

        vendor_profile = {
            "normalized_name": normalized.get("normalized_name"),
            "tax_id": normalized.get("tax_id"),
            "enrichment_meta": enriched,
        }
        normalized_invoice = {
            "amount": payload.get("amount"),
            "currency": payload.get("currency"),
            "line_items": payload.get("line_items", []),
        }

        logs = _append_log(state, "PREPARE", "bigtool.select", _tool_log(selection))
        logs = _append_log(logs, "PREPARE", "ability", normalized)
        logs = _append_log(logs, "PREPARE", "ability", enriched)
        logs = _append_log(logs, "PREPARE", "ability", flags)

        return {
            "vendor": vendor_profile,
            "flags": flags,
            "parsed": {**state.get("parsed", {}), "normalized_invoice": normalized_invoice},
            "status": "PREPARED",
            "logs": logs,
        }

    def retrieve(self, state: InvoiceState) -> InvoiceState:
        payload = state.get("input_payload", {})
        selection = self.deps.bigtool.select(
            "erp_connector",
            context=_extract_context(payload),
            pool_hint=["sap_sandbox", "netsuite", "mock_erp"],
        )
        po_payload = {
            "amount": payload.get("amount"),
            "currency": payload.get("currency"),
        }
        if "po_amount" in payload:
            po_payload["po_amount"] = payload.get("po_amount")
        if payload.get("force_mismatch"):
            po_payload["force_mismatch"] = True
        po_result = self.deps.router.execute(
            self._server_for("fetch_po", "ATLAS"),
            "fetch_po",
            po_payload,
        )
        grn_result = self.deps.router.execute(
            self._server_for("fetch_grn", "ATLAS"),
            "fetch_grn",
            {},
        )
        history_result = self.deps.router.execute(
            self._server_for("fetch_history", "ATLAS"),
            "fetch_history",
            {"amount": payload.get("amount")},
        )

        retrieved = {
            "matched_pos": po_result.get("matched_pos", []),
            "matched_grns": grn_result.get("matched_grns", []),
            "history": history_result.get("history", []),
        }

        logs = _append_log(state, "RETRIEVE", "bigtool.select", _tool_log(selection))
        logs = _append_log(logs, "RETRIEVE", "ability", po_result)
        logs = _append_log(logs, "RETRIEVE", "ability", grn_result)
        logs = _append_log(logs, "RETRIEVE", "ability", history_result)

        return {"retrieved": retrieved, "status": "RETRIEVED", "logs": logs}

    def match_two_way(self, state: InvoiceState) -> InvoiceState:
        payload = state.get("input_payload", {})
        retrieved = state.get("retrieved", {})
        po_amount = _get_first_amount(retrieved.get("matched_pos", []))
        invoice_amount = payload.get("amount")
        tolerance = float(self.deps.settings.workflow.get("config", {}).get("two_way_tolerance_pct", 5))

        result = self.deps.router.execute(
            self._server_for("compute_match_score", "COMMON"),
            "compute_match_score",
            {
                "invoice_amount": invoice_amount,
                "po_amount": po_amount,
                "tolerance_pct": tolerance,
            },
        )
        threshold = float(self.deps.settings.workflow.get("config", {}).get("match_threshold", 0.9))
        match_score = float(result.get("match_score") or 0)
        match_result = "MATCHED" if match_score >= threshold else "FAILED"

        match = {
            **result,
            "match_result": match_result,
        }

        logs = _append_log(state, "MATCH_TWO_WAY", "ability", result)

        return {"match": match, "status": "MATCHED" if match_result == "MATCHED" else "MISMATCH", "logs": logs}

    def checkpoint_hitl(self, state: InvoiceState) -> InvoiceState:
        match = state.get("match", {})
        if match.get("match_result") != "FAILED":
            return {"status": state.get("status", ""), "logs": state.get("logs", [])}

        payload = state.get("input_payload", {})
        selection = self.deps.bigtool.select(
            "db",
            context=_extract_context(payload),
            pool_hint=["postgres", "sqlite", "dynamodb"],
        )

        review_url = f"{self.deps.app_url.rstrip('/')}/human-review/pending"
        checkpoint_id = f"chk_{uuid.uuid4().hex[:12]}"
        checkpoint = {
            "checkpoint_id": checkpoint_id,
            "review_url": review_url,
            "paused_reason": "2-way match failed",
        }
        checkpoint_state = {**state, "checkpoint": checkpoint, "status": "PAUSED"}
        save_checkpoint(
            self.deps.db_conn,
            checkpoint_state,
            reason="2-way match failed",
            review_url=review_url,
            invoice_id=payload.get("invoice_id"),
            vendor_name=payload.get("vendor_name"),
            amount=payload.get("amount"),
            checkpoint_id=checkpoint_id,
        )

        logs = _append_log(state, "CHECKPOINT_HITL", "bigtool.select", _tool_log(selection))
        logs = _append_log(logs, "CHECKPOINT_HITL", "checkpoint", checkpoint)

        return {
            "checkpoint": checkpoint,
            "status": "PAUSED",
            "logs": logs,
        }

    def hitl_decision(self, state: InvoiceState, checkpoint_id: Optional[str] = None) -> InvoiceState:
        checkpoint_id = checkpoint_id or state.get("checkpoint", {}).get("checkpoint_id")
        if not checkpoint_id:
            return {
                "human": {"human_decision": "UNKNOWN", "next_stage": "MANUAL_HANDOFF"},
                "status": "REQUIRES_MANUAL_HANDLING",
            }

        status = get_checkpoint_status(self.deps.db_conn, checkpoint_id)
        decision = status.get("decision")
        if not decision:
            return {
                "human": {
                    "human_decision": "PENDING",
                    "next_stage": "WAITING",
                },
                "status": "WAITING_HUMAN",
            }

        if decision == "ACCEPT":
            next_stage = "RECONCILE"
            status_value = "RESUME_RECONCILE"
        elif decision == "REJECT":
            next_stage = "MANUAL_HANDOFF"
            status_value = "REQUIRES_MANUAL_HANDLING"
        else:
            next_stage = "WAITING"
            status_value = "WAITING_HUMAN"

        human = {
            "human_decision": decision,
            "reviewer_id": status.get("reviewer_id"),
            "resume_token": status.get("resume_token"),
            "next_stage": next_stage,
        }
        logs = _append_log(state, "HITL_DECISION", "decision", human)
        return {"human": human, "status": status_value, "logs": logs}

    def reconcile(self, state: InvoiceState) -> InvoiceState:
        payload = state.get("input_payload", {})
        result = self.deps.router.execute(
            self._server_for("build_accounting_entries", "COMMON"),
            "build_accounting_entries",
            {"amount": payload.get("amount"), "currency": payload.get("currency")},
        )

        report = {
            "reconciled_at": _utc_now(),
            "entries": result.get("accounting_entries", []),
        }

        logs = _append_log(state, "RECONCILE", "ability", result)

        return {
            "reconcile": {
                "accounting_entries": result.get("accounting_entries", []),
                "reconciliation_report": report,
            },
            "status": "RECONCILED",
            "logs": logs,
        }

    def approve(self, state: InvoiceState) -> InvoiceState:
        payload = state.get("input_payload", {})
        result = self.deps.router.execute(
            self._server_for("apply_invoice_approval_policy", "ATLAS"),
            "apply_invoice_approval_policy",
            {"amount": payload.get("amount")},
        )

        logs = _append_log(state, "APPROVE", "ability", result)

        return {"approval": result, "status": "APPROVED", "logs": logs}

    def posting(self, state: InvoiceState) -> InvoiceState:
        payload = state.get("input_payload", {})
        selection = self.deps.bigtool.select(
            "erp_connector",
            context=_extract_context(payload),
            pool_hint=["sap_sandbox", "netsuite", "mock_erp"],
        )
        post_result = self.deps.router.execute(
            self._server_for("post_to_erp", "ATLAS"),
            "post_to_erp",
            {},
        )
        payment_result = self.deps.router.execute(
            self._server_for("schedule_payment", "ATLAS"),
            "schedule_payment",
            {"due_date": payload.get("due_date")},
        )

        posting = {
            "posted": post_result.get("posted", False),
            "erp_txn_id": post_result.get("erp_txn_id"),
            "scheduled_payment_id": payment_result.get("scheduled_payment_id"),
        }

        logs = _append_log(state, "POSTING", "bigtool.select", _tool_log(selection))
        logs = _append_log(logs, "POSTING", "ability", post_result)
        logs = _append_log(logs, "POSTING", "ability", payment_result)

        return {"posting": posting, "status": "POSTED", "logs": logs}

    def notify(self, state: InvoiceState) -> InvoiceState:
        payload = state.get("input_payload", {})
        selection = self.deps.bigtool.select(
            "email",
            context=_extract_context(payload),
            pool_hint=["sendgrid", "smartlead", "ses"],
        )
        vendor_result = self.deps.router.execute(
            self._server_for("notify_vendor", "ATLAS"),
            "notify_vendor",
            {"vendor_name": payload.get("vendor_name")},
        )
        finance_result = self.deps.router.execute(
            self._server_for("notify_finance_team", "ATLAS"),
            "notify_finance_team",
            {},
        )
        notify_status, notified_parties = _merge_notify_results(
            vendor_result, finance_result
        )

        notify = {
            "notify_status": notify_status,
            "notified_parties": notified_parties,
        }

        logs = _append_log(state, "NOTIFY", "bigtool.select", _tool_log(selection))
        logs = _append_log(logs, "NOTIFY", "ability", vendor_result)
        logs = _append_log(logs, "NOTIFY", "ability", finance_result)

        return {"notify": notify, "status": "NOTIFIED", "logs": logs}

    def complete(self, state: InvoiceState) -> InvoiceState:
        payload = state.get("input_payload", {})
        selection = self.deps.bigtool.select(
            "db",
            context=_extract_context(payload),
            pool_hint=["postgres", "sqlite", "dynamodb"],
        )
        final_status = "COMPLETED"
        if state.get("status") == "REQUIRES_MANUAL_HANDLING" or state.get("human", {}).get(
            "human_decision"
        ) == "REJECT":
            final_status = "REQUIRES_MANUAL_HANDLING"
        final_payload = {
            "invoice_id": payload.get("invoice_id"),
            "vendor_name": payload.get("vendor_name"),
            "amount": payload.get("amount"),
            "currency": payload.get("currency"),
            "status": final_status,
            "match": state.get("match"),
            "approval": state.get("approval"),
            "posting": state.get("posting"),
        }
        result = self.deps.router.execute(
            self._server_for("output_final_payload", "COMMON"),
            "output_final_payload",
            {"final_payload": final_payload, "status": final_status},
        )
        final_payload_result = result.get("final_payload", final_payload)
        run_id = state.get("run_id")
        if run_id:
            save_final_result(
                self.deps.db_conn,
                run_id,
                payload,
                final_status,
                final_payload_result,
            )

        audit_log = list(state.get("logs", []))

        logs = _append_log(state, "COMPLETE", "bigtool.select", _tool_log(selection))
        logs = _append_log(logs, "COMPLETE", "ability", result)
        if run_id:
            logs = _append_log(
                logs,
                "COMPLETE",
                "persist_final",
                {"run_id": run_id, "stored": True},
            )

        return {
            "final": {
                "final_payload": final_payload_result,
                "audit_log": audit_log,
                "status": final_status,
            },
            "status": final_status,
            "logs": logs,
        }

    def apply_human_decision(
        self,
        checkpoint_id: str,
        decision: str,
        notes: str,
        reviewer_id: str,
    ) -> Dict[str, Any]:
        resume_token, next_stage = save_human_decision(
            self.deps.db_conn,
            checkpoint_id,
            decision,
            notes,
            reviewer_id,
        )
        return {
            "resume_token": resume_token,
            "next_stage": next_stage,
        }

    def load_checkpoint_state(self, checkpoint_id: str) -> InvoiceState:
        return load_checkpoint(self.deps.db_conn, checkpoint_id)
