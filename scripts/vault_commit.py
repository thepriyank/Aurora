#!/usr/bin/env python3
"""Snapshot the memory vault with git. Run every ~30 minutes from a scheduler.

    python scripts/vault_commit.py [--push]

- git-inits the vault on first run and writes a vault .gitignore
- commits only when something actually changed
- --push also pushes to `origin` if one is configured (set it up yourself:
  `git -C <vault> remote add origin <private-repo-url>`)

Stdlib only. See docs/SYNC.md for cron / Task Scheduler / launchd snippets.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime

from _vaultlib import VAULT_GITIGNORE, vault_dir


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(vault_dir()), *args],
        capture_output=True, text=True, check=check,
    )


def main() -> int:
    v = vault_dir()
    if not v.is_dir():
        print(f"vault not found: {v}", file=sys.stderr)
        return 1

    if not (v / ".git").exists():
        print(f"git-init {v}")
        _git("init", "-q")
        _git("symbolic-ref", "HEAD", "refs/heads/main", check=False)
        (v / ".gitignore").write_text(VAULT_GITIGNORE, encoding="utf-8")

    _git("add", "-A")
    status = _git("status", "--porcelain").stdout.strip()
    if not status:
        print("no changes")
        return 0

    msg = f"vault snapshot {datetime.now():%Y-%m-%d %H:%M}"
    r = _git("commit", "-q", "-m", msg, check=False)
    if r.returncode != 0:
        print(r.stderr.strip() or "commit failed", file=sys.stderr)
        return r.returncode
    n = len(status.splitlines())
    print(f"committed: {msg}  ({n} path{'s' if n != 1 else ''})")

    if "--push" in sys.argv:
        has_origin = _git("remote", check=False).stdout.split()
        if "origin" in has_origin:
            p = _git("push", "-q", "origin", "HEAD", check=False)
            print("pushed" if p.returncode == 0 else
                  f"push failed: {p.stderr.strip()}")
        else:
            print("--push given but no 'origin' remote on the vault; skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
