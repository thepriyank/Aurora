"""run_turn() — the local agent loop, one turn at a time.

Input:  the user's text + prior turns + the persona.
Output: complete sentences, streamed, ready to hand straight to TTS.

No backtalk import here on purpose: this is the unit that must be testable
with nothing but Ollama running (`python -m jarvis_brain chat`).

Tools, memory retrieval and cloud escalation are later phases. Today this is
persona + conversation window -> local model -> spoken sentences.
"""
from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable

from .config import BrainCfg, LocalModelCfg
from .providers.ollama import OllamaClient

# Same rule backtalk's mouth expects: break after . ! ? followed by whitespace.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Appended to the system prompt only when tools are in play. Short on purpose —
# a small local model follows a tight brief.
_TOOL_GUIDANCE = (
    "You have tools. Before answering from memory about the user's preferences, "
    "past notes, or files, call vault.search or fs.search to check. Use the "
    "vault tools to save and recall notes. If a request is destructive — "
    "deleting many files, wiping or formatting a folder or disk — refuse plainly "
    "and say why; do not attempt it. Give tool paths relative to the vault or "
    "workspace."
)
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


def _parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            return v if isinstance(v, dict) else {"value": v}
        except ValueError:
            return {}
    return {}


async def _tool_rounds(
    client: OllamaClient,
    messages: list[dict],
    *,
    model: str,
    lc: LocalModelCfg,
    tools: list[dict],
    dispatch: Callable[[str, dict], Awaitable[str]],
    max_rounds: int,
) -> None:
    """Run non-streaming tool-calling rounds in place on `messages`, appending
    the model's tool_calls and each tool result, until the model stops asking
    for tools (or the round cap is hit). The final spoken answer is produced
    afterwards by the streaming pass."""
    for _ in range(max_rounds):
        msg = await client.chat(
            messages, model=model, tools=tools,
            keep_alive=lc.keep_alive, temperature=lc.temperature,
            num_ctx=lc.context,
        )
        calls = msg.get("tool_calls") or []
        if not calls:
            return
        messages.append({
            "role": "assistant",
            "content": msg.get("content", "") or "",
            "tool_calls": calls,
        })
        for call in calls:
            fn = (call.get("function") or {})
            name = fn.get("name", "")
            args = _parse_args(fn.get("arguments"))
            result = await dispatch(name, args)
            messages.append({
                "role": "tool", "tool_name": name, "content": str(result),
            })
    # cap reached: nudge the model to answer with what it has
    messages.append({
        "role": "user",
        "content": "Answer now with what you have. Do not call more tools.",
    })


async def run_turn(
    user_text: str,
    history: list[dict] | None = None,
    *,
    brain_cfg: BrainCfg,
    persona: str,
    discipline: str = "",
    stop_check: Callable[[], bool] | None = None,
    tools: list[dict] | None = None,
    dispatch: Callable[[str, dict], Awaitable[str]] | None = None,
    max_tool_rounds: int = 5,
    extra_context: str = "",
) -> AsyncIterator[str]:
    """Yield complete, speakable sentences for one user turn (local model).

    When `tools` and `dispatch` are given, the model may call tools first
    (non-streaming rounds); the spoken answer then streams as usual with the
    tool results in context.
    """
    lc = brain_cfg.local
    if lc.provider != "ollama":
        raise NotImplementedError(f"local provider {lc.provider!r} not wired yet")

    client = OllamaClient(base_url=lc.base_url)
    messages = build_messages(
        user_text, history, persona=persona, discipline=discipline
    )
    if extra_context.strip():
        messages[0]["content"] += "\n\n---\n" + extra_context.strip()

    if tools and dispatch is not None:
        messages[0]["content"] += "\n\n---\n" + _TOOL_GUIDANCE
        await _tool_rounds(
            client, messages, model=lc.model, lc=lc, tools=tools,
            dispatch=dispatch, max_rounds=max_tool_rounds,
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
