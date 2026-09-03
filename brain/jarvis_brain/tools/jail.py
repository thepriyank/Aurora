"""Filesystem jail.

Every path a tool touches is resolved to an absolute real path and must live
under one of the configured roots (vault, workspace, and anything the user adds
in config/tools.yaml). `..`, absolute paths outside the roots, and symlinks that
point out are all rejected — `Path.resolve()` collapses them before the check.
"""
from __future__ import annotations

import os
from pathlib import Path


class OutOfJail(Exception):
    """A tool asked for a path outside every allowed root."""


def _real(p: Path) -> Path:
    # strict=False: the target may not exist yet (fs.write, fs.mkdir)
    return Path(os.path.realpath(p))


def resolve_in_roots(
    path_str: str,
    roots: dict[str, Path],
    *,
    must_exist: bool = False,
) -> Path:
    if not path_str or not str(path_str).strip():
        raise OutOfJail("empty path")
    raw = Path(os.path.expanduser(str(path_str).strip()))

    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(_real(raw))
    else:
        # a bare relative path is tried against each root
        for base in roots.values():
            candidates.append(_real(base / raw))

    in_a_root = False
    for cand in candidates:
        for base in roots.values():
            rbase = _real(base)
            if cand == rbase or rbase in cand.parents:
                in_a_root = True
                if must_exist and not cand.exists():
                    continue  # structurally fine, just not here — try the next root
                return cand

    if in_a_root and must_exist:
        raise OutOfJail(f"no such path under the allowed roots: {path_str}")
    allowed = ", ".join(str(b) for b in roots.values())
    raise OutOfJail(
        f"path {path_str!r} is outside the allowed roots ({allowed})"
    )


def label_for(path: Path, roots: dict[str, Path]) -> str:
    """A short 'root:relative' label for logs and spoken confirmations."""
    for name, base in roots.items():
        rbase = _real(base)
        if path == rbase or rbase in path.parents:
            rel = path.relative_to(rbase)
            return f"{name}/{rel}" if str(rel) != "." else name
    return str(path)
