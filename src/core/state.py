from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class LogEntry(TypedDict):
    stage: str
    action: str
    detail: Dict[str, Any]


class InvoiceState(TypedDict, total=False):
    run_id: str
    workflow_name: str
    config: Dict[str, Any]
    input_payload: Dict[str, Any]
    resume_from: str

    raw: Dict[str, Any]
    parsed: Dict[str, Any]
    vendor: Dict[str, Any]
    flags: Dict[str, Any]
    retrieved: Dict[str, Any]
    match: Dict[str, Any]
    checkpoint: Dict[str, Any]
    human: Dict[str, Any]
    reconcile: Dict[str, Any]
    approval: Dict[str, Any]
    posting: Dict[str, Any]
    notify: Dict[str, Any]
    final: Dict[str, Any]

    status: str
    logs: List[LogEntry]
