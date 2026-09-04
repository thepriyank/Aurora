"""Shared helpers for the vault maintenance scripts. Stdlib only — these run
from a bare `python`, no venv, so a cron / Task Scheduler / launchd job needs
nothing installed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
JARVIS_JSON = REPO_ROOT / "config" / "jarvis.json"


def vault_dir() -> Path:
    """config/jarvis.json -> vault_path, else the repo-local Vault/."""
    try:
        data = json.loads(JARVIS_JSON.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        data = {}
    v = str(data.get("vault_path") or "").strip()
    return Path(os.path.expanduser(v)) if v else REPO_ROOT / "Vault"


VAULT_GITIGNORE = """\
# Obsidian churn — these cause almost all false sync/merge conflicts
.obsidian/workspace.json
.obsidian/workspace*.json
.obsidian/cache
.obsidian/cache/
.trash/
.DS_Store
"""

# Folders whose per-device shards (<date>.<device>.md) the nightly job merges.
SHARDED_SUBDIRS = ("01 - Daily Notes", "04 - Sessions")
