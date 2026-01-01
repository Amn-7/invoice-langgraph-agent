from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

DEFAULT_WORKFLOW_PATH = "configs/workflow.json"
DEFAULT_TOOLS_PATH = "configs/tools.yaml"


@dataclass
class Settings:
    workflow: Dict[str, Any]
    tool_pools: Dict[str, Any]
    env: Dict[str, str]


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _resolve_config_refs(obj: Any, env: Dict[str, str]) -> Any:
    if isinstance(obj, dict):
        return {k: _resolve_config_refs(v, env) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_config_refs(v, env) for v in obj]
    if isinstance(obj, str) and obj.startswith("{{") and obj.endswith("}}"):
        key = obj[2:-2].strip()
        return env.get(key, obj)
    return obj


def load_settings(
    workflow_path: str = DEFAULT_WORKFLOW_PATH,
    tools_path: str | None = None,
) -> Settings:
    load_dotenv()
    env = dict(os.environ)

    tools_path = tools_path or env.get("TOOLS_CONFIG", DEFAULT_TOOLS_PATH)

    workflow = _load_json(workflow_path)
    workflow = _resolve_config_refs(workflow, env)

    tools_cfg = _load_yaml(tools_path)
    pools = tools_cfg.get("pools", {})

    return Settings(workflow=workflow, tool_pools=pools, env=env)
