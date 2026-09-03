"""Tool registry: config load, root resolution, the tool table, and the
Ollama function schemas.

Phase 2 ships native tools (filesystem, shell, web, git, Obsidian vault). MCP
servers are declared in config/tools.yaml for a later pass; nothing here needs
them for the Definition of Done.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from ..config import CONFIG_DIR, REPO_ROOT, load_jarvis_json
from . import handlers as H

Tier = str  # "auto" | "confirm" | "never"

_DEFAULT_TIERS: dict[str, Tier] = {
    "fs.read": "auto", "fs.list": "auto", "fs.search": "auto",
    "fs.write": "confirm", "fs.move": "confirm", "fs.mkdir": "confirm",
    "fs.delete": "never",
    "shell.run": "confirm",
    "web.search": "auto", "web.fetch": "auto",
    "git.status": "auto", "git.log": "auto", "git.diff": "auto",
    "git.add": "confirm", "git.commit": "confirm",
    "vault.append_daily_note": "auto", "vault.create_note": "confirm",
    "vault.search": "auto", "vault.read_note_set": "auto",
}

_DEFAULT_SHELL = {
    "allow": ["ls", "cat", "echo", "pwd", "date", "whoami", "git", "rg",
              "grep", "find", "head", "tail", "wc", "python", "python3",
              "node", "npm", "uv"],
    "deny_patterns": ["rm -rf", "rm -r ", "rm -fr", ":(){", "mkfs", "dd if=",
                      "> /dev/sd", "format ", "del /", "rmdir /s", "shutdown",
                      "reg delete", "diskpart"],
}
_DEFAULT_WEB = {
    "search_url": "https://duckduckgo.com/html/",
    "max_fetch_bytes": 200_000,
    "timeout_s": 15,
}


@dataclass
class ToolsConfig:
    roots: dict[str, Path]
    tiers: dict[str, Tier]
    shell: dict[str, Any]
    web: dict[str, Any]
    _raw: dict = field(default_factory=dict, repr=False)

    def tier(self, tool: str) -> Tier:
        return self.tiers.get(tool, _DEFAULT_TIERS.get(tool, "confirm"))


def _default_roots() -> dict[str, Path]:
    ident = load_jarvis_json()
    vault = (ident.get("vault_path") or "").strip()
    workspace = (ident.get("workspace_path") or "~/jarvis-workspace").strip()
    # workspace first: a bare relative path in a file task lands here, not in
    # the memory vault. vault.* tools always pass their own {"vault": ...}.
    roots = {
        "workspace": Path(os.path.expanduser(workspace)),
        "vault": Path(os.path.expanduser(vault)) if vault else REPO_ROOT / "Vault",
    }
    for p in roots.values():
        p.mkdir(parents=True, exist_ok=True)
    return roots


def load_tools_config() -> ToolsConfig:
    path = CONFIG_DIR / "tools.yaml"
    raw: dict = {}
    if path.exists():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            raw = {}

    roots = _default_roots()
    for name, val in (raw.get("roots") or {}).items():
        if val and str(val).strip():
            p = Path(os.path.expanduser(str(val).strip()))
            p.mkdir(parents=True, exist_ok=True)
            roots[name] = p

    tiers = dict(_DEFAULT_TIERS)
    tiers.update({k: str(v) for k, v in (raw.get("tiers") or {}).items()})

    shell = dict(_DEFAULT_SHELL)
    shell.update(raw.get("shell") or {})
    web = dict(_DEFAULT_WEB)
    web.update(raw.get("web") or {})

    return ToolsConfig(roots=roots, tiers=tiers, shell=shell, web=web, _raw=raw)


# --------------------------------------------------------------------------- #
# the tool table
# --------------------------------------------------------------------------- #
@dataclass
class ToolDef:
    name: str
    description: str
    params: dict            # JSON schema for the arguments object
    handler: Callable[..., str]


def _s(t: str, desc: str) -> dict:
    return {"type": t, "description": desc}


TOOLS: dict[str, ToolDef] = {
    "fs.read": ToolDef(
        "fs.read", "Read a UTF-8 text file inside the allowed roots.",
        {"type": "object", "properties": {"path": _s("string", "file path")},
         "required": ["path"]},
        H.fs_read),
    "fs.list": ToolDef(
        "fs.list", "List a directory inside the allowed roots.",
        {"type": "object", "properties": {"path": _s("string", "dir path, default '.'")}},
        H.fs_list),
    "fs.search": ToolDef(
        "fs.search", "Search file contents (regex) under a path in the roots.",
        {"type": "object", "properties": {
            "query": _s("string", "regex or literal"),
            "path": _s("string", "dir to search, default all roots")},
         "required": ["query"]},
        H.fs_search),
    "fs.write": ToolDef(
        "fs.write", "Create or modify a text file inside the roots.",
        {"type": "object", "properties": {
            "path": _s("string", "file path"),
            "content": _s("string", "full new content"),
            "mode": _s("string", "'overwrite' (default) or 'append'")},
         "required": ["path", "content"]},
        H.fs_write),
    "fs.move": ToolDef(
        "fs.move", "Move or rename a file/dir; both ends must be inside the roots.",
        {"type": "object", "properties": {
            "src": _s("string", "source path"),
            "dst": _s("string", "destination path")},
         "required": ["src", "dst"]},
        H.fs_move),
    "fs.mkdir": ToolDef(
        "fs.mkdir", "Create a directory (with parents) inside the roots.",
        {"type": "object", "properties": {"path": _s("string", "dir path")},
         "required": ["path"]},
        H.fs_mkdir),
    "fs.delete": ToolDef(
        "fs.delete", "Delete a file or directory inside the roots. Blocked by "
        "default (never tier).",
        {"type": "object", "properties": {
            "path": _s("string", "path to delete"),
            "recursive": _s("boolean", "delete a non-empty directory")},
         "required": ["path"]},
        H.fs_delete),
    "shell.run": ToolDef(
        "shell.run", "Run one allowlisted shell command in the workspace root.",
        {"type": "object", "properties": {"command": _s("string", "the command line")},
         "required": ["command"]},
        H.shell_run),
    "web.search": ToolDef(
        "web.search", "Web search; returns a few titles, snippets and URLs.",
        {"type": "object", "properties": {"query": _s("string", "search query")},
         "required": ["query"]},
        H.web_search),
    "web.fetch": ToolDef(
        "web.fetch", "Fetch a URL and return its readable text (truncated).",
        {"type": "object", "properties": {"url": _s("string", "http(s) URL")},
         "required": ["url"]},
        H.web_fetch),
    "git.status": ToolDef(
        "git.status", "git status for a repo root (default: workspace).",
        {"type": "object", "properties": {"root": _s("string", "root name, default 'workspace'")}},
        H.git_status),
    "git.log": ToolDef(
        "git.log", "Recent git commits for a repo root.",
        {"type": "object", "properties": {
            "root": _s("string", "root name"), "n": _s("integer", "count, default 10")}},
        H.git_log),
    "git.diff": ToolDef(
        "git.diff", "git diff for a repo root.",
        {"type": "object", "properties": {"root": _s("string", "root name")}},
        H.git_diff),
    "git.add": ToolDef(
        "git.add", "git add paths in a repo root.",
        {"type": "object", "properties": {
            "root": _s("string", "root name"),
            "paths": _s("string", "space-separated paths, default '-A'")}},
        H.git_add),
    "git.commit": ToolDef(
        "git.commit", "git commit staged changes in a repo root.",
        {"type": "object", "properties": {
            "root": _s("string", "root name"),
            "message": _s("string", "commit message")},
         "required": ["message"]},
        H.git_commit),
    "vault.append_daily_note": ToolDef(
        "vault.append_daily_note", "Append a line to today's daily note in the vault.",
        {"type": "object", "properties": {"text": _s("string", "the line to add")},
         "required": ["text"]},
        H.vault_append_daily_note),
    "vault.create_note": ToolDef(
        "vault.create_note", "Create a markdown note in the vault.",
        {"type": "object", "properties": {
            "path": _s("string", "note path under the vault, .md"),
            "content": _s("string", "note body")},
         "required": ["path", "content"]},
        H.vault_create_note),
    "vault.search": ToolDef(
        "vault.search", "Search the vault's markdown for a term.",
        {"type": "object", "properties": {"query": _s("string", "regex or literal")},
         "required": ["query"]},
        H.vault_search),
    "vault.read_note_set": ToolDef(
        "vault.read_note_set", "Read a named note set declared in VAULT-INDEX.md.",
        {"type": "object", "properties": {"name": _s("string", "note-set name")},
         "required": ["name"]},
        H.vault_read_note_set),
}


def ollama_schemas(cfg: ToolsConfig, *, include_never: bool = False) -> list[dict]:
    """Function specs for /api/chat `tools`. `never`-tier tools are hidden from
    the model entirely unless asked for."""
    out = []
    for name, td in TOOLS.items():
        if not include_never and cfg.tier(name) == "never":
            continue
        out.append({
            "type": "function",
            "function": {
                "name": name,
                "description": td.description,
                "parameters": td.params,
            },
        })
    return out
