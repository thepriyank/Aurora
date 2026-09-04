"""Post-turn durable-fact extraction — Phase 2 write policy.

After a turn, one cheap local call decides whether anything worth keeping for
months was said (a stable preference, a personal fact, a project detail). Those
lines are appended to the right vault note with a source / confidence /
sensitivity trailer. Small talk and questions are dropped. A line that
contradicts an existing one is added as a dated correction, never an overwrite.

Failure here never touches the spoken turn — the caller guards it and we also
swallow everything internally.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

from .config import BrainCfg, device_name
from .providers.ollama import OllamaClient

_SYS = (
    "You extract only DURABLE facts worth remembering for months: stable "
    "preferences, personal facts, project details, people the user knows. "
    "Ignore questions, chit-chat, and momentary state. Reply with ONLY a JSON "
    "array. Each item: {\"fact\": one short third-person sentence, "
    "\"category\": profile|preference|project|people|other, "
    "\"sensitivity\": normal|private|health|finance_personal|family, "
    "\"confidence\": number 0..1}. Reply [] if nothing durable.\n"
    "Examples:\n"
    "User said: Remember I take my coffee black. -> "
    "[{\"fact\":\"Takes coffee black\",\"category\":\"preference\","
    "\"sensitivity\":\"normal\",\"confidence\":0.95}]\n"
    "User said: what's the weather like? -> []"
)

_NOTE_FOR = {
    "preference": "People/Me.md",
    "profile": "People/Me.md",
    "people": "People/Notes.md",
    "project": "Projects/Notes.md",
    "other": None,  # -> today's daily note
}
_MIN_CONFIDENCE = 0.5


_STOP = {
    "what", "when", "where", "which", "with", "your", "you", "the", "and", "for",
    "that", "this", "have", "how", "was", "are", "did", "does", "tell", "about",
    "check", "notes", "note", "please", "from", "into", "them", "then", "there",
}


_SENS_TAGS = ("private", "health", "finance_personal", "family")
_SENS_RE = re.compile(r"sensitivity:\s*([a-z_]+)", re.IGNORECASE)


def recall_context(
    user_text: str, vault: Path, *, max_lines: int = 6
) -> tuple[str, set[str]]:
    """Cheap pre-turn retrieval. Returns (hint_block, sensitivity_tags) where
    the tags are any never-escalate markers on the matched notes/lines (so the
    escalation policy can keep a private turn local). Never raises."""
    hits: list[str] = []
    tags: set[str] = set()
    try:
        words = {
            w.lower() for w in re.findall(r"[A-Za-z0-9]{4,}", user_text)
        } - _STOP
        if not words or not vault.is_dir():
            return "", tags
        rx = re.compile("|".join(re.escape(w) for w in words), re.IGNORECASE)
        for md in vault.rglob("*.md"):
            if len(hits) >= max_lines:
                break
            if any(seg in {".git", ".obsidian", ".trash"} for seg in md.parts):
                continue
            stem_tag = md.stem.lower()
            try:
                text = md.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            file_tags = {t for t in _SENS_TAGS if t in stem_tag or f"#{t}" in text}
            for line in text.splitlines():
                raw = line.strip()
                s = raw.lstrip("-*# ").split("<!--")[0].strip()
                if len(s) > 3 and rx.search(s):
                    hits.append(f"- {s}  ({md.stem})")
                    tags |= file_tags
                    m = _SENS_RE.search(raw)
                    if m and m.group(1).lower() in _SENS_TAGS:
                        tags.add(m.group(1).lower())
                    if len(hits) >= max_lines:
                        break
    except Exception:  # noqa: BLE001 - retrieval is best-effort
        return "", set()
    hint = ("Notes that may be relevant to this turn:\n" + "\n".join(hits)) if hits else ""
    return hint, tags


def recall_hint(user_text: str, vault: Path, *, max_lines: int = 6) -> str:
    return recall_context(user_text, vault, max_lines=max_lines)[0]


def _daily_note(vault: Path) -> Path:
    # per-device shard (Phase 3); the nightly job merges into <date>.md
    return vault / "01 - Daily Notes" / f"{date.today():%Y-%m-%d}.{device_name()}.md"


def _target(vault: Path, category: str) -> Path:
    rel = _NOTE_FOR.get(category, None)
    return (vault / rel) if rel else _daily_note(vault)


def _extract_json_array(text: str) -> list:
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        v = json.loads(m.group(0))
        return v if isinstance(v, list) else []
    except ValueError:
        return []


def _similar_line_exists(body: str, fact: str) -> tuple[bool, bool]:
    """(exact_dup, near_contradiction) against existing bullet lines."""
    norm = fact.strip().lower()
    for line in body.splitlines():
        b = line.lstrip("-* ").split("<!--")[0].strip().lower()
        if not b:
            continue
        if b == norm:
            return True, False
        if SequenceMatcher(None, b, norm).ratio() > 0.6:
            return False, True
    return False, False


def _append(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists()
    with path.open("a", encoding="utf-8") as f:
        if fresh:
            f.write(f"# {path.stem}\n\n")
        f.write(line + "\n")


async def remember(
    user_text: str,
    reply_text: str,
    *,
    brain_cfg: BrainCfg,
    vault: Path,
) -> list[str]:
    """Return a list of 'note: fact' strings actually written (for the audit log)."""
    lc = brain_cfg.local
    if lc.provider != "ollama":
        return []
    client = OllamaClient(base_url=lc.base_url)
    try:
        msg = await client.chat(
            [
                {"role": "system", "content": _SYS},
                {"role": "user",
                 "content": f"User said: {user_text}\nAssistant said: {reply_text}\nJSON:"},
            ],
            model=lc.model, keep_alive=lc.keep_alive, temperature=0.0,
            num_ctx=lc.context,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[memory] extract call failed: {e}", file=sys.stderr)
        return []

    written: list[str] = []
    for item in _extract_json_array(msg.get("content", "") or ""):
        if not isinstance(item, dict):
            continue
        fact = str(item.get("fact", "")).strip()
        if not fact:
            continue
        try:
            conf = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0.0
        if conf < _MIN_CONFIDENCE:
            continue
        category = str(item.get("category", "other")).lower()
        sens = str(item.get("sensitivity", "normal")).lower()
        path = _target(vault, category)
        body = path.read_text(encoding="utf-8") if path.exists() else ""
        exact, contra = _similar_line_exists(body, fact)
        if exact:
            continue
        trailer = (f"  <!-- source: session {date.today():%Y-%m-%d}; "
                   f"confidence: {conf:.2f}; sensitivity: {sens} -->")
        if contra:
            line = f"- correction ({date.today():%Y-%m-%d}): {fact}{trailer}"
        else:
            line = f"- {fact}{trailer}"
        try:
            _append(path, line)
            written.append(f"{path.name}: {fact}")
        except OSError as e:
            print(f"[memory] could not write {path}: {e}", file=sys.stderr)
    return written
