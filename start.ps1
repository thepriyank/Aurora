<#
  start.ps1 — launch the Jarvis voice line (Windows).

  Usage:
    .\start.ps1                # voice mode (default)
    .\start.ps1 voice
    .\start.ps1 chat           # text REPL against the local brain, no mic
    .\start.ps1 configure      # (re)run the local-LLM setup wizard

  On first run (or whenever the brain isn't ready) it runs the setup wizard
  before starting the voice line.
#>
param([string]$Mode = "voice")

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Brain = Join-Path $Root "brain"
$Backtalk = Join-Path $Root "vendor\backtalk"

function Need($name, $hint) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    Write-Host "Missing '$name'. $hint" -ForegroundColor Red
    exit 1
  }
}
Need "uv" "Install: https://github.com/astral-sh/uv"

# --- brain env ---------------------------------------------------------------
Push-Location $Brain
uv sync --quiet
Pop-Location

function Brain($cmdArgs) {
  Push-Location $Brain
  try { uv run python -m jarvis_brain @cmdArgs; return $LASTEXITCODE }
  finally { Pop-Location }
}

if ($Mode -eq "configure") { exit (Brain @("configure")) }

if ($Mode -eq "chat") {
  Brain @("check") | Out-Null
  if ($LASTEXITCODE -ne 0) { if ((Brain @("configure")) -ne 0) { exit 1 } }
  exit (Brain @("chat"))
}

# --- ensure the brain is configured & ready --------------------------------
Brain @("check") | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Setting up the local LLM..." -ForegroundColor Cyan
  if ((Brain @("configure")) -ne 0) { Write-Host "Setup did not finish." -ForegroundColor Red; exit 1 }
}

# --- backtalk config -------------------------------------------------------
if (-not (Test-Path $Backtalk)) {
  Write-Host "vendor\backtalk is missing. Run the Phase 0 import first." -ForegroundColor Red
  exit 1
}
$btJson = Join-Path $Backtalk "backtalk.json"
if (-not (Test-Path $btJson)) {
  $name = "Aria"
  $jj = Join-Path $Root "config\jarvis.json"
  if (Test-Path $jj) { try { $name = (Get-Content $jj -Raw | ConvertFrom-Json).name } catch {} }
  @{
    brain      = "local"
    agent_dir  = $Root
    name       = $name
    ptt_key    = "home"
    voice      = "bm_lewis"
    stt_model  = "small.en"
    signals_dir = $Backtalk
  } | ConvertTo-Json | Set-Content $btJson -Encoding utf8
  Write-Host "wrote vendor\backtalk\backtalk.json (brain=local, agent_dir=$Root)" -ForegroundColor DarkGray
}

# --- launch --------------------------------------------------------------
Write-Host "Starting the voice line (Ctrl-C to hang up)..." -ForegroundColor Cyan
Push-Location $Backtalk
try { uv run python -m backtalk.main }
finally { Pop-Location }
