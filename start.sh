#!/usr/bin/env bash
# start.sh — launch the Jarvis voice line (macOS / Linux).
#
#   ./start.sh              # voice mode (default)
#   ./start.sh voice
#   ./start.sh chat         # text REPL against the local brain, no mic
#   ./start.sh configure    # (re)run the local-LLM setup wizard
#   ./start.sh overlay      # desktop 3D avatar overlay (separate process)
#
# First run (or whenever the brain isn't ready) runs the setup wizard first.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRAIN="$ROOT/brain"
BACKTALK="$ROOT/vendor/backtalk"
MODE="${1:-voice}"

command -v uv >/dev/null 2>&1 || { echo "Missing 'uv': https://github.com/astral-sh/uv"; exit 1; }

( cd "$BRAIN" && uv sync --quiet )

brain() { ( cd "$BRAIN" && uv run python -m jarvis_brain "$@" ); }

if [ "$MODE" = "configure" ]; then brain configure; exit $?; fi

if [ "$MODE" = "overlay" ]; then
  command -v npm >/dev/null 2>&1 || { echo "Missing 'npm': https://nodejs.org"; exit 1; }
  cd "$ROOT/overlay"
  [ -d node_modules ] || { echo "Installing overlay deps (one-time)..."; npm install; }
  exec npm start
fi

if [ "$MODE" = "chat" ]; then
  brain check >/dev/null 2>&1 || brain configure || exit 1
  exec bash -c "cd '$BRAIN' && uv run python -m jarvis_brain chat"
fi

if ! brain check >/dev/null 2>&1; then
  echo "Setting up the local LLM..."
  brain configure || { echo "Setup did not finish."; exit 1; }
fi

[ -d "$BACKTALK" ] || { echo "vendor/backtalk is missing. Run the Phase 0 import first."; exit 1; }

BT_JSON="$BACKTALK/backtalk.json"
if [ ! -f "$BT_JSON" ]; then
  NAME="Aurora"
  ALIASES="[]"
  if [ -f "$ROOT/config/jarvis.json" ]; then
    NAME="$(python3 -c "import json,sys;print(json.load(open('$ROOT/config/jarvis.json')).get('name','Aurora'))" 2>/dev/null || echo Aurora)"
    ALIASES="$(python3 -c "import json,sys;print(json.dumps(json.load(open('$ROOT/config/jarvis.json')).get('nicknames',[])))" 2>/dev/null || echo '[]')"
  fi
  cat > "$BT_JSON" <<EOF
{
  "brain": "local",
  "agent_dir": "$ROOT",
  "name": "$NAME",
  "aliases": $ALIASES,
  "ptt_key": "home",
  "stt_model": "small.en",
  "signals_dir": "$BACKTALK"
}
EOF
  echo "wrote vendor/backtalk/backtalk.json (brain=local, agent_dir=$ROOT)"
fi

echo "Starting the voice line (Ctrl-C to hang up)..."
exec bash -c "cd '$BACKTALK' && uv run python -m backtalk.main"
