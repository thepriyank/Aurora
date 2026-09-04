#!/usr/bin/env python3
"""Merge per-device daily-note / session shards into one file per day.

    python scripts/vault_consolidate.py

Each device writes `01 - Daily Notes/<date>.<device>.md` and
`04 - Sessions/<date>.<device>.md` so live edits never collide on Drive. This
job (run nightly, after the day's devices have synced) folds every
`<date>.<device>.md` shard it can see — any date — into `<date>.md` under a
`## <device>` heading, then deletes the shard. Idempotent: with the shards
gone, a second run is a no-op, so a straggler that syncs in late is simply
picked up on the next run.

Stdlib only. See docs/SYNC.md.
"""
from __future__ import annotations

import re
import sys

from _vaultlib import SHARDED_SUBDIRS, vault_dir

_SHARD = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\.(?P<device>[A-Za-z0-9-]+)\.md$")


def _consolidate_dir(folder) -> int:
    if not folder.is_dir():
        return 0
    merged = 0
    shards_by_date: dict[str, list] = {}
    for f in folder.iterdir():
        m = _SHARD.match(f.name)
        if m:
            shards_by_date.setdefault(m.group("date"), []).append((m.group("device"), f))

    for d, shards in sorted(shards_by_date.items()):
        target = folder / f"{d}.md"
        parts = []
        if not target.exists():
            parts.append(f"# {d}\n")
        for device, shard in sorted(shards):
            body = shard.read_text(encoding="utf-8").strip()
            # drop a leading "# <date>" line from the shard; keep the rest
            body = re.sub(r"\A#\s*\S.*\n?", "", body).strip()
            parts.append(f"\n## {device}\n\n{body}\n")
        with target.open("a", encoding="utf-8") as fh:
            fh.write("".join(parts))
        for _, shard in shards:
            shard.unlink()
        merged += len(shards)
        print(f"  {folder.name}/{d}.md  <- {len(shards)} shard(s)")
    return merged


def main() -> int:
    v = vault_dir()
    if not v.is_dir():
        print(f"vault not found: {v}", file=sys.stderr)
        return 1

    total = 0
    for sub in SHARDED_SUBDIRS:
        total += _consolidate_dir(v / sub)
    print(f"merged {total} shard(s)" if total else "nothing to consolidate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
