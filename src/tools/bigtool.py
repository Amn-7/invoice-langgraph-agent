from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ToolSelection:
    capability: str
    tool: str
    pool: List[str]
    reason: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "tool": self.tool,
            "pool": list(self.pool),
            "reason": self.reason,
        }


class BigtoolPicker:
    def __init__(self, pools: Dict[str, List[str]], seed: Optional[str] = None) -> None:
        self.pools = pools
        self.seed = seed or ""

    def select(
        self,
        capability: str,
        context: Optional[Dict[str, Any]] = None,
        pool_hint: Optional[List[str]] = None,
    ) -> ToolSelection:
        context = context or {}
        pool = list(pool_hint or self.pools.get(capability, []))
        if not pool:
            raise ValueError(f"No tools configured for capability '{capability}'.")

        preferred = context.get("preferred_tool") or context.get("tool")
        if preferred in pool:
            return ToolSelection(
                capability=capability,
                tool=preferred,
                pool=pool,
                reason="preferred_tool",
            )

        selection_key = "|".join(
            [
                self.seed,
                capability,
                str(context.get("invoice_id", "")),
                str(context.get("vendor_name", "")),
                str(context.get("amount", "")),
            ]
        )
        digest = hashlib.sha256(selection_key.encode("utf-8")).hexdigest()
        index = int(digest[:8], 16) % len(pool)
        return ToolSelection(
            capability=capability,
            tool=pool[index],
            pool=pool,
            reason="deterministic_hash",
        )
