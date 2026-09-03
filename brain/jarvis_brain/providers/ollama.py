"""Ollama transport — native /api endpoints (not the OpenAI-compat shim).

Native gives us `keep_alive` and streaming NDJSON with the least ceremony.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx


class OllamaError(RuntimeError):
    pass


class OllamaDown(OllamaError):
    """The server didn't answer — it's probably not running."""


@dataclass
class OllamaClient:
    base_url: str = "http://localhost:11434"
    # generous: first token on a cold model can take a while
    connect_timeout: float = 3.0
    read_timeout: float = 300.0

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    # -- health / inventory -------------------------------------------------- #
    async def is_up(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.connect_timeout) as c:
                r = await c.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(f"{self.base_url}/api/tags")
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, OSError) as e:
            raise OllamaDown(f"cannot reach Ollama at {self.base_url}: {e}") from e
        return sorted(m["name"] for m in data.get("models", []) if m.get("name"))

    async def has_model(self, model: str) -> bool:
        names = await self.list_models()
        # accept "qwen3:8b" matching a listed "qwen3:8b"; also bare "qwen3"
        return model in names or any(n.split(":", 1)[0] == model for n in names)

    async def pull(
        self, model: str, on_progress: Callable[[str], None] | None = None
    ) -> None:
        """Blocking-until-done model download. Streams status lines to
        `on_progress` (e.g. print) so the wizard can show life."""
        timeout = httpx.Timeout(self.connect_timeout, read=None)
        try:
            async with httpx.AsyncClient(timeout=timeout) as c:
                async with c.stream(
                    "POST", f"{self.base_url}/api/pull",
                    json={"model": model, "stream": True},
                ) as resp:
                    resp.raise_for_status()
                    last = ""
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        evt = json.loads(line)
                        if evt.get("error"):
                            raise OllamaError(evt["error"])
                        status = evt.get("status", "")
                        total, done = evt.get("total"), evt.get("completed")
                        if total and done:
                            pct = 100 * done / total
                            msg = f"{status}  {pct:5.1f}%  ({done/1e6:.0f}/{total/1e6:.0f} MB)"
                        else:
                            msg = status
                        if msg and msg != last and on_progress:
                            on_progress(msg)
                            last = msg
        except (httpx.HTTPError, OSError) as e:
            raise OllamaDown(f"pull failed for {model!r}: {e}") from e

    # -- inference --------------------------------------------------------- #
    async def chat_stream(
        self,
        messages: list[dict],
        *,
        model: str,
        keep_alive: object = -1,
        temperature: float = 0.7,
        num_ctx: int | None = None,
        stop_check: Callable[[], bool] | None = None,
    ) -> AsyncIterator[str]:
        """Yield text deltas from /api/chat. `stop_check` lets the caller
        abort mid-stream (used for barge-in / interrupt)."""
        options: dict = {"temperature": temperature}
        if num_ctx:
            options["num_ctx"] = num_ctx
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": keep_alive,
            "options": options,
        }
        timeout = httpx.Timeout(self.connect_timeout, read=self.read_timeout)
        try:
            async with httpx.AsyncClient(timeout=timeout) as c:
                async with c.stream(
                    "POST", f"{self.base_url}/api/chat", json=payload
                ) as resp:
                    if resp.status_code == 404:
                        raise OllamaError(
                            f"model {model!r} is not pulled "
                            f"(run: ollama pull {model})"
                        )
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", "replace")
                        detail = body.strip()
                        try:
                            detail = json.loads(body).get("error", detail)
                        except ValueError:
                            pass
                        low = detail.lower()
                        if "out of memory" in low or "unable to allocate" in low:
                            raise OllamaError(
                                f"{model!r} needs more RAM/VRAM than is free right "
                                f"now. Try a smaller model (e.g. llama3.2:3b, "
                                f"qwen3:4b) via `python -m jarvis_brain configure`, "
                                f"or free memory. [ollama: {detail[:200]}]"
                            )
                        raise OllamaError(
                            f"ollama returned {resp.status_code}: {detail[:400]}"
                        )
                    async for line in resp.aiter_lines():
                        if stop_check and stop_check():
                            return
                        if not line.strip():
                            continue
                        evt = json.loads(line)
                        if evt.get("error"):
                            raise OllamaError(evt["error"])
                        chunk = (evt.get("message") or {}).get("content", "")
                        if chunk:
                            yield chunk
                        if evt.get("done"):
                            return
        except httpx.ConnectError as e:
            raise OllamaDown(
                f"cannot reach Ollama at {self.base_url} — is `ollama serve` running?"
            ) from e
        except (httpx.HTTPError, OSError) as e:
            raise OllamaError(f"chat stream failed: {e}") from e
