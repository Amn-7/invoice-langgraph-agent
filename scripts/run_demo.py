from __future__ import annotations

import json
from pathlib import Path
import sys

from rich import print

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.config import load_settings
from src.core.workflow import WorkflowRunner


def load_payload(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    settings = load_settings()
    runner = WorkflowRunner(settings)

    input_path = sys.argv[1] if len(sys.argv) > 1 else "data/sample_invoice.json"
    payload = load_payload(input_path)
    state = runner.run(payload)

    print("\n[bold]Input[/bold]", input_path)
    print("[bold]Workflow Status[/bold]", state.get("status"))
    print("[bold]Checkpoint[/bold]", state.get("checkpoint"))
    print("[bold]Final Payload[/bold]")
    print(state.get("final"))

    print("\n[bold]Logs[/bold]")
    for entry in state.get("logs", []):
        print(f"- {entry['stage']} :: {entry['action']} :: {entry['detail']}")


if __name__ == "__main__":
    main()
