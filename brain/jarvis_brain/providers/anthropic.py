"""Anthropic Messages API streaming — the API-key path to Claude when you don't
want to (or can't) use the `claude` CLI bridge.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

_BASE = "https://api.anthropic.com/v1"
_VERSION = "2023-06-01"


class AnthropicError(RuntimeError):
    pass


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    system = "\n\n".join(
        m["content"] for m in messages if m.get("role") == "system" and m.get("content")
    )
    turns = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    return system, turns


async def chat_stream(
    messages: list[dict],
    *,
    model: str,
    api_key: str,
    max_tokens: int = 2048,
    temperature: float = 0.7,
    timeout: float = 120.0,
) -> AsyncIterator[str]:
    if not api_key:
        raise AnthropicError("missing API key")
    system, turns = _split_system(messages)
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "messages": turns or [{"role": "user", "content": "Hello"}],
    }
    if system:
        payload["system"] = system
    headers = {
        "x-api-key": api_key,
        "anthropic-version": _VERSION,
        "content-type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=timeout)) as c:
            async with c.stream(
                "POST", f"{_BASE}/messages", json=payload, headers=headers
            ) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise AnthropicError(
                        f"anthropic returned {resp.status_code}: {body[:300]}"
                    )
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        evt = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    if evt.get("type") == "content_block_delta":
                        piece = (evt.get("delta") or {}).get("text") or ""
                        if piece:
                            yield piece
                    elif evt.get("type") == "message_stop":
                        return
    except httpx.HTTPError as e:
        raise AnthropicError(f"anthropic request failed: {e}") from e
