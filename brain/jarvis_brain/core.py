"""run_turn() — the local agent loop, one turn at a time.

Input:  the user's text + prior turns + the persona.
Output: complete sentences, streamed, ready to hand straight to TTS.

No backtalk import here on purpose: this is the unit that must be testable
with nothing but Ollama running (`python -m jarvis_brain chat`).

Tools, memory retrieval and cloud escalation are later phases. Today this is
persona + conversation window -> local model -> spoken sentences.
"""
from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable

from .config import BrainCfg
from .providers.ollama import OllamaClient

# Same rule backtalk's mouth expects: break after . ! ? followed by whitespace.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
# Reasoning models (qwen3, deepseek-r1, ...) emit a visible chain of thought.
# It must never be spoken. Strip whole <think>…</think> spans, and while the
# opening tag is still unmatched, withhold everything after it.
_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


class _ThinkFilter:
    """Streaming remover of <think>…</think>. Feed deltas, get back only the
    speakable text seen so far."""

    def __init__(self) -> None:
        self._in_think = False
        self._carry = ""  # holds a partial tag straddling two deltas

    def feed(self, delta: str) -> str:
        buf = self._carry + delta
        self._carry = ""
        out = []
        while buf:
            if self._in_think:
                idx = buf.find(_THINK_CLOSE)
                if idx == -1:
                    # keep a tail that might be a split "</think>"
                    self._carry = _tag_tail(buf, _THINK_CLOSE)
                    return "".join(out)
                buf = buf[idx + len(_THINK_CLOSE):]
                self._in_think = False
            else:
                idx = buf.find(_THINK_OPEN)
                if idx == -1:
                    tail = _tag_tail(buf, _THINK_OPEN)
                    out.append(buf[: len(buf) - len(tail)])
                    self._carry = tail
                    return "".join(out)
                out.append(buf[:idx])
                buf = buf[idx + len(_THINK_OPEN):]
                self._in_think = True
        return "".join(out)


def _tag_tail(s: str, tag: str) -> str:
    """Longest suffix of `s` that is a prefix of `tag` (a tag split across
    deltas). Empty string if none."""
    for k in range(min(len(s), len(tag) - 1), 0, -1):
        if tag.startswith(s[-k:]):
            return s[-k:]
    return ""


def build_messages(
    user_text: str,
    history: list[dict] | None,
    *,
    persona: str,
    discipline: str = "",
) -> list[dict]:
    system = persona.strip()
    if discipline.strip():
        system = f"{system}\n\n---\n{discipline.strip()}"
    msgs: list[dict] = [{"role": "system", "content": system}]
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": user_text})
    return msgs


async def run_turn(
    user_text: str,
    history: list[dict] | None = None,
    *,
    brain_cfg: BrainCfg,
    persona: str,
    discipline: str = "",
    stop_check: Callable[[], bool] | None = None,
) -> AsyncIterator[str]:
    """Yield complete, speakable sentences for one user turn (local model)."""
    lc = brain_cfg.local
    if lc.provider != "ollama":
        raise NotImplementedError(f"local provider {lc.provider!r} not wired yet")

    client = OllamaClient(base_url=lc.base_url)
    messages = build_messages(
        user_text, history, persona=persona, discipline=discipline
    )
    think = _ThinkFilter()
    buf = ""

    async for delta in client.chat_stream(
        messages,
        model=lc.model,
        keep_alive=lc.keep_alive,
        temperature=lc.temperature,
        num_ctx=lc.context,
        stop_check=stop_check,
    ):
        speakable = think.feed(delta)
        if not speakable:
            continue
        buf += speakable
        while True:
            m = _SENTENCE_END.search(buf)
            if not m:
                break
            sentence, buf = buf[: m.start()].strip(), buf[m.end():]
            if sentence:
                yield sentence

    tail = buf.strip()
    if tail:
        yield tail
