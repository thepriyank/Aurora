"""The permission gate + dispatcher.

Every tool call the model makes goes through Dispatcher.__call__:

  never   -> blocked outright, logged, the model is told no
  auto    -> runs immediately
  confirm -> routed to `can_use_tool` (backtalk's spoken gate, or a typed
             prompt in the REPL). No gate attached + not auto-approving ->
             denied, because a side effect with nobody to ask is a no.

Both the decision and the outcome are appended to brain/audit.jsonl.
"""
from __future__ import annotations

import inspect
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from ..config import REPO_ROOT
from .handlers import ToolError, _clip
from .jail import OutOfJail
from .registry import TOOLS, ToolsConfig

AUDIT_PATH = REPO_ROOT / "brain" / "audit.jsonl"

# A callable (sync or async) shaped like backtalk's gate:
#   can_use_tool(tool_name, tool_input, ctx) -> PermissionResult{Allow,Deny}
CanUseTool = Callable[[str, dict, dict], Any | Awaitable[Any]]


def _short_args(args: dict) -> dict:
    out = {}
    for k, v in (args or {}).items():
        out[k] = _clip(v, 300) if isinstance(v, str) else v
    return out


class Dispatcher:
    def __init__(
        self,
        cfg: ToolsConfig,
        *,
        can_use_tool: CanUseTool | None = None,
        assume: str = "deny",         # what a confirm-tier call does with no gate
        audit_path: Path | None = None,
    ) -> None:
        self.cfg = cfg
        self.can_use_tool = can_use_tool
        self.assume = assume
        self.audit_path = audit_path or AUDIT_PATH

    # -- audit ---------------------------------------------------------- #
    def _audit(self, tool: str, args: dict, tier: str, decision: str,
               outcome: str) -> None:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tool": tool,
            "args": _short_args(args),
            "tier": tier,
            "decision": decision,
            "outcome": _clip(outcome, 500),
        }
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def note(self, event: str, detail: Any) -> None:
        """Record a non-tool side effect (e.g. the memory writer) in the audit."""
        self._audit(event, {}, "auto", "allow", _clip(str(detail), 500))

    # -- decision ----------------------------------------------------- #
    async def _decide(self, name: str, args: dict, tier: str) -> tuple[str, str]:
        if tier == "never":
            return "blocked", "that action is blocked by policy"
        if tier == "auto":
            return "allow", "auto"
        # confirm
        if self.can_use_tool is not None:
            try:
                res = self.can_use_tool(name, args, {})
                if inspect.isawaitable(res):
                    res = await res
            except Exception as e:  # noqa: BLE001 - a broken gate denies
                return "denied", f"permission gate error: {e}"
            if getattr(res, "behavior", None) == "allow":
                return "allow", "confirmed"
            return "denied", getattr(res, "message", None) or "you declined"
        if self.assume == "allow":
            return "allow", "auto-approved (non-interactive)"
        return "denied", "needs confirmation and no gate is attached"

    # -- call ------------------------------------------------------- #
    async def __call__(self, name: str, args: dict | None = None) -> str:
        args = args or {}
        td = TOOLS.get(name)
        if td is None:
            self._audit(name, args, "?", "error", "unknown tool")
            return f"error: unknown tool {name!r}"
        tier = self.cfg.tier(name)
        decision, reason = await self._decide(name, args, tier)
        if decision != "allow":
            self._audit(name, args, tier, decision, reason)
            return f"[{decision}] {reason}"
        t0 = time.monotonic()
        try:
            result = td.handler(self.cfg.roots, self.cfg, **args)
        except (ToolError, OutOfJail) as e:
            self._audit(name, args, tier, decision, f"error: {e}")
            return f"error: {e}"
        except TypeError as e:
            self._audit(name, args, tier, decision, f"bad args: {e}")
            return f"error: bad arguments for {name}: {e}"
        except Exception as e:  # noqa: BLE001 - never crash the turn
            self._audit(name, args, tier, decision, f"error: {e!r}")
            return f"error: {name} failed: {e}"
        ms = int((time.monotonic() - t0) * 1000)
        self._audit(name, args, tier, decision, f"ok ({ms}ms)")
        return result
