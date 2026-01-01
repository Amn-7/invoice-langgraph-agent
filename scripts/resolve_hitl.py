from __future__ import annotations

import sys
from pathlib import Path

from rich import print

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.config import load_settings
from src.db import save_human_decision
from src.core.workflow import WorkflowRunner


def main() -> None:
    if len(sys.argv) < 4:
        print("Usage: resolve_hitl.py <checkpoint_id> <ACCEPT|REJECT> <reviewer_id> [notes]")
        raise SystemExit(1)

    checkpoint_id = sys.argv[1]
    decision = sys.argv[2]
    reviewer_id = sys.argv[3]
    notes = sys.argv[4] if len(sys.argv) > 4 else ""

    settings = load_settings()
    save_human_decision(
        settings.env.get("DB_CONN", "sqlite:///./data/demo.db"),
        checkpoint_id,
        decision,
        notes,
        reviewer_id,
    )

    runner = WorkflowRunner(settings)
    state = runner.resume_from_checkpoint(checkpoint_id)

    print("\n[bold]Workflow Status[/bold]", state.get("status"))
    print("[bold]Final Payload[/bold]")
    print(state.get("final"))


if __name__ == "__main__":
    main()
