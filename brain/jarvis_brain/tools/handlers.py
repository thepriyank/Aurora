"""Tool implementations. Every handler takes (roots, cfg, **args) and returns a
short string the model reads back. Handlers raise ToolError for a clean,
model-visible failure; anything else is caught by the dispatcher.

Filesystem access goes through jail.resolve_in_roots — there is no path here
that can escape the configured roots.
"""
from __future__ import annotations

import html
import os
import re
import shlex
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from .jail import OutOfJail, label_for, resolve_in_roots

_MAX_READ = 100_000
_MAX_OUT = 6_000


class ToolError(Exception):
    """A tool failed in a way worth telling the model about verbatim."""


def _clip(s: str, n: int = _MAX_OUT) -> str:
    s = s if isinstance(s, str) else str(s)
    return s if len(s) <= n else s[:n] + f"\n… [truncated, {len(s)} chars total]"


# --------------------------------------------------------------------------- #
# filesystem
# --------------------------------------------------------------------------- #
def fs_read(roots, cfg, *, path: str) -> str:
    p = resolve_in_roots(path, roots, must_exist=True)
    if not p.is_file():
        raise ToolError(f"{path} is not a file")
    data = p.read_bytes()[:_MAX_READ]
    try:
        return _clip(data.decode("utf-8"), 20_000)
    except UnicodeDecodeError:
        raise ToolError(f"{path} is not UTF-8 text")


def fs_list(roots, cfg, *, path: str = ".") -> str:
    p = resolve_in_roots(path, roots, must_exist=True)
    if not p.is_dir():
        raise ToolError(f"{path} is not a directory")
    rows = []
    for child in sorted(p.iterdir()):
        tag = "d" if child.is_dir() else "f"
        size = child.stat().st_size if child.is_file() else ""
        rows.append(f"{tag}  {child.name}{('  ' + str(size) + 'B') if size != '' else ''}")
    return _clip("\n".join(rows) or "(empty)")


def _iter_search_roots(path: str | None, roots) -> list[Path]:
    if path:
        return [resolve_in_roots(path, roots, must_exist=True)]
    return list(roots.values())


def fs_search(roots, cfg, *, query: str, path: str | None = None) -> str:
    bases = _iter_search_roots(path, roots)
    try:
        rx = re.compile(query, re.IGNORECASE)
    except re.error as e:
        raise ToolError(f"bad regex: {e}")
    hits: list[str] = []
    for base in bases:
        files = [base] if base.is_file() else base.rglob("*")
        for f in files:
            if not f.is_file() or f.stat().st_size > _MAX_READ:
                continue
            if any(seg in {".git", "node_modules", ".venv", "__pycache__"}
                   for seg in f.parts):
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{label_for(f, roots)}:{i}: {line.strip()[:200]}")
                    if len(hits) >= 60:
                        return _clip("\n".join(hits) + "\n… [60-hit cap]")
    return _clip("\n".join(hits)) if hits else "no matches"


def fs_write(roots, cfg, *, path: str, content: str, mode: str = "overwrite") -> str:
    p = resolve_in_roots(path, roots)
    p.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append":
        with p.open("a", encoding="utf-8") as f:
            f.write(content)
    else:
        p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {label_for(p, roots)} ({mode})"


def fs_move(roots, cfg, *, src: str, dst: str) -> str:
    s = resolve_in_roots(src, roots, must_exist=True)
    # anchor a relative destination to the SAME root the source is in, so
    # "move X from Downloads to Invoices" doesn't jump roots
    if not Path(os.path.expanduser(str(dst))).is_absolute():
        for base in roots.values():
            rb = Path(os.path.realpath(base))
            if s == rb or rb in s.parents:
                d = resolve_in_roots(str(rb / dst), {"_": rb})
                break
        else:
            d = resolve_in_roots(dst, roots)
    else:
        d = resolve_in_roots(dst, roots)
    if d.is_dir():
        d = d / s.name
    d.parent.mkdir(parents=True, exist_ok=True)
    s.rename(d)
    return f"moved {label_for(s, roots)} -> {label_for(d, roots)}"


def fs_mkdir(roots, cfg, *, path: str) -> str:
    p = resolve_in_roots(path, roots)
    p.mkdir(parents=True, exist_ok=True)
    return f"created {label_for(p, roots)}"


def fs_delete(roots, cfg, *, path: str, recursive: bool = False) -> str:
    """Only reachable if tools.yaml downgrades fs.delete from its default
    'never' tier. Even then: a non-empty directory needs recursive=true."""
    import shutil

    p = resolve_in_roots(path, roots, must_exist=True)
    if p.is_dir():
        if any(p.iterdir()) and not recursive:
            raise ToolError(f"{path} is a non-empty directory (pass recursive=true)")
        shutil.rmtree(p) if recursive else p.rmdir()
    else:
        p.unlink()
    return f"deleted {label_for(p, roots)}"


# --------------------------------------------------------------------------- #
# shell (allowlisted argv[0], denylisted substrings, no shell=True)
# --------------------------------------------------------------------------- #
def shell_run(roots, cfg, *, command: str) -> str:
    cmd = str(command).strip()
    low = cmd.lower()
    for bad in cfg.shell.get("deny_patterns", []):
        if bad.lower() in low:
            raise ToolError(f"refused: command matches a blocked pattern ({bad!r})")
    try:
        argv = shlex.split(cmd, posix=True)
    except ValueError as e:
        raise ToolError(f"cannot parse command: {e}")
    if not argv:
        raise ToolError("empty command")
    prog = Path(argv[0]).name
    allow = set(cfg.shell.get("allow", []))
    if prog not in allow:
        raise ToolError(f"refused: {prog!r} is not in the shell allowlist")
    cwd = roots.get("workspace") or next(iter(roots.values()))
    try:
        r = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise ToolError("command timed out after 30s")
    except OSError as e:
        raise ToolError(f"could not run: {e}")
    out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
    return _clip(f"exit {r.returncode}\n{out.strip()}")


# --------------------------------------------------------------------------- #
# web
# --------------------------------------------------------------------------- #
_TAG = re.compile(r"<[^>]+>")
_RESULT = re.compile(
    r'result__a[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
    r'result__snippet[^>]*>(?P<snip>.*?)</a>',
    re.S,
)


def web_search(roots, cfg, *, query: str) -> str:
    url = cfg.web.get("search_url", "https://duckduckgo.com/html/")
    try:
        r = httpx.post(
            url, data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 jarvis-brain"},
            timeout=cfg.web.get("timeout_s", 15), follow_redirects=True,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        return f"web search unavailable (offline?): {e}"
    rows = []
    for m in _RESULT.finditer(r.text):
        title = html.unescape(_TAG.sub("", m.group("title"))).strip()
        snip = html.unescape(_TAG.sub("", m.group("snip"))).strip()
        link = html.unescape(m.group("url"))
        if title:
            rows.append(f"- {title}\n  {snip[:200]}\n  {link}")
        if len(rows) >= 5:
            break
    return "\n".join(rows) if rows else "no results parsed"


def web_fetch(roots, cfg, *, url: str) -> str:
    if not re.match(r"^https?://", url):
        raise ToolError("only http(s) URLs")
    cap = int(cfg.web.get("max_fetch_bytes", 200_000))
    try:
        r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0 jarvis-brain"},
                      timeout=cfg.web.get("timeout_s", 15), follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as e:
        return f"fetch failed: {e}"
    text = r.text[:cap]
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = _TAG.sub(" ", text)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return _clip(text, 8_000)


# --------------------------------------------------------------------------- #
# git
# --------------------------------------------------------------------------- #
def _git(roots, root_name: str | None, *args: str) -> str:
    root = roots.get(root_name or "workspace")
    if root is None:
        raise ToolError(f"unknown root {root_name!r}")
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ToolError(f"git failed: {e}")
    if r.returncode != 0 and r.stderr:
        raise ToolError(_clip(r.stderr.strip(), 1_000))
    return _clip((r.stdout or "").strip() or "(no output)")


def git_status(roots, cfg, *, root: str | None = None) -> str:
    return _git(roots, root, "status", "--short", "--branch")


def git_log(roots, cfg, *, root: str | None = None, n: int = 10) -> str:
    return _git(roots, root, "log", f"-{int(n)}", "--oneline")


def git_diff(roots, cfg, *, root: str | None = None) -> str:
    return _git(roots, root, "diff")


def git_add(roots, cfg, *, root: str | None = None, paths: str = "-A") -> str:
    return _git(roots, root, "add", *shlex.split(paths or "-A")) or "staged"


def git_commit(roots, cfg, *, root: str | None = None, message: str) -> str:
    return _git(roots, root, "commit", "-m", message)


# --------------------------------------------------------------------------- #
# Obsidian vault helpers
# --------------------------------------------------------------------------- #
def _vault(roots) -> Path:
    v = roots.get("vault")
    if v is None:
        raise ToolError("no vault root configured")
    return v


def vault_append_daily_note(roots, cfg, *, text: str) -> str:
    v = _vault(roots)
    d = v / "01 - Daily Notes"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{date.today():%Y-%m-%d}.md"
    fresh = not f.exists()
    with f.open("a", encoding="utf-8") as fh:
        if fresh:
            fh.write(f"# {date.today():%Y-%m-%d}\n\n")
        fh.write(f"- {text.strip()}\n")
    return f"appended to daily note {f.name}"


def vault_create_note(roots, cfg, *, path: str, content: str) -> str:
    v = _vault(roots)
    rel = path if path.endswith(".md") else path + ".md"
    p = resolve_in_roots(str(v / rel), {"vault": v})
    if p.exists():
        raise ToolError(f"{rel} already exists — use fs.write to change it")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.rstrip() + "\n", encoding="utf-8")
    return f"created note {rel}"


def vault_search(roots, cfg, *, query: str) -> str:
    v = _vault(roots)
    direct = fs_search({"vault": v}, cfg, query=query)
    if direct != "no matches":
        return direct
    # loose retry: OR the meaningful words so "coffee preference" still finds
    # "...prefers their coffee..."
    words = [re.escape(w) for w in re.findall(r"[A-Za-z0-9]{3,}", query)]
    if len(words) >= 1:
        loose = fs_search({"vault": v}, cfg, query="|".join(words))
        if loose != "no matches":
            return "loose matches:\n" + loose
    return "no matches"


def vault_read_note_set(roots, cfg, *, name: str) -> str:
    v = _vault(roots)
    idx = v / "VAULT-INDEX.md"
    if not idx.exists():
        return ("no VAULT-INDEX.md in the vault yet — note sets are defined "
                "there as 'setname: Note A.md, Note B.md'")
    text = idx.read_text(encoding="utf-8")
    want = name.strip().lower()
    notes: list[str] = []
    for block in re.split(r"\n(?=#{1,6}\s|\s*-\s|\w+:)", text):
        head = block.strip().lower()
        if want in head[:80]:
            notes += re.findall(r"[\w /\-]+\.md", block)
    notes = list(dict.fromkeys(notes))
    if not notes:
        return f"no note set named {name!r} in VAULT-INDEX.md"
    chunks = []
    for n in notes:
        p = (v / n.strip())
        if p.is_file():
            chunks.append(f"### {n.strip()}\n{p.read_text(encoding='utf-8')}")
    return _clip("\n\n".join(chunks) or f"note set {name!r} lists files that don't exist yet")
