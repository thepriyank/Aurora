"""Phase 4 escalation policy — when a big-brain request is refused, and the
cloud-usage ledger + monthly cap.

Every reason returns a sentence to say out loud. The local model still answers
after the refusal (offline / cap / private-note all fall back to local).
"""
from __future__ import annotations

import json
import socket
from datetime import datetime, timezone
from pathlib import Path

from .config import REPO_ROOT, BrainCfg

USAGE_PATH = REPO_ROOT / "brain" / "usage.jsonl"

# Rough INR per 1k tokens for the API path (verify against your provider's
# pricing). CLI / subscription providers cost 0 here — you've already paid.
_RATE_INR = {
    "openrouter": 0.5, "openai": 2.0, "anthropic": 2.0, "groq": 0.1,
    "together": 0.3, "deepseek": 0.1, "mistral": 0.4,
    "ollama": 0.3,  # Ollama Cloud — rough guess, check your plan's real rate
}


def is_online(timeout: float = 2.0) -> bool:
    for host, port in (("1.1.1.1", 53), ("8.8.8.8", 53)):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def month_spend_inr(path: Path = USAGE_PATH) -> float:
    if not path.exists():
        return 0.0
    ym = datetime.now().strftime("%Y-%m")
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if str(r.get("ts", "")).startswith(ym):
            total += float(r.get("est_cost_inr", 0) or 0)
    return round(total, 2)


def escalation_refusal(
    cfg: BrainCfg,
    touched_tags: set[str],
    *,
    check_online: bool = True,
) -> str | None:
    """A spoken reason to refuse escalation, or None to allow it."""
    blocked = sorted(set(cfg.never_escalate_tags) & set(touched_tags))
    if blocked:
        return (f"That touches a {blocked[0].replace('_', ' ')} note, so it stays "
                f"on this machine. I won't send it to the cloud.")
    if not cfg.big:
        return "There's no big brain set up yet. Run the setup wizard to add one."
    if check_online and not is_online():
        return "We're offline, so the big brain isn't reachable. Answering locally."
    cap = cfg.monthly_cloud_cap_inr
    if cap and month_spend_inr() >= cap:
        return "The big brain budget is used up for this month. Staying local."
    return None


def record_usage(
    *,
    provider: str,
    model: str,
    kind: str,
    in_chars: int,
    out_chars: int,
    path: Path = USAGE_PATH,
) -> float:
    """Append a row to usage.jsonl. Returns the estimated INR for this call."""
    approx_tokens = (in_chars + out_chars) / 4
    rate = 0.0 if kind == "cli" else _RATE_INR.get(provider, 1.0)
    est = round(rate * approx_tokens / 1000, 4)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider or kind,
        "model": model,
        "kind": kind,
        "approx_tokens_in": int(in_chars / 4),
        "approx_tokens_out": int(out_chars / 4),
        "est_cost_inr": est,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return est
