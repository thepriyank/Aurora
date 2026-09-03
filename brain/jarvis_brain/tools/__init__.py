"""jarvis_brain.tools — native tool layer (Phase 2).

    registry.py   config load, root resolution, the tool table, Ollama schemas
    jail.py       filesystem confinement to the configured roots
    handlers.py   the actual tools: fs / shell / web / git / Obsidian vault
    gate.py       Dispatcher: tier check -> spoken/typed confirm -> audit.jsonl

Usage from the brain:

    cfg = load_tools_config()
    dispatch = Dispatcher(cfg, can_use_tool=<backtalk gate or None>)
    schemas = ollama_schemas(cfg)
    ... pass schemas + dispatch into core.run_turn ...
"""
from __future__ import annotations

from .gate import AUDIT_PATH, Dispatcher
from .registry import (
    TOOLS,
    ToolsConfig,
    load_tools_config,
    ollama_schemas,
)

__all__ = [
    "AUDIT_PATH",
    "Dispatcher",
    "TOOLS",
    "ToolsConfig",
    "load_tools_config",
    "ollama_schemas",
]
