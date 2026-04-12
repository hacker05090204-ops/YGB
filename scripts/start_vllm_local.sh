#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"
MODEL="${YBG_VLLM_MODEL:-${1:-Qwen/Qwen2.5-1.5B-Instruct}}"
PORT="${YBG_VLLM_PORT:-${2:-8000}}"
BIND_HOST="${YBG_VLLM_BIND_HOST:-0.0.0.0}"
TENSOR_PARALLEL_SIZE="${YBG_VLLM_TENSOR_PARALLEL_SIZE:-1}"

echo "[YBG] Starting local vLLM server"
echo "[YBG] Model: ${MODEL}"
echo "[YBG] Bind host: ${BIND_HOST}"
echo "[YBG] Port: ${PORT}"
echo "[YBG] Tensor parallel size: ${TENSOR_PARALLEL_SIZE}"

if ! "${PYTHON_BIN}" -c "import vllm" >/dev/null 2>&1; then
  echo "[YBG] vLLM is not installed in this environment. Install it before running this script." >&2
  exit 1
fi

echo "[YBG] ngrok guidance:"
echo "[YBG]   ngrok http ${PORT}"
echo "[YBG]   export YBG_VLLM_HOST=https://<your-ngrok-subdomain>.ngrok-free.app"
echo "[YBG]   python scripts/run_ybg_training_colab.py --vllm-host \"${YBG_VLLM_HOST:-https://<your-ngrok-subdomain>.ngrok-free.app}\""

exec "${PYTHON_BIN}" -m vllm.entrypoints.openai.api_server \
  --host "${BIND_HOST}" \
  --port "${PORT}" \
  --model "${MODEL}" \
  --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}"
