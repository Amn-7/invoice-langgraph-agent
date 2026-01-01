Invoice LangGraph Agent - Invoice Processing Workflow

Overview
- Implements a 12-stage LangGraph workflow with deterministic and non-deterministic nodes.
- Supports HITL checkpoints (pause/resume), MCP routing (COMMON/ATLAS), and Bigtool tool selection.
- Includes a human-review FastAPI service and demo scripts.

Getting Started (Quick Run)
- python3 -m venv .venv
- source .venv/bin/activate
- pip install -r requirements.txt
- cp .env.example .env
- PYTHONPATH=. .venv/bin/python scripts/run_demo.py

Project Structure
- configs/workflow.json: workflow definition (Appendix-1)
- configs/tools.yaml: Bigtool pools
- docs/architecture.md: architecture summary
- src/core/config.py: config loader + env ref resolver
- src/tools/bigtool.py: Bigtool picker
- src/mcp/: COMMON/ATLAS client stubs + router
- src/nodes/workflow_nodes.py: workflow nodes
- src/core/graph.py: LangGraph assembly + routing
- src/core/workflow.py: runner (start/resume)
- src/db/store.py: sqlite checkpoint + review queue
- src/api/app.py: human-review API
- scripts/run_demo.py: run demo from sample input
- scripts/resolve_hitl.py: resolve HITL decision and resume

Setup
1) Create venv and install deps
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

If you do not have a requirements.txt, install the packages used in this project:
   pip install langgraph fastapi uvicorn pydantic python-dotenv httpx rich pytest

2) Create env file
   cp .env.example .env

Demo (Happy Path)
- Run with the default sample invoice:
  PYTHONPATH=. .venv/bin/python scripts/run_demo.py

Demo (HITL Path)
- Run with a forced mismatch:
  PYTHONPATH=. .venv/bin/python scripts/run_demo.py data/sample_invoice_mismatch.json

- You will see a checkpoint_id printed. Resolve it:
  PYTHONPATH=. .venv/bin/python scripts/resolve_hitl.py <checkpoint_id> ACCEPT reviewer_1 "Looks good"

Human Review API
- Start API server:
  PYTHONPATH=. .venv/bin/uvicorn src.api.app:app --reload

- Open the basic frontend:
  http://localhost:8000/

- Submit an invoice from the UI (optional) or via curl:
  curl -X POST http://localhost:8000/invoice/submit \
    -H "Content-Type: application/json" \
    -d @data/sample_invoice.json

- List pending:
  curl http://localhost:8000/human-review/pending

- Submit decision:
  curl -X POST http://localhost:8000/human-review/decision \
    -H "Content-Type: application/json" \
    -d '{"checkpoint_id":"<id>","decision":"ACCEPT","notes":"ok","reviewer_id":"reviewer_1"}'

Notes
- By default, sqlite DB lives at ./data/demo.db (see .env).
- Raw invoice payloads are stored in the `raw_invoices` table during INTAKE.
- Bigtool selection is deterministic based on payload context.
- MCP clients in src/mcp are stub implementations (MCP integration is satisfied without real endpoints). Swap them for real servers when URLs/auth are provided.
- Set `MCP_MODE=stub` in `.env` to keep stubs active; use real MCP URLs if provided.

Artifacts
- logs/demo_success.log: happy path run output
- logs/demo_hitl_pause.log: HITL pause output
- logs/demo_hitl_accept.log: HITL accept/resume output
