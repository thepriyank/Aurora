"""`python -m jarvis_brain <cmd>`

    configure [--defaults]   first-run wizard: vault, local model, big brain
    check                    exit 0 iff ready to run (used by start.ps1/.sh)
    chat                     a plain REPL against the brain (no voice)
    server [--host H --port P]  HTTP front: POST /turn (SSE), GET /health
    keys                     add / list big-brain + specialized API providers
"""
from __future__ import annotations

import asyncio
import sys


def _chat() -> int:
    # Windows consoles default to a legacy codepage; force UTF-8 so Hindi /
    # Hinglish input and output survive the REPL. (backtalk feeds text via STT,
    # not stdin, so this only matters for this dev REPL.)
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    from . import core, escalation, memory
    from .config import ConfigError, load_brain_cfg, load_persona
    from .tools import Dispatcher, load_tools_config, ollama_schemas

    try:
        cfg = load_brain_cfg(required=True)
    except ConfigError as e:
        print(f"{e}", file=sys.stderr)
        return 1

    persona = load_persona()
    history: list[dict] = []

    # A typed confirmation gate so confirm-tier tools can be exercised here the
    # same way the spoken gate does on the voice line.
    class _Allow:
        behavior = "allow"

    class _Deny:
        behavior = "deny"

        def __init__(self, msg: str) -> None:
            self.message = msg

    def _typed_gate(tool: str, args: dict, _ctx: dict):
        ans = input(f"  [confirm] run {tool} {args}? (y/N) ").strip().lower()
        return _Allow() if ans in {"y", "yes"} else _Deny("you declined at the prompt")

    tools_cfg = load_tools_config()
    dispatch = Dispatcher(tools_cfg, can_use_tool=_typed_gate)
    schemas = ollama_schemas(tools_cfg)
    print(f"chat with the local brain ({cfg.local.model}), {len(schemas)} tools. "
          f"Ctrl-C or 'exit' to quit.\n")

    disc = "Spoken style: short sentences, no markdown."

    async def turn(text: str) -> None:
        reply: list[str] = []
        asked, want_big = escalation.detect(text)
        hint, tags = memory.recall_context(asked, tools_cfg.roots["vault"])

        if want_big:
            esc = escalation.Escalation(cfg)
            async for sentence in esc.stream(asked, history, persona=persona,
                                             discipline=disc, touched_tags=tags):
                print(f"  {sentence}", flush=True)
                reply.append(sentence)
            if esc.answered_big:
                history.append({"role": "user", "content": asked})
                history.append({"role": "assistant", "content": " ".join(reply).strip()})
                return
            text = asked  # refused / all providers failed -> local answers

        async for sentence in core.run_turn(
            text, history, brain_cfg=cfg, persona=persona, discipline=disc,
            tools=schemas, dispatch=dispatch, extra_context=hint,
        ):
            print(f"  {sentence}", flush=True)
            reply.append(sentence)
        joined = " ".join(reply).strip()
        if joined:
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": joined})
            written = await memory.remember(
                text, joined, brain_cfg=cfg, vault=tools_cfg.roots["vault"])
            if written:
                dispatch.note("memory.remember", written)
                print(f"  · remembered: {'; '.join(written)}", flush=True)

    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if text.lower() in {"exit", "quit"}:
            return 0
        if not text:
            continue
        try:
            asyncio.run(turn(text))
        except Exception as e:  # noqa: BLE001 - REPL: show and keep going
            print(f"  ! {e}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    cmd = argv[0] if argv else "configure"
    rest = argv[1:]

    if cmd == "configure":
        from .configure import main as wiz
        return wiz(rest)
    if cmd == "check":
        from .configure import check
        return check()
    if cmd == "chat":
        return _chat()
    if cmd == "keys":
        from .configure import run_keys
        return run_keys()
    if cmd == "server":
        from .server import serve
        host, port = "127.0.0.1", 8765
        for i, arg in enumerate(rest):
            if arg == "--host" and i + 1 < len(rest):
                host = rest[i + 1]
            elif arg == "--port" and i + 1 < len(rest):
                port = int(rest[i + 1])
        return serve(host, port)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
