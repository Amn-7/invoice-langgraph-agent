from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.core.config import load_settings
from src.db import list_final_results, list_pending_reviews, save_human_decision
from src.core.workflow import WorkflowRunner


class DecisionRequest(BaseModel):
    checkpoint_id: str = Field(..., min_length=1)
    decision: str = Field(..., min_length=1)
    notes: str = ""
    reviewer_id: str = Field(..., min_length=1)


class DecisionResponse(BaseModel):
    resume_token: str
    next_stage: str
    workflow_status: Optional[str] = None


class InvoiceSubmitResponse(BaseModel):
    status: str
    run_id: str
    checkpoint: Optional[Dict[str, Any]] = None
    final: Optional[Dict[str, Any]] = None
    match: Optional[Dict[str, Any]] = None


settings = load_settings()
runner = WorkflowRunner(settings)
app = FastAPI(title="Invoice HITL Review API")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/human-review/pending")
async def list_pending() -> Dict[str, Any]:
    items = list_pending_reviews(settings.env.get("DB_CONN", "sqlite:///./data/demo.db"))
    return {"items": items}


@app.post("/human-review/decision", response_model=DecisionResponse)
async def record_decision(request: DecisionRequest) -> DecisionResponse:
    decision = request.decision.strip().upper()
    if decision not in {"ACCEPT", "REJECT"}:
        raise HTTPException(status_code=400, detail="decision must be ACCEPT or REJECT")

    resume_token, next_stage = save_human_decision(
        settings.env.get("DB_CONN", "sqlite:///./data/demo.db"),
        request.checkpoint_id,
        decision,
        request.notes,
        request.reviewer_id,
    )

    workflow_status: Optional[str] = None
    try:
        state = runner.resume_from_checkpoint(request.checkpoint_id)
        workflow_status = state.get("status")
    except Exception:
        workflow_status = None

    return DecisionResponse(
        resume_token=resume_token,
        next_stage=next_stage,
        workflow_status=workflow_status,
    )


@app.post("/invoice/submit", response_model=InvoiceSubmitResponse)
async def submit_invoice(payload: Dict[str, Any] = Body(...)) -> InvoiceSubmitResponse:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invoice payload must be a JSON object.")

    required = ["invoice_id", "vendor_name", "invoice_date", "amount", "currency"]
    missing = [field for field in required if not payload.get(field)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required fields: {', '.join(missing)}",
        )

    state = runner.run(payload)
    return InvoiceSubmitResponse(
        status=state.get("status", "UNKNOWN"),
        run_id=state.get("run_id", ""),
        checkpoint=state.get("checkpoint"),
        final=state.get("final"),
        match=state.get("match"),
    )


@app.get("/human-review/decision")
async def decision_help() -> Dict[str, Any]:
    return {
        "detail": "This endpoint expects POST with JSON body.",
        "example": {
            "checkpoint_id": "chk_123",
            "decision": "ACCEPT",
            "notes": "ok",
            "reviewer_id": "reviewer_1",
        },
    }


@app.get("/final-results")
async def get_final_results(limit: int = 20) -> Dict[str, Any]:
    items = list_final_results(settings.env.get("DB_CONN", "sqlite:///./data/demo.db"), limit=limit)
    return {"items": items}
