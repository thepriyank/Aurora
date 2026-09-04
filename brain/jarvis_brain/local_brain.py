"""LocalBrain — a WarmBrain-shaped adapter over the local model.

vendor/backtalk/backtalk/main.py builds its whole session around one object
with this surface:

    WarmBrain(model=..., can_use_tool=..., resume_id=...)
      .model            str
      .session          {"turns","out_tokens","in_tokens","cost"}
      async start()
      async stop()
      async ask_stream(text) -> async iterator[str]        # complete sentences
      async interrupt()
      async reset_turn(timeout=...)
      async set_permission_mode(mode)
      async command(cmd) -> str                            # /clear /compact /effort
      async context_usage() -> obj | None

We provide exactly that, backed by jarvis_brain.core.run_turn against Ollama.
Conversation memory is a plain in-process list of turns (no SDK session, no
resume yet). Personality comes from the agent_dir's CLAUDE.md, same as the
Claude path — backtalk stays the medium, never the character.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

from . import core, escalation, memory
from .config import load_brain_cfg, load_persona, persona_from_text
from .providers.ollama import OllamaClient, OllamaDown
from .sessions import SessionLog
from .tools import Dispatcher, load_tools_config, ollama_schemas

_MAX_HISTORY_TURNS = 24  # user+assistant pairs kept in the window


def _persona() -> str:
    """The spoken character only — the PERSONA block, never the whole
    architecture doc (a 3B model fed the full CLAUDE.md answers *about* it).
    Prefer backtalk's configured agent_dir/CLAUDE.md, then the repo CLAUDE.md,
    then a bare identity line."""
    try:
        from backtalk.config import CFG as _BT
        agent_dir = _BT.get("agent_dir")
        if agent_dir:
            p = Path(os.path.expanduser(agent_dir)) / "CLAUDE.md"
            if p.is_file():
                block = persona_from_text(p.read_text(encoding="utf-8"))
                if block:
                    return block
    except Exception:
        pass
    return load_persona()


def _discipline() -> str:
    """backtalk's spoken-delivery discipline (write for the ear, no markdown,
    say numbers as words...). If backtalk isn't importable, a short stand-in."""
    try:
        from backtalk.config import DISCIPLINE
        return DISCIPLINE
    except Exception:
        return (
            "Your reply is spoken aloud by a text-to-speech engine. Write for "
            "the ear: short conversational sentences, contractions, no markdown, "
            "no lists, no code blocks, no URLs, no file paths. Say numbers as "
            "words. Answer directly."
        )


class LocalBrain:
    def __init__(
        self,
        model: str | None = None,
        can_use_tool=None,
        resume_id: str | None = None,
    ) -> None:
        self._cfg = load_brain_cfg()  # raises ConfigError if the wizard never ran
        # An explicit --model override wins; else models.yaml.
        self.model = model or self._cfg.local.model
        self._can_use_tool = can_use_tool  # unused until Phase 2 (tools)
        if resume_id:
            # local mode has no SDK session to reattach to yet
            pass
        self.session = {"turns": 0, "out_tokens": 0, "in_tokens": 0, "cost": 0.0}
        self._history: list[dict] = []
        self._persona = _persona()
        self._discipline = _discipline()
        self._session = SessionLog()  # transcript -> vault/04 - Sessions/<date>.md
        # Phase 2: native tools + the spoken confirmation gate (can_use_tool is
        # backtalk's make_permission_gate, or None outside the voice line).
        self._tools_cfg = load_tools_config()
        self._dispatch = Dispatcher(self._tools_cfg, can_use_tool=can_use_tool)
        self._tool_schemas = ollama_schemas(self._tools_cfg)
        self._stop = False
        self._perm_mode = "ask"

    # -- lifecycle ------------------------------------------------------- #
    async def start(self) -> None:
        client = OllamaClient(base_url=self._cfg.local.base_url)
        if not await client.is_up():
            raise OllamaDown(
                f"Ollama isn't answering at {self._cfg.local.base_url}. "
                f"Start it with `ollama serve` (or the Ollama app), then relaunch."
            )
        if not await client.has_model(self.model):
            raise OllamaDown(
                f"The model {self.model!r} isn't pulled. Run:  "
                f"ollama pull {self.model}   (or: python -m jarvis_brain configure)"
            )

    async def stop(self) -> None:
        self._history.clear()

    # -- the turn ------------------------------------------------------- #
    async def ask_stream(self, utterance: str) -> AsyncIterator[str]:
        self._stop = False
        reply_parts: list[str] = []
        vault = self._tools_cfg.roots["vault"]
        asked, want_big = escalation.detect(utterance)
        hint, tags = memory.recall_context(asked, vault)

        # Phase 4: "use the big brain" routes THIS turn to a stronger model.
        if want_big:
            esc = escalation.Escalation(self._cfg)
            async for sentence in esc.stream(
                asked, self._history,
                persona=self._persona, discipline=self._discipline,
                touched_tags=tags,
            ):
                reply_parts.append(sentence)
                yield sentence
            if esc.answered_big:
                reply = " ".join(reply_parts).strip()
                self._history.append({"role": "user", "content": asked})
                self._history.append({"role": "assistant", "content": reply})
                self._session.append(utterance, reply)
                self.session["turns"] += 1
                return
            # policy refusal or every provider failed — fall through to local
            utterance = asked

        async for sentence in core.run_turn(
            utterance,
            self._history,
            brain_cfg=self._cfg,
            persona=self._persona,
            discipline=self._discipline,
            stop_check=lambda: self._stop,
            tools=self._tool_schemas,
            dispatch=self._dispatch,
            extra_context=hint,
        ):
            reply_parts.append(sentence)
            yield sentence

        reply = " ".join(reply_parts).strip()
        if reply:
            self._history.append({"role": "user", "content": utterance})
            self._history.append({"role": "assistant", "content": reply})
            if len(self._history) > _MAX_HISTORY_TURNS * 2:
                self._history = self._history[-_MAX_HISTORY_TURNS * 2:]
            self._session.append(utterance, reply)
            await self._store_durable_facts(utterance, reply)
        # rough bookkeeping so "usage report" has something to say
        self.session["turns"] += 1
        self.session["out_tokens"] += max(1, len(reply) // 4)

    async def _store_durable_facts(self, utterance: str, reply: str) -> None:
        """Phase 2 write policy: extract durable facts and append them to the
        vault. Best-effort — a failure must never break the turn."""
        try:
            written = await memory.remember(
                utterance, reply,
                brain_cfg=self._cfg,
                vault=self._tools_cfg.roots["vault"],
            )
            if written:
                self._dispatch.note("memory.remember", written)
        except Exception as e:  # noqa: BLE001
            import sys
            print(f"[local_brain] memory step failed: {e}", file=sys.stderr)

    async def interrupt(self) -> None:
        self._stop = True

    async def reset_turn(self, timeout: float = 8.0) -> None:
        # local calls are self-contained: nothing buffered to re-align.
        self._stop = False

    async def set_permission_mode(self, backtalk_mode: str) -> None:
        self._perm_mode = backtalk_mode

    async def context_usage(self):
        return None

    async def command(self, cmd: str) -> str:
        """Voice-console slash commands. Local mode supports the ones that
        make sense; the model-tier switches are a Phase 4 ('big brain') story."""
        c = cmd.strip().lower()
        if c.startswith("/clear"):
            self._history.clear()
            return ""
        if c.startswith("/compact"):
            # cheap compaction: keep the last few turns verbatim
            self._history = self._history[-8:]
            return ""
        if c.startswith("/effort"):
            return ""  # no reasoning-effort knob on the local model here
        if c.startswith("/model"):
            # "switch to the deep model" sends a Claude id that means nothing
            # locally. Don't pretend; don't error either.
            return ""
        return ""
