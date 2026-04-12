# Colab DDP Quickstart

This guide is limited to the Phase 14 DDP + Colab coordination flow already present in this repository.

- It does **not** unlock or bypass the permanent authority lock.
- It assumes the leader is the **only** process that claims experts in `experts_status.json`.
- It requires real data and the existing training scripts in this repository.

## 1. Leader host preparation

1. Start the OpenAI-compatible vLLM endpoint on the leader host:

   ```bash
   bash scripts/start_vllm_local.sh
   ```

2. Publish the vLLM HTTP endpoint with ngrok so Colab can reach it:

   ```bash
   ngrok http 8000
   export YBG_VLLM_HOST="https://<your-ngrok-subdomain>.ngrok-free.app"
   export YGB_VLLM_HOST="${YBG_VLLM_HOST}"
   ```

   The repository scripts read `YBG_VLLM_HOST`. If your surrounding shell or notebook setup uses the `YGB_VLLM_HOST` name, export both variables to the same ngrok URL so the runtime configuration stays explicit.

3. Choose the DDP address and port that the follower can actually reach. Do **not** use a placeholder in production.

   ```bash
   export YGB_DDP_ADDR="<leader-reachable-ip-or-hostname>"
   export YGB_DDP_PORT="29500"
   export YGB_EXPERT_STATUS_PATH="experts_status.json"
   ```

4. Start the leader so it claims the next expert before training begins:

   ```bash
   bash scripts/launch_training.sh leader
   ```

## 2. Colab runtime preparation

1. Clone or mount the same repository state in Colab.
2. Ensure the follower can read the same expert queue file the leader wrote. If the queue file is not on shared storage, sync the current `experts_status.json` into the Colab runtime before starting the follower.
3. Export the same DDP target values inside Colab:

   ```bash
   export YGB_DDP_ADDR="<leader-reachable-ip-or-hostname>"
   export YGB_DDP_PORT="29500"
   export YGB_EXPERT_STATUS_PATH="/content/YGB-main/experts_status.json"
   export YBG_VLLM_HOST="https://<your-ngrok-subdomain>.ngrok-free.app"
    export YGB_VLLM_HOST="${YBG_VLLM_HOST}"
   ```

## 3. Required vLLM connectivity test before training

Run the Colab training entrypoint in dry-run mode first. This validates that the runtime can load real tasks and that the ngrok-backed vLLM endpoint responds before any training starts.

```bash
python scripts/run_ybg_training_colab.py \
  --dry-run \
  --vllm-host "${YBG_VLLM_HOST}" \
  --model-name "${YBG_VLLM_MODEL:-Qwen/Qwen2.5-1.5B-Instruct}"
```

Expected dry-run behavior:

- prints a JSON payload
- includes `"status": "ok"`
- reports a real `task_count`
- shows the resolved vLLM model list when the endpoint is reachable

If the dry-run fails, stop there and fix connectivity before starting training.

## 4. Start the follower from Colab

After the dry-run succeeds and the leader has already claimed an expert, start the follower:

```bash
python run_rtx3050_follower.py
```

Follower behavior in this repository:

- reads `YGB_DDP_ADDR` and `YGB_DDP_PORT`
- logs the real leader target it will connect to
- resolves the already-claimed expert from `experts_status.json`
- does **not** claim a new expert itself

If there are multiple active claims in the queue, set `YGB_EXPERT_ID` explicitly to the already-claimed expert that should be followed.

## 5. Optional launcher usage

The shell launcher can be used for the supported modes:

```bash
bash scripts/launch_training.sh leader
bash scripts/launch_training.sh follower
bash scripts/launch_training.sh agent
```

The launcher preserves the current values of `YGB_DDP_ADDR`, `YGB_DDP_PORT`, and `YGB_EXPERT_STATUS_PATH`.
