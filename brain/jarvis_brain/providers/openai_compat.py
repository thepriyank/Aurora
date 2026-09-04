"""OpenAI-compatible chat streaming — OpenRouter, Groq, OpenAI, Together, and
any endpoint that speaks `/v1/chat/completions` with SSE.

Used for the API-key flavour of the big brain (config: kind=api).
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

# Sensible default base URLs so config only needs `provider` + `model` + key.
DEFAULT_BASE = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "mistral": "https://api.mistral.ai/v1",
}


class OpenAICompatError(RuntimeError):
    pass


async def chat_stream(
    messages: list[dict],
    *,
    model: str,
    api_key: str,
    provider: str = "openrouter",
    base_url: str = "",
    temperature: float = 0.7,
    timeout: float = 120.0,
) -> AsyncIterator[str]:
    base = (base_url or DEFAULT_BASE.get(provider, "")).rstrip("/")
    if not base:
        raise OpenAICompatError(
            f"no base_url for provider {provider!r} — set base_url in models.yaml"
        )
    if not api_key:
        raise OpenAICompatError("missing API key")

    headers = {"Authorization": f"Bearer {api_key}"}
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/thepriyank/Aurora"
        headers["X-Title"] = "Jarvis"

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=timeout)) as c:
            async with c.stream(
                "POST", f"{base}/chat/completions", json=payload, headers=headers
            ) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise OpenAICompatError(
                        f"{provider} returned {resp.status_code}: {body[:300]}"
                    )
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        delta = json.loads(data)["choices"][0]["delta"]
                    except (ValueError, KeyError, IndexError):
                        continue
                    piece = delta.get("content") or ""
                    if piece:
                        yield piece
    except httpx.HTTPError as e:
        raise OpenAICompatError(f"{provider} request failed: {e}") from e
