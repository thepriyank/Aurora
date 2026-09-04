"""Session transcripts — every turn appended to a plain-markdown note.

The model gets its short conversation window from memory, but the
human-readable transcript is also written to

    <vault>/04 - Sessions/<date>.<device>.md

Per-device filename (Phase 3): two machines never touch the same file the same
minute, so a Drive sync never has to merge. The nightly consolidation job
(scripts/vault_consolidate.py) folds the day's shards into <date>.md.

A write failure never breaks a turn — it logs to stderr and the conversation
carries on.
"""
from __future__ import annotations

import sys
from datetime import datetime

from .config import dated_shard, load_jarvis_json

_SUBDIR = "04 - Sessions"


class SessionLog:
    """Append-only writer for one running conversation."""

    def __init__(self, *, speaker: str | None = None) -> None:
        self._speaker = speaker or load_jarvis_json().get("name", "Assistant")

    def append(self, user_text: str, reply_text: str) -> None:
        user_text, reply_text = user_text.strip(), reply_text.strip()
        if not user_text and not reply_text:
            return
        try:
            path = dated_shard(_SUBDIR)
            path.parent.mkdir(parents=True, exist_ok=True)
            fresh = not path.exists()
            with path.open("a", encoding="utf-8") as f:
                if fresh:
                    f.write(f"# Session — {datetime.now():%Y-%m-%d}\n")
                f.write(f"\n## {datetime.now():%H:%M}\n\n")
                f.write(f"**You:** {user_text}\n\n")
                f.write(f"**{self._speaker}:** {reply_text}\n")
        except OSError as e:  # disk full, permissions, bad path — non-fatal
            print(f"[sessions] could not write transcript: {e}", file=sys.stderr)
