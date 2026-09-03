"""Session transcripts — every turn appended to a plain-markdown note.

Phase 1 requirement: the model gets its short conversation window from memory,
but the *human-readable* transcript is also written to

    <vault>/04 - Sessions/<date>.md

so it syncs with the Obsidian vault (Phase 3) and can be re-read later. One file
per local date, one block per turn, append-only.

Kept deliberately dumb. A write failure never breaks a turn — it logs to stderr
and the conversation carries on.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from .config import REPO_ROOT, load_jarvis_json

_SUBDIR = "04 - Sessions"


def sessions_dir() -> Path:
    """`<vault_path>/04 - Sessions` when a vault is configured, else a repo-local
    `Vault/04 - Sessions` (already git-ignored). Phase 3 points vault_path at the
    Drive-synced folder and this starts syncing for free."""
    vault = (load_jarvis_json().get("vault_path") or "").strip()
    base = Path(os.path.expanduser(vault)) if vault else (REPO_ROOT / "Vault")
    return base / _SUBDIR


class SessionLog:
    """Append-only writer for one running conversation."""

    def __init__(self, *, speaker: str | None = None) -> None:
        self._speaker = speaker or load_jarvis_json().get("name", "Assistant")
        self._dir = sessions_dir()

    def _today_file(self) -> Path:
        return self._dir / f"{datetime.now():%Y-%m-%d}.md"

    def append(self, user_text: str, reply_text: str) -> None:
        user_text, reply_text = user_text.strip(), reply_text.strip()
        if not user_text and not reply_text:
            return
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path = self._today_file()
            fresh = not path.exists()
            with path.open("a", encoding="utf-8") as f:
                if fresh:
                    f.write(f"# Session — {datetime.now():%Y-%m-%d}\n")
                f.write(f"\n## {datetime.now():%H:%M}\n\n")
                f.write(f"**You:** {user_text}\n\n")
                f.write(f"**{self._speaker}:** {reply_text}\n")
        except OSError as e:  # disk full, permissions, bad path — non-fatal
            print(f"[sessions] could not write transcript: {e}", file=sys.stderr)
