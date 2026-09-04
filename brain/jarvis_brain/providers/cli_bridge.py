"""Big-brain via a coding-agent CLI you're already signed into.

No API key: `claude`, `codex`, and `gemini` each run one non-interactive turn
against your existing subscription. We shell out, capture stdout, and yield it
in chunks so the sentence splitter upstream can feed TTS as usual.

This is deliberately thin. Each CLI has its own flags; if one changes, only the
table below moves.
"""
from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator

SUPPORTED = ("claude", "codex", "gemini")


class CliBridgeError(RuntimeError):
    pass


def available(cli: str) -> bool:
    return shutil.which(cli) is not None


def which_supported() -> list[str]:
    return [c for c in SUPPORTED if available(c)]


def _argv(cli: str, prompt: str, *, system: str, model: str) -> tuple[list[str], str]:
    """Return (argv, stdin_text). Most CLIs take the prompt as an arg; we fold
    the system prompt in where there's no dedicated flag."""
    exe = shutil.which(cli)
    if not exe:
        raise CliBridgeError(f"{cli!r} is not on PATH")

    if cli == "claude":
        argv = [exe, "-p", prompt, "--output-format", "text"]
        if system:
            argv += ["--append-system-prompt", system]
        if model:
            argv += ["--model", model]
        return argv, ""

    if cli == "codex":
        full = f"{system}\n\n{prompt}" if system else prompt
        argv = [exe, "exec", "--skip-git-repo-check", full]
        if model:
            argv[2:2] = ["-m", model]
        return argv, ""

    if cli == "gemini":
        full = f"{system}\n\n{prompt}" if system else prompt
        argv = [exe, "-p", full]
        if model:
            argv += ["-m", model]
        return argv, ""

    raise CliBridgeError(f"unsupported CLI {cli!r} (expected one of {SUPPORTED})")


async def run_cli(
    cli: str,
    prompt: str,
    *,
    system: str = "",
    model: str = "",
    timeout: float = 240.0,
) -> AsyncIterator[str]:
    argv, stdin_text = _argv(cli, prompt, system=system, model=model)
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if stdin_text else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as e:
        raise CliBridgeError(f"could not start {cli!r}: {e}") from e

    if stdin_text and proc.stdin:
        proc.stdin.write(stdin_text.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

    saw_output = False
    try:
        while True:
            chunk = await asyncio.wait_for(proc.stdout.read(1024), timeout=timeout)
            if not chunk:
                break
            saw_output = True
            yield chunk.decode("utf-8", "replace")
    except asyncio.TimeoutError:
        proc.kill()
        raise CliBridgeError(f"{cli!r} timed out after {int(timeout)}s")

    await proc.wait()
    if proc.returncode != 0:
        err = (await proc.stderr.read()).decode("utf-8", "replace").strip()
        raise CliBridgeError(
            f"{cli!r} exited {proc.returncode}: {err[:300] or '(no stderr)'}"
        )
    if not saw_output:
        raise CliBridgeError(f"{cli!r} produced no output")
