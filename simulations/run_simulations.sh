#!/usr/bin/env bash
# Operational runner only. Does not modify application source.
set -u
cd "$(dirname "$0")/.."
ROOT="$(pwd)/simulations"
PY="$(pwd)/.venv/bin/python"
LOG="$ROOT/runner.log"
export PYTHONUNBUFFERED=1
# Groq published llama3-8b-8192 rates, USD per 1M tokens.
export COST_PER_MILLION_PROMPT_TOKENS=0.05
export COST_PER_MILLION_COMPLETION_TOKENS=0.08

{
  echo "MODULE_CHECK $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "$PY" -m research-scout </dev/null >"$ROOT/module-check-research-scout.txt" 2>&1
  echo "module_exit=$?"
} >>"$LOG"

run_one() {
  local slug="$1"
  local scorer="$2"
  local profile="$3"
  local base="$ROOT/$slug"
  mkdir -p "$base"
  export DATA_DIR="$base/data"
  export RESULTS_DIR="$base/results"
  export LOGS_DIR="$base/logs"
  export METRICS_DIR="$base/metrics"
  export SCORER="$scorer"
  echo "START slug=$slug scorer=$scorer $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG"
  set +e
  "$PY" -m research_scout <"$profile" >"$base/console.txt" 2>&1
  local code=$?
  set -e
  echo "END slug=$slug exit=$code $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG"
  return "$code"
}

set -e
run_one "llama-01-cs-swe-web-infra" "llama" "$ROOT/profiles/01-cs-swe-web-infra.txt"
run_one "jev-01-cs-swe-web-infra" "jev" "$ROOT/profiles/01-cs-swe-web-infra.txt"
run_one "llama-02-ai-engineer" "llama" "$ROOT/profiles/02-ai-engineer.txt"
run_one "jev-02-ai-engineer" "jev" "$ROOT/profiles/02-ai-engineer.txt"
run_one "llama-03-data-engineer" "llama" "$ROOT/profiles/03-data-engineer.txt"
run_one "jev-03-data-engineer" "jev" "$ROOT/profiles/03-data-engineer.txt"
echo "ALL_DONE $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG"
