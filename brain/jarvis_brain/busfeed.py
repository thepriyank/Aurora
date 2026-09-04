"""Signal-bus writer for a TYPED conversation — drives the desktop overlay
without STT/TTS.

backtalk owns these files during a real voice session; this writes the same
ones so the `overlay/` avatar reacts (thinking pulse, speaking glow) while
STT/TTS are still being ported to Windows/ARM64. Same contract:

    .voice_state     idle | listening | thinking | speaking
    .voice_waveform  {ts, samples:[64 floats]}   int16-scale, while speaking
"""
from __future__ import annotations

import asyncio
import json
import math
import random
import time
from pathlib import Path

from .config import REPO_ROOT, load_jarvis_json

_WAVE_HZ = 15                # matches backtalk's write rate
_CHARS_PER_SEC = 14.0        # rough spoken pace, for faking sentence duration


def bus_dir() -> Path:
    d = (load_jarvis_json().get("bus") or {}).get("signals_dir") or "vendor/backtalk"
    p = Path(d).expanduser()
    return p if p.is_absolute() else (REPO_ROOT / p)


class BusFeed:
    def __init__(self) -> None:
        self.dir = bus_dir()
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def _write(self, name: str, text: str) -> None:
        try:
            (self.dir / name).write_text(text, encoding="utf-8")
        except OSError:
            pass

    def state(self, s: str) -> None:
        self._write(".voice_state", s)

    def idle(self) -> None:
        self.state("idle")

    def _waveform(self, level: float) -> None:
        amp = max(0.0, min(1.0, level)) * 26000.0
        samples = [
            amp * (0.35 + 0.65 * random.random()) * math.sin(i / 3.0)
            for i in range(64)
        ]
        self._write(".voice_waveform",
                    json.dumps({"ts": time.time(), "samples": samples}))

    async def speak_sentence(self, sentence: str) -> None:
        """Hold 'speaking' + emit a speech-shaped waveform for about as long as
        this sentence would take to say."""
        self.state("speaking")
        dur = max(0.8, len(sentence) / _CHARS_PER_SEC)
        n = max(1, int(dur * _WAVE_HZ))
        for i in range(n):
            # gentle envelope: rise, sustain with wobble, fall
            phase = i / n
            env = math.sin(math.pi * phase) ** 0.5
            self._waveform(0.15 + 0.85 * env * (0.6 + 0.4 * random.random()))
            await asyncio.sleep(1 / _WAVE_HZ)
        self._waveform(0.04)
        await asyncio.sleep(0.12)
