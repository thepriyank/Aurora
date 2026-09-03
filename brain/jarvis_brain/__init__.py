"""jarvis_brain — the local-LLM agent core.

Layers (bottom up):
  providers/        raw model transports (ollama today; openai_compat/anthropic later)
  config.py         loads config/models.yaml + finds the repo root and CLAUDE.md
  core.py           run_turn(): system prompt -> provider -> streamed sentences
  local_brain.py    a WarmBrain-compatible adapter so vendor/backtalk can use it unchanged
  configure.py      the first-run wizard (picks/pulls the local model, writes models.yaml)

core.py has NO dependency on backtalk and is the unit to test in isolation.
"""

__version__ = "0.1.0"
