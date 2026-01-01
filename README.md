# Invoice LangGraph Agent - Invoice Processing Workflow

A config-driven **LangGraph** agent that processes invoices through a **12-stage workflow**, supports **Human-In-The-Loop (HITL) pause/resume via checkpoints**, routes abilities via **MCP (COMMON vs ATLAS)**, and uses **Bigtool** to deterministically select tools (OCR, enrichment, ERP connector, DB, email) while logging every decision.

---

## Overview (What it does)

You submit an invoice payload (JSON + attachment names). The agent runs the invoice through these stages:

1. **INTAKE** - validate schema + persist raw invoice
2. **UNDERSTAND** - OCR attachments + parse line items / PO references
3. **PREPARE** - normalize vendor + enrich vendor + compute flags
4. **RETRIEVE** - fetch PO/GRN/history (ERP connector)
5. **MATCH_TWO_WAY** - compute invoice vs PO match score
6. **CHECKPOINT_HITL** - if match fails -> checkpoint + queue for human review + pause
7. **HITL_DECISION** - human ACCEPT/REJECT -> resume or stop
8. **RECONCILE** - build accounting entries
9. **APPROVE** - approval policy (auto-approve / escalate)
10. **POSTING** - post to ERP + schedule payment
11. **NOTIFY** - notify vendor + finance team
12. **COMPLETE** - output final payload + audit log + mark done

Outputs include:
- `final_payload`: structured result (status, matching evidence, approval, posting ids, etc.)
- `audit_log`: stage-by-stage trace including Bigtool selections and MCP ability calls

---

## Requirements
- Python **3.9+**
- Default persistence: SQLite (local file DB)

---

## Quick Run (CLI demo)

### 1) Clone + setup
```bash
git clone https://github.com/Amn-7/invoice-langgraph-agent.git
cd invoice-langgraph-agent

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

### 2) Happy path (no HITL)
```bash
PYTHONPATH=. python scripts/run_demo.py
```

### 3) HITL path (creates checkpoint + pauses)
```bash
PYTHONPATH=. python scripts/run_demo.py data/sample_invoice_mismatch.json
```
You should see:
- `Workflow Status PAUSED`
- a printed `checkpoint_id` like `chk_...`

### 4) Resolve HITL and resume (CLI)
Replace `<checkpoint_id>` with the printed id:
```bash
PYTHONPATH=. python scripts/resolve_hitl.py <checkpoint_id> ACCEPT reviewer_1 "Looks good"
```
To test reject:
```bash
PYTHONPATH=. python scripts/resolve_hitl.py <checkpoint_id> REJECT reviewer_1 "Needs manual handling"
```

---

## Run the Human Review API + UI

### Start server
```bash
PYTHONPATH=. uvicorn src.api.app:app --reload
```

### Open UI
`http://localhost:8000/`

### API (optional)
List pending human reviews:
```bash
curl http://localhost:8000/human-review/pending
```
Submit decision (ACCEPT / REJECT):
```bash
curl -X POST http://localhost:8000/human-review/decision \
  -H "Content-Type: application/json" \
  -d '{"checkpoint_id":"<id>","decision":"ACCEPT","notes":"ok","reviewer_id":"reviewer_1"}'
```

### Status codes
`POST /human-review/decision`:
- `200`: decision applied + resume started
- `404`: checkpoint not found
- `409`: checkpoint exists but cannot be resumed (already resolved / invalid state / resume failure)

---

## Configuration

`.env`
- Default DB is SQLite at `./data/demo.db` (via `DB_CONN`).
- Bigtool pools come from `TOOLS_CONFIG=./configs/tools.yaml`.
- MCP is stubbed by default: `MCP_MODE=stub`.

Optional real MCP config (when endpoints/auth are provided):
- `MCP_COMMON_URL=...`
- `MCP_ATLAS_URL=...`
- `MCP_AUTH_HEADER=Authorization`
- `MCP_AUTH_TOKEN=...`

---

## Project Structure
- `configs/workflow.json` - workflow definition
- `configs/tools.yaml` - Bigtool pools
- `src/core/config.py` - config loader + env ref resolver
- `src/tools/bigtool.py` - Bigtool picker
- `src/mcp/` - COMMON/ATLAS client stubs + router
- `src/nodes/workflow_nodes.py` - workflow nodes (INTAKE -> COMPLETE)
- `src/core/graph.py` - LangGraph assembly + routing
- `src/core/workflow.py` - runner (start/resume)
- `src/db/store.py` - SQLite checkpoint + review queue
- `src/api/app.py` - human review API + static UI hosting
- `src/api/static/` - frontend UI
- `scripts/run_demo.py` - run demo from sample input
- `scripts/resolve_hitl.py` - resolve HITL decision and resume

---

## Notes / Troubleshooting
- Raw invoice payloads are stored in `raw_invoices` during INTAKE.
- Bigtool selection is pluggable and stubbed in this demo; selections are logged and can route to real tools.
- MCP clients under `src/mcp/` are stub implementations by default (`MCP_MODE=stub`). Swap to real MCP endpoints when URLs/auth are provided.
- Some macOS setups may show a urllib3 LibreSSL warning; it does not affect demo runs.

---

## Artifacts (optional)
If you generate demo logs, store them under `logs/`:
- `logs/demo_success.log`
- `logs/demo_hitl_pause.log`
- `logs/demo_hitl_accept.log`

---

### What you should do now
1) Delete everything in README
2) Paste the corrected one above
3) Save
4) Push

If you want to verify quickly, run:
```bash
python -c "print(open('README.md').read().count('```'))"
```
It should be an even number (every code block opens and closes).
