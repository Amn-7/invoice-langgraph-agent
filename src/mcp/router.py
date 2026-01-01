from __future__ import annotations

from typing import Any, Dict

from .atlas_client import AtlasClient
from .common_client import CommonClient


class McpRouter:
    def __init__(
        self,
        common: CommonClient | None = None,
        atlas: AtlasClient | None = None,
    ) -> None:
        self.common = common or CommonClient()
        self.atlas = atlas or AtlasClient()

    def execute(self, server: str, ability: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        server_key = server.strip().upper()
        if server_key == "COMMON":
            return self.common.execute_ability(ability, payload)
        if server_key == "ATLAS":
            return self.atlas.execute_ability(ability, payload)
        raise ValueError(f"Unsupported MCP server '{server}'.")
