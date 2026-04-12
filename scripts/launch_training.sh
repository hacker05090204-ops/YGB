#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 {leader|follower|agent} [args...]"
  echo "Defaults: PYTHON_BIN=python YGB_USE_MOE=true YGB_DDP_ADDR=127.0.0.1 YGB_DDP_PORT=29500"
  echo "Queue: YGB_EXPERT_STATUS_PATH defaults to experts_status.json"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

cd "$PROJECT_ROOT"

MODE="${1:-leader}"
if [[ $# -gt 0 ]]; then
  shift
fi

export YGB_USE_MOE=true
export YGB_DDP_PORT="${YGB_DDP_PORT:-29500}"
export YGB_DDP_ADDR="${YGB_DDP_ADDR:-127.0.0.1}"
export YGB_EXPERT_STATUS_PATH="${YGB_EXPERT_STATUS_PATH:-experts_status.json}"

case "$MODE" in
  leader)
    export YGB_DDP_ROLE=leader
    exec "${PYTHON_BIN}" run_leader_ddp.py "$@"
    ;;
  follower)
    export YGB_DDP_ROLE=follower
    exec "${PYTHON_BIN}" run_rtx3050_follower.py "$@"
    ;;
  agent)
    export YGB_DDP_ROLE=agent
    exec "${PYTHON_BIN}" scripts/device_agent.py "$@"
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
