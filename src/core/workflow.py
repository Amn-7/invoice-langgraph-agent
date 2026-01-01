from __future__ import annotations

from typing import Any, Dict, Optional

from src.core.config import Settings
from src.db import SQLiteSaver, load_checkpoint
from src.core.graph import build_graph, create_initial_state
from src.core.state import InvoiceState


class WorkflowRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_conn = settings.env.get("DB_CONN", "sqlite:///./data/demo.db")
        self.checkpointer = SQLiteSaver(self.db_conn)
        self.graph = build_graph(settings, checkpointer=self.checkpointer)

    def run(self, payload: Dict[str, Any], run_id: Optional[str] = None) -> InvoiceState:
        state = create_initial_state(self.settings, payload, run_id=run_id)
        thread_id = state["run_id"]
        config = {"configurable": {"thread_id": thread_id}}
        return self.graph.invoke(state, config=config)

    def resume_from_checkpoint(
        self,
        checkpoint_id: str,
        resume_from: str = "HITL_DECISION",
    ) -> InvoiceState:
        state = load_checkpoint(self.db_conn, checkpoint_id)
        state["resume_from"] = resume_from
        thread_id = state.get("run_id", checkpoint_id)
        config = {"configurable": {"thread_id": thread_id}}
        return self.graph.invoke(state, config=config)
