"""brain/server.py — a thin HTTP front for the local brain.

Phase 1 stub. The Android client (Phase 8) POSTs turns here over Tailscale; for
now this just proves the shape and gives the desktop something to curl.

    GET  /health              -> {"ok": true, "model": "..."}
    POST /turn                -> text/event-stream
         body: {"text": "...", "history": [{"role","content"}, ...]}
         each speakable sentence arrives as its own `data:` frame;
         the stream ends with an `event: done` frame (or `event: error`).

Stdlib only (http.server + asyncio). Serialised, one turn at a time — this is
not the production surface, it's a bring-up aid.

    python -m jarvis_brain server [--host 127.0.0.1] [--port 8765]
"""
from __future__ import annotations

import asyncio
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import core
from .config import ConfigError, load_brain_cfg, load_persona
from .sessions import SessionLog

_DISCIPLINE = "Spoken style: short sentences, contractions, no markdown."


def _sse(payload: str, *, event: str | None = None) -> bytes:
    """One SSE frame. Multi-line payloads get one `data:` line each (spec)."""
    lines = [f"event: {event}"] if event else []
    lines += [f"data: {ln}" for ln in payload.split("\n")]
    return ("\n".join(lines) + "\n\n").encode("utf-8")


def _collect_turn(text: str, history: list[dict], *, brain_cfg, persona, emit) -> None:
    """Drive core.run_turn to completion on a private event loop, handing each
    finished sentence to `emit` as it lands."""
    async def go() -> None:
        async for sentence in core.run_turn(
            text, history, brain_cfg=brain_cfg, persona=persona,
            discipline=_DISCIPLINE,
        ):
            emit(sentence)

    asyncio.run(go())


class _Handler(BaseHTTPRequestHandler):
    server_version = "jarvis-brain/0.1"
    protocol_version = "HTTP/1.1"

    # -- helpers ------------------------------------------------------------ #
    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:  # noqa: A002 - stdlib signature
        sys.stderr.write("[server] " + (fmt % args) + "\n")

    # -- routes ----------------------------------------------------------- #
    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            self._json(200, {"ok": True, "model": self.server.brain_cfg.local.model})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/turn":
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            self._json(400, {"error": "body must be JSON"})
            return

        text = (payload.get("text") or "").strip()
        if not text:
            self._json(400, {"error": "missing 'text'"})
            return
        history = [
            t for t in (payload.get("history") or [])
            if isinstance(t, dict) and t.get("role") in ("user", "assistant")
        ]

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        parts: list[str] = []

        def emit(sentence: str) -> None:
            parts.append(sentence)
            self.wfile.write(_sse(sentence))
            self.wfile.flush()

        try:
            _collect_turn(
                text, history,
                brain_cfg=self.server.brain_cfg,
                persona=self.server.persona,
                emit=emit,
            )
        except Exception as e:  # noqa: BLE001 - report to the client, keep serving
            self.wfile.write(_sse(str(e), event="error"))
            self.wfile.flush()
            return

        reply = " ".join(parts).strip()
        if reply:
            self.server.session.append(text, reply)
        self.wfile.write(_sse("end", event="done"))
        self.wfile.flush()


def serve(host: str = "127.0.0.1", port: int = 8765) -> int:
    try:
        cfg = load_brain_cfg(required=True)
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 1

    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.brain_cfg = cfg
    httpd.persona = load_persona()
    httpd.session = SessionLog()
    print(
        f"jarvis-brain server on http://{host}:{port}  "
        f"(POST /turn, GET /health)  model={cfg.local.model}",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down", flush=True)
    finally:
        httpd.server_close()
    return 0
