"""Big-brain escalation — Phase 4.

One spoken trigger ("use the big brain") routes the CURRENT turn to a stronger
model, then control returns to local. Providers in `brain.big` are tried in
order (subscription CLI or API key); the first that answers wins. Every call is
metered to brain/usage.jsonl and the monthly cap is enforced.

    esc = Escalation(brain_cfg)
    async for sentence in esc.stream(text, history, persona=..., discipline=...,
                                     touched_tags={"private"}):
        ...
    if not esc.answered_big:
        # nothing cloud-side worked (or policy refused) — caller runs local
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from . import policy
from .config import BrainCfg, env_value, load_jarvis_json
from .core import _SENTENCE_END, _ThinkFilter, build_messages
from .providers import anthropic as anthropic_p
from .providers import cli_bridge, openai_compat


def _phrases() -> list[str]:
    tp = (load_jarvis_json().get("trigger_phrases") or {}).get("big_brain") or []
    return [str(p).strip().lower() for p in tp if str(p).strip()]


def detect(text: str) -> tuple[str, bool]:
    """(text_without_trigger, wanted). The trigger may sit anywhere in the
    utterance; strip its first occurrence and the filler around it."""
    low = text.lower()
    for p in _phrases():
        i = low.find(p)
        if i != -1:
            out = (text[:i] + text[i + len(p):]).strip(" ,.:;-—\t\n")
            return (out or text), True
    return text, False


async def _sentences(source: AsyncIterator[str]) -> AsyncIterator[str]:
    think = _ThinkFilter()
    buf = ""
    async for delta in source:
        s = think.feed(delta)
        if not s:
            continue
        buf += s
        while True:
            m = _SENTENCE_END.search(buf)
            if not m:
                break
            sent, buf = buf[: m.start()].strip(), buf[m.end():]
            if sent:
                yield sent
    if buf.strip():
        yield buf.strip()


class Escalation:
    def __init__(self, brain_cfg: BrainCfg) -> None:
        self.cfg = brain_cfg
        self.answered_big = False
        self.provider_label = ""
        self.errors: list[str] = []

    def _open(self, prov, messages: list[dict]):
        """Return (async source of text deltas, spoken label)."""
        if prov.kind == "cli":
            if not cli_bridge.available(prov.cli):
                raise cli_bridge.CliBridgeError(f"{prov.cli} is not installed")
            return (
                cli_bridge.run_cli(
                    prov.cli, messages[-1]["content"],
                    system=messages[0]["content"], model=prov.model,
                ),
                f"the {prov.cli} big brain",
            )
        key = env_value(prov.api_key_env)
        if not key:
            raise RuntimeError(f"no API key in {prov.api_key_env or '(unset)'}")
        if prov.provider == "anthropic":
            return (
                anthropic_p.chat_stream(messages, model=prov.model, api_key=key),
                f"Claude ({prov.model})",
            )
        return (
            openai_compat.chat_stream(
                messages, model=prov.model, api_key=key,
                provider=prov.provider, base_url=prov.base_url,
            ),
            f"{prov.provider} ({prov.model})",
        )

    async def stream(
        self,
        user_text: str,
        history: list[dict],
        *,
        persona: str,
        discipline: str,
        touched_tags: set[str] | None = None,
    ) -> AsyncIterator[str]:
        refusal = policy.escalation_refusal(self.cfg, touched_tags or set())
        if refusal:
            self.errors.append(refusal)
            yield refusal
            return

        messages = build_messages(
            user_text, history, persona=persona, discipline=discipline
        )
        for prov in self.cfg.big:
            try:
                source, label = self._open(prov, messages)
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"{prov.label}: {e}")
                continue
            out: list[str] = []
            try:
                first = True
                async for sent in _sentences(source):
                    if first:
                        yield f"Big brain here, via {label}."
                        first = False
                    out.append(sent)
                    yield sent
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"{prov.label}: {e}")
                if out:
                    yield "The big brain cut out mid-answer."
                continue
            if not out:
                self.errors.append(f"{prov.label}: empty reply")
                continue
            est = policy.record_usage(
                provider=prov.provider or prov.cli, model=prov.model,
                kind=prov.kind, in_chars=len(str(messages)),
                out_chars=len(" ".join(out)),
            )
            self.answered_big = True
            self.provider_label = label
            self._last_cost = est
            return

        yield ("The big brain didn't come through, so here's my local take "
               "instead.")
