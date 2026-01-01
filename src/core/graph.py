from __future__ import annotations

import re
import uuid
from typing import Any, Dict, Optional

from langgraph.graph import END, START, StateGraph

from src.core.config import Settings
from src.db import SQLiteSaver
from src.mcp import McpRouter
from src.nodes import InvoiceNodes, NodeDeps
from src.core.state import InvoiceState
from src.tools import BigtoolPicker

def build_deps(settings: Settings) -> NodeDeps:
    db_conn = settings.env.get("DB_CONN", "sqlite:///./data/demo.db")
    app_url = settings.env.get("APP_URL", "http://localhost:8000")
    router = McpRouter()
    bigtool = BigtoolPicker(settings.tool_pools)
    ability_map = settings.workflow.get("ability_map", {})
    return NodeDeps(
        settings=settings,
        router=router,
        bigtool=bigtool,
        db_conn=db_conn,
        app_url=app_url,
        ability_map=ability_map,
    )


def _deep_get(data: Dict[str, Any], path: str) -> Optional[Any]:
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _resolve_path(state: InvoiceState, path: str) -> Optional[Any]:
    normalized = path
    if normalized.startswith("input_state."):
        normalized = normalized[len("input_state.") :]
    value = _deep_get(state, normalized)
    if value is None and normalized == "match_result":
        value = state.get("match", {}).get("match_result")
    return value


def _evaluate_trigger(expr: Optional[str], state: InvoiceState) -> bool:
    if not expr:
        return False
    match = re.match(r"^\\s*([\\w\\.]+)\\s*(==|!=)\\s*(['\"])(.*?)\\3\\s*$", expr)
    if not match:
        return False
    path, op, _, literal = match.groups()
    value = _resolve_path(state, path)
    if value is None:
        return False
    if op == "==":
        return str(value) == literal
    if op == "!=":
        return str(value) != literal
    return False


def hitl_router(state: InvoiceState) -> str:
    decision = state.get("human", {}).get("human_decision")
    if decision == "ACCEPT":
        return "RECONCILE"
    if decision == "REJECT":
        return "COMPLETE"
    return END


def build_graph(
    settings: Settings,
    checkpointer: SQLiteSaver | None = None,
):
    deps = build_deps(settings)
    nodes = InvoiceNodes(deps)

    builder = StateGraph(InvoiceState)
    stage_handlers = {
        "INTAKE": nodes.intake,
        "UNDERSTAND": nodes.understand,
        "PREPARE": nodes.prepare,
        "RETRIEVE": nodes.retrieve,
        "MATCH_TWO_WAY": nodes.match_two_way,
        "CHECKPOINT_HITL": nodes.checkpoint_hitl,
        "HITL_DECISION": nodes.hitl_decision,
        "RECONCILE": nodes.reconcile,
        "APPROVE": nodes.approve,
        "POSTING": nodes.posting,
        "NOTIFY": nodes.notify,
        "COMPLETE": nodes.complete,
    }

    stages = settings.workflow.get("stages", [])
    stage_by_id = {stage.get("id"): stage for stage in stages if stage.get("id")}
    stage_ids = [stage.get("id") for stage in stages if stage.get("id")]
    if not stage_ids:
        stage_ids = list(stage_handlers.keys())

    for stage_id in stage_ids:
        handler = stage_handlers.get(stage_id)
        if handler is None:
            raise ValueError(f"Missing handler for stage '{stage_id}'")
        builder.add_node(stage_id, handler)

    entry_nodes = set(stage_ids)

    def entry_router(state: InvoiceState) -> str:
        resume_from = state.get("resume_from")
        if resume_from in entry_nodes:
            return resume_from
        return stage_ids[0]

    builder.set_conditional_entry_point(entry_router)

    trigger_expr = stage_by_id.get("CHECKPOINT_HITL", {}).get("trigger_condition")

    def match_router(state: InvoiceState) -> str:
        if _evaluate_trigger(trigger_expr, state):
            return "CHECKPOINT_HITL"
        match_result = state.get("match", {}).get("match_result")
        if match_result == "FAILED":
            return "CHECKPOINT_HITL"
        return "RECONCILE"

    for idx, stage_id in enumerate(stage_ids):
        if stage_id == "MATCH_TWO_WAY":
            builder.add_conditional_edges("MATCH_TWO_WAY", match_router)
            continue
        if stage_id == "CHECKPOINT_HITL":
            builder.add_edge("CHECKPOINT_HITL", END)
            continue
        if stage_id == "HITL_DECISION":
            builder.add_conditional_edges("HITL_DECISION", hitl_router)
            continue

        next_idx = idx + 1
        if next_idx < len(stage_ids):
            builder.add_edge(stage_id, stage_ids[next_idx])
        else:
            builder.add_edge(stage_id, END)

    return builder.compile(checkpointer=checkpointer or SQLiteSaver(deps.db_conn))


def create_initial_state(
    settings: Settings, payload: Dict[str, Any], run_id: str | None = None
) -> InvoiceState:
    run_id = run_id or f"run_{uuid.uuid4().hex[:10]}"
    return {
        "run_id": run_id,
        "workflow_name": settings.workflow.get("workflow_name", "InvoiceProcessing"),
        "config": settings.workflow.get("config", {}),
        "input_payload": payload,
        "status": "NEW",
        "logs": [],
    }
