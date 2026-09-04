# BIG_BRAIN.md — escalation & specialized providers (Phase 4)

Every turn runs on the **local** model. Saying a trigger phrase
(`config/jarvis.json` → `trigger_phrases.big_brain`, e.g. *"use the big brain"*,
*"बड़ा मॉडल इस्तेमाल करो"*) sends **that one turn** to a stronger model, then it
reverts to local. There is no automatic escalation.

## Two ways to have a big brain

Configured in `config/models.yaml` → `brain.big`, a list tried in order (first
that answers wins).

### 1. A subscription you already pay for — `kind: cli`

Shells out to a coding-agent CLI you're signed into. **No API key.** Cost is
your existing plan.

```yaml
big:
  - kind: cli
    cli: claude        # claude | codex | gemini
    # model: claude-opus-5   # optional
```

| `cli` | CLI it calls | Get it |
|---|---|---|
| `claude` | Claude Code (`claude -p`) — Claude Pro/Max or Console | <https://claude.com/claude-code> |
| `codex`  | OpenAI Codex (`codex exec`) — ChatGPT Plus/Pro | `npm i -g @openai/codex` |
| `gemini` | Gemini CLI (`gemini -p`) — Google account | `npm i -g @google/gemini-cli` |

The wizard auto-detects whichever of these are on your `PATH`.

### 2. An API key — `kind: api`

```yaml
big:
  - kind: api
    provider: openrouter    # openrouter | openai | anthropic | groq | deepseek | mistral | together
    model: deepseek/deepseek-chat
    api_key_env: OPENROUTER_API_KEY     # the NAME of a var in .env
    # base_url: https://openrouter.ai/api/v1   # optional; default per provider
```

`provider: anthropic` uses the Anthropic Messages API; everything else uses the
OpenAI-compatible `/v1/chat/completions`. For any other OpenAI-compatible host,
set `provider` to its name and give an explicit `base_url`.

### Mixing / fallback

List as many as you like — a subscription first, an API key as backup:

```yaml
big:
  - { kind: cli, cli: claude }
  - { kind: api, provider: openrouter, model: deepseek/deepseek-chat, api_key_env: OPENROUTER_API_KEY }
```

## Guardrails

- **Privacy tags are law.** If the turn's retrieved notes carry `private`,
  `health`, `finance_personal`, or `family` (`brain.never_escalate_tags`), the
  request is refused out loud and stays local.
- **Offline** → refused, local answers.
- **Monthly cap** — `brain.monthly_cloud_cap_inr`. Summed from
  `brain/usage.jsonl` for the current month. `kind: cli` calls are logged at
  cost 0 (you already pay the subscription), so the cap really guards API spend.
- Every escalation appends a row to `brain/usage.jsonl`:
  `{ts, provider, model, kind, approx_tokens_in/out, est_cost_inr}`.
- If a provider errors, the next one in the list is tried; if all fail, the
  local model answers instead.

## Specialized providers (image / video / audio / …)

Keys for **non-chat** work live under `specialized:` in `models.yaml`, keyed by
a capability name **you choose** (`image`, `video`, `music`, `ocr`, `embed`, …):

```yaml
specialized:
  image:
    provider: kie.ai
    base_url: https://api.kie.ai
    api_key_env: KIE_API_KEY
    model: flux-1.1-pro
  video:
    provider: higgsfield
    base_url: https://platform.higgsfield.ai/api
    api_key_env: HIGGSFIELD_API_KEY
```

The secret itself goes in `.env` under `api_key_env` — never in `models.yaml`.
Known presets in the wizard: **kie.ai, higgsfield, fal, replicate, elevenlabs,
openai** — or type your own `provider` + `base_url` + env-var name.

Add or edit them any time:

```
python -m jarvis_brain keys
```

These are **registered** now; the tools that call them (generate an image, a
video, narration) land in a later phase. `python -m jarvis_brain check` reports
which have their key set.

## Commands

| | |
|---|---|
| `python -m jarvis_brain configure` | full first-run wizard (vault, local model, big brain, specialized) |
| `python -m jarvis_brain keys` | add / list big-brain + specialized providers only |
| `python -m jarvis_brain check` | prints local model, vault, big brain, specialized key status |
