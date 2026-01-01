Architecture - Invoice LangGraph Agent

Overview
This project implements a 12-stage invoice workflow using LangGraph. The graph is built from `configs/workflow.json`, and each stage is implemented as a node that reads and writes a shared state object.

Key Modules
- Core orchestration: `src/core/graph.py`, `src/core/workflow.py`
- Node implementations: `src/nodes/workflow_nodes.py`
- State schema: `src/core/state.py`
- Configuration loader: `src/core/config.py`
- MCP routing: `src/mcp/router.py` + `src/mcp/*_client.py`
- Bigtool selection: `src/tools/bigtool.py`
- Checkpoints + queue: `src/db/store.py`
- LangGraph checkpointer: `src/db/langgraph_saver.py`
- Human review API: `src/api/app.py`

Data Flow (Happy Path)
Input payload -> INTAKE -> UNDERSTAND -> PREPARE -> RETRIEVE -> MATCH_TWO_WAY ->
RECONCILE -> APPROVE -> POSTING -> NOTIFY -> COMPLETE

Data Flow (HITL Path)
Input payload -> INTAKE -> UNDERSTAND -> PREPARE -> RETRIEVE -> MATCH_TWO_WAY
  if FAILED -> CHECKPOINT_HITL (pause) -> HITL_DECISION -> RECONCILE -> ... -> COMPLETE
  if ACCEPT -> continue
  if REJECT -> COMPLETE (status = REQUIRES_MANUAL_HANDLING)

Graph Wiring
- The graph is assembled dynamically from `configs/workflow.json` stage order.
- Conditional edges:
  - MATCH_TWO_WAY -> CHECKPOINT_HITL or RECONCILE
  - HITL_DECISION -> RECONCILE or COMPLETE

MCP Routing
- Ability names map to servers via `configs/workflow.json` -> `ability_map`.
- `McpRouter.execute(server, ability, payload)` routes calls to COMMON or ATLAS clients.

Bigtool Selection
- `BigtoolPicker.select(capability, context)` chooses a tool deterministically.
- Tool choice is logged per stage in `logs`.

Checkpointing
- LangGraph checkpointer uses `SQLiteSaver` to persist checkpoint frames.
- Separate workflow checkpoint state is stored in `checkpoints` + `human_review_queue` tables.
- HITL resumes from stored state via `WorkflowRunner.resume_from_checkpoint()`.

State Shape (High Level)
- `input_payload`: original invoice payload
- `raw`, `parsed`, `vendor`, `flags`, `retrieved`, `match`: intermediate outputs
- `checkpoint`, `human`: HITL data
- `reconcile`, `approval`, `posting`, `notify`, `final`: downstream outputs
- `logs`: stage-by-stage log entries

Runtime Entry Points
- CLI demo: `scripts/run_demo.py`
- HITL resolution: `scripts/resolve_hitl.py`
- API: `src/api/app.py`
