"""Run real CVE severity training in Colab via GRPO or Agent Lightning fallback."""

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.training.agent_lightning_bridge import (
    AL_AVAILABLE,
    CVESeverityAgent,
    CVETrainingTask,
    YBGDatasetProvider,
    build_ybg_trainer,
)


def _normalize_vllm_host(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        raise RuntimeError("A non-empty vLLM host is required")
    if not normalized.startswith(("http://", "https://")):
        normalized = f"http://{normalized}"
    return normalized


def _probe_vllm_models(base_url: str, *, timeout_seconds: float = 15.0) -> list[str]:
    normalized_base_url = _normalize_vllm_host(base_url)
    request = urllib.request.Request(
        f"{normalized_base_url}/v1/models",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Unable to reach the vLLM host at {normalized_base_url}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected vLLM model payload type: {type(payload).__name__}")
    data = payload.get("data", [])
    if not isinstance(data, list):
        raise RuntimeError("Unexpected vLLM /v1/models payload: missing data list")
    model_ids = [str(item.get("id") or "").strip() for item in data if isinstance(item, dict)]
    return [model_id for model_id in model_ids if model_id]


def _completion_to_text(completion: Any) -> str:
    if isinstance(completion, str):
        return completion
    if isinstance(completion, dict):
        if "content" in completion:
            return _completion_to_text(completion["content"])
        message = completion.get("message")
        if message is not None:
            return _completion_to_text(message)
    if isinstance(completion, list):
        return "\n".join(_completion_to_text(item) for item in completion)
    return str(completion)


def _build_vllm_predictor(base_url: str, model_name: str, *, timeout_seconds: float = 60.0):
    normalized_base_url = _normalize_vllm_host(base_url)

    def _predict(prompt: str, task: CVETrainingTask) -> str:
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 16,
        }
        request = urllib.request.Request(
            f"{normalized_base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"vLLM completion request failed for {task.cve_id}: {exc}"
            ) from exc
        choices = body.get("choices", []) if isinstance(body, dict) else []
        if not choices:
            raise RuntimeError(f"vLLM completion response had no choices for {task.cve_id}")
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        return str(message.get("content") or "").strip()

    return _predict


def _require_grpo_dependencies():
    try:
        from datasets import Dataset
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from trl import GRPOConfig, GRPOTrainer
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "GRPO training requires `trl`, `transformers`, and `datasets` in the Colab environment."
        ) from exc
    return Dataset, AutoModelForCausalLM, AutoTokenizer, GRPOConfig, GRPOTrainer


def _build_grpo_config(GRPOConfig, args: argparse.Namespace):
    config_kwargs = {
        "output_dir": str(args.output_dir),
        "learning_rate": float(args.learning_rate),
        "max_steps": int(args.max_steps),
        "per_device_train_batch_size": int(args.per_device_train_batch_size),
        "gradient_accumulation_steps": int(args.gradient_accumulation_steps),
        "logging_steps": 1,
        "save_steps": max(int(args.max_steps), 1),
        "num_generations": int(args.num_generations),
        "max_prompt_length": int(args.max_prompt_length),
        "max_completion_length": int(args.max_completion_length),
    }
    if args.vllm_host:
        config_kwargs["use_vllm"] = True
    try:
        return GRPOConfig(**config_kwargs)
    except TypeError as exc:
        if "use_vllm" not in config_kwargs:
            raise RuntimeError(f"Unable to construct GRPOConfig: {exc}") from exc
        config_kwargs.pop("use_vllm")
        try:
            return GRPOConfig(**config_kwargs)
        except TypeError as inner_exc:
            raise RuntimeError(f"Unable to construct GRPOConfig: {inner_exc}") from inner_exc


def _run_grpo(args: argparse.Namespace, tasks: list[CVETrainingTask]) -> dict[str, Any]:
    Dataset, AutoModelForCausalLM, AutoTokenizer, GRPOConfig, GRPOTrainer = _require_grpo_dependencies()
    if not args.model_name:
        raise RuntimeError("A model name is required to run GRPO training")
    rows = [
        {
            "prompt": task.prompt,
            "task_id": task.task_id,
            "expected_severity": task.expected_severity,
        }
        for task in tasks
    ]
    dataset = Dataset.from_list(rows)
    task_lookup = {task.task_id: task for task in tasks}
    reward_agent = CVESeverityAgent()
    if args.vllm_host:
        os.environ["YBG_VLLM_HOST"] = _normalize_vllm_host(args.vllm_host)
        os.environ.setdefault("OPENAI_BASE_URL", f"{os.environ['YBG_VLLM_HOST']}/v1")

    def reward_fn(completions, task_id, expected_severity, **_: Any) -> list[float]:
        rewards: list[float] = []
        for completion, current_task_id, current_expected in zip(
            completions,
            task_id,
            expected_severity,
        ):
            task = task_lookup[str(current_task_id)]
            outcome = reward_agent.run(
                task,
                predicted_severity=_completion_to_text(completion) or str(current_expected),
            )
            rewards.append(float(outcome["reward"]))
        return rewards

    tokenizer = AutoTokenizer.from_pretrained(
        args.model_name,
        trust_remote_code=bool(args.trust_remote_code),
    )
    if tokenizer.pad_token is None and tokenizer.eos_token is not None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        trust_remote_code=bool(args.trust_remote_code),
    )
    grpo_config = _build_grpo_config(GRPOConfig, args)
    trainer_signature = inspect.signature(GRPOTrainer.__init__)
    trainer_kwargs: dict[str, Any] = {
        "model": model,
        "args": grpo_config,
        "train_dataset": dataset,
    }
    if "reward_funcs" in trainer_signature.parameters:
        trainer_kwargs["reward_funcs"] = [reward_fn]
    elif "reward_function" in trainer_signature.parameters:
        trainer_kwargs["reward_function"] = reward_fn
    else:  # pragma: no cover - depends on installed TRL version
        raise RuntimeError("Installed GRPOTrainer does not expose a reward function argument")
    if "processing_class" in trainer_signature.parameters:
        trainer_kwargs["processing_class"] = tokenizer
    elif "tokenizer" in trainer_signature.parameters:
        trainer_kwargs["tokenizer"] = tokenizer
    trainer = GRPOTrainer(**trainer_kwargs)
    train_method = getattr(trainer, "train", None)
    if not callable(train_method):  # pragma: no cover - depends on installed TRL version
        raise RuntimeError("GRPOTrainer does not expose a train() method")
    train_method()
    save_model = getattr(trainer, "save_model", None)
    if callable(save_model):
        save_model(str(args.output_dir))
    return {
        "backend": "grpo",
        "task_count": len(tasks),
        "output_dir": str(args.output_dir),
    }


def _run_agent_lightning_fallback(args: argparse.Namespace, provider: YBGDatasetProvider) -> dict[str, Any]:
    if not AL_AVAILABLE:
        raise RuntimeError("Agent Lightning fallback is unavailable because Agent Lightning is not installed")
    if not args.vllm_host:
        raise RuntimeError("Agent Lightning fallback requires a vLLM host for remote generation")
    if not args.model_name:
        raise RuntimeError("Agent Lightning fallback requires a resolved model name")
    predictor = _build_vllm_predictor(args.vllm_host, args.model_name)
    trainer = build_ybg_trainer(
        dataset_provider=provider,
        agent=CVESeverityAgent(predict_fn=predictor),
        trainer_kwargs={"dataset_limit": args.dataset_limit},
    )
    for method_name in ("fit", "train", "run"):
        method = getattr(trainer, method_name, None)
        if callable(method):
            method()
            return {
                "backend": "agent_lightning",
                "task_count": len(provider.load_tasks(limit=args.dataset_limit)),
                "model_name": args.model_name,
            }
    raise RuntimeError("Agent Lightning trainer does not expose fit(), train(), or run()")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run real CVE severity training in Colab with GRPO or Agent Lightning fallback.",
    )
    parser.add_argument(
        "--feature-store-root",
        default=os.environ.get("YBG_FEATURE_STORE_ROOT", "training/features_safetensors"),
        help="Path to the real safetensors feature store.",
    )
    parser.add_argument(
        "--raw-data-root",
        default=os.environ.get("YBG_RAW_DATA_ROOT", "data/raw"),
        help="Path to the real raw CVE sample directory.",
    )
    parser.add_argument(
        "--vllm-host",
        default=os.environ.get("YBG_VLLM_HOST", ""),
        help="Base URL for a reachable vLLM OpenAI-compatible endpoint.",
    )
    parser.add_argument(
        "--model-name",
        default=os.environ.get("YBG_VLLM_MODEL", ""),
        help="Model identifier exposed by vLLM or loadable in Colab.",
    )
    parser.add_argument(
        "--dataset-limit",
        type=int,
        default=int(os.environ.get("YBG_COLAB_DATASET_LIMIT", "256")),
        help="Maximum number of real CVE tasks to load. Use 0 for all available tasks.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.environ.get("YBG_COLAB_OUTPUT_DIR", "reports/phase6_colab")),
        help="Directory where training outputs should be written.",
    )
    parser.add_argument(
        "--trainer-backend",
        choices=("auto", "grpo", "agent_lightning"),
        default=os.environ.get("YBG_COLAB_TRAINER_BACKEND", "auto"),
        help="Preferred training backend.",
    )
    parser.add_argument("--max-steps", type=int, default=8, help="Maximum training steps to run.")
    parser.add_argument(
        "--per-device-train-batch-size",
        type=int,
        default=1,
        help="Per-device batch size for GRPO training.",
    )
    parser.add_argument(
        "--gradient-accumulation-steps",
        type=int,
        default=1,
        help="Gradient accumulation steps for GRPO training.",
    )
    parser.add_argument(
        "--num-generations",
        type=int,
        default=2,
        help="Number of generations per GRPO step.",
    )
    parser.add_argument(
        "--max-prompt-length",
        type=int,
        default=512,
        help="Maximum prompt length for GRPO training.",
    )
    parser.add_argument(
        "--max-completion-length",
        type=int,
        default=32,
        help="Maximum completion length for GRPO training.",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=1e-5,
        help="Learning rate for GRPO training.",
    )
    parser.add_argument(
        "--trust-remote-code",
        action="store_true",
        help="Allow transformers to trust remote model code when required.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load the real dataset and validate the vLLM endpoint without starting training.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    provider = YBGDatasetProvider(
        feature_store_root=args.feature_store_root,
        raw_data_root=args.raw_data_root,
    )
    dataset_limit = None if int(args.dataset_limit) <= 0 else int(args.dataset_limit)
    tasks = provider.load_tasks(limit=dataset_limit)
    if not tasks:
        raise RuntimeError(
            f"No real CVE tasks were found under {Path(args.feature_store_root).as_posix()} or {Path(args.raw_data_root).as_posix()}"
        )

    model_candidates: list[str] = []
    if args.vllm_host:
        model_candidates = _probe_vllm_models(args.vllm_host)
        if not args.model_name and model_candidates:
            args.model_name = model_candidates[0]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "ok",
                    "task_count": len(tasks),
                    "first_task_ids": [task.task_id for task in tasks[:5]],
                    "vllm_host": _normalize_vllm_host(args.vllm_host) if args.vllm_host else None,
                    "vllm_models": model_candidates,
                    "trainer_backend": args.trainer_backend,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    backend_errors: list[str] = []
    if args.trainer_backend in {"auto", "grpo"}:
        try:
            summary = _run_grpo(args, tasks)
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
        except RuntimeError as exc:
            backend_errors.append(f"grpo: {exc}")
            if args.trainer_backend == "grpo":
                raise

    if args.trainer_backend in {"auto", "agent_lightning"}:
        try:
            summary = _run_agent_lightning_fallback(args, provider)
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
        except RuntimeError as exc:
            backend_errors.append(f"agent_lightning: {exc}")
            raise RuntimeError("; ".join(backend_errors)) from exc

    raise RuntimeError("No training backend was selected")


if __name__ == "__main__":
    raise SystemExit(main())
