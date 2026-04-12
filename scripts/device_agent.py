from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.expert_task_queue import (
    DEFAULT_CLAIM_TIMEOUT_SECONDS,
    DEFAULT_STATUS_PATH,
    STATUS_COMPLETED,
    STATUS_FAILED,
    claim_next_expert,
    print_status,
    release_expert,
)

logger = logging.getLogger(__name__)


def _configure_logging(*, verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
    )


def _resolve_status_path(status_path: Path | str) -> Path:
    return Path(status_path).resolve()


def train_single_expert(expert_id: int, field_name: str):
    from training_controller import train_single_expert as controller_train_single_expert

    return controller_train_single_expert(expert_id, field_name)


def run_device_agent(
    worker_id: str,
    *,
    status_path: Path | str = DEFAULT_STATUS_PATH,
    claim_timeout_seconds: float = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    print_queue_status: bool = False,
    max_experts: Optional[int] = None,
) -> dict[str, Any]:
    resolved_status_path = _resolve_status_path(status_path)
    train_single_expert_fn = train_single_expert
    max_experts_value = None if max_experts is None else int(max_experts)
    if max_experts_value is not None and max_experts_value < 0:
        raise ValueError("max_experts must be >= 0")

    summaries: list[dict[str, Any]] = []
    stop_reason = "queue_empty"

    logger.info(
        "Starting device agent for worker_id=%s status_path=%s",
        worker_id,
        resolved_status_path,
    )

    while max_experts_value is None or len(summaries) < max_experts_value:
        claimed = claim_next_expert(
            worker_id,
            status_path=resolved_status_path,
            claim_timeout_seconds=claim_timeout_seconds,
        )
        if claimed is None:
            logger.info("No expert available for worker_id=%s", worker_id)
            break

        expert_id = int(claimed["expert_id"])
        field_name = str(claimed["field_name"])
        logger.info(
            "Claimed expert_id=%s field_name=%s for worker_id=%s",
            expert_id,
            field_name,
            worker_id,
        )

        try:
            result = train_single_expert_fn(expert_id, field_name)
            result_status = str(
                getattr(result, "status", STATUS_COMPLETED) or STATUS_COMPLETED
            ).upper()
            final_status = (
                STATUS_FAILED if result_status == STATUS_FAILED else STATUS_COMPLETED
            )
            queue_record = release_expert(
                expert_id,
                status_path=resolved_status_path,
                worker_id=worker_id,
                status=final_status,
                val_f1=getattr(result, "val_f1", None),
                val_precision=getattr(result, "val_precision", None),
                val_recall=getattr(result, "val_recall", None),
                checkpoint_path=str(getattr(result, "checkpoint_path", "") or ""),
                error="" if final_status != STATUS_FAILED else "training_failed",
            )
            summary = {
                "worker_id": worker_id,
                "expert_id": expert_id,
                "field_name": field_name,
                "status": final_status,
                "val_f1": float(getattr(result, "val_f1", 0.0) or 0.0),
                "val_precision": float(getattr(result, "val_precision", 0.0) or 0.0),
                "val_recall": float(getattr(result, "val_recall", 0.0) or 0.0),
                "checkpoint_path": str(getattr(result, "checkpoint_path", "") or ""),
                "queue_record": queue_record,
            }
            summaries.append(summary)
            logger.info(
                "Released expert_id=%s field_name=%s with status=%s val_f1=%.4f",
                expert_id,
                field_name,
                final_status,
                summary["val_f1"],
            )
        except Exception as exc:
            try:
                release_expert(
                    expert_id,
                    status_path=resolved_status_path,
                    worker_id=worker_id,
                    status=STATUS_FAILED,
                    error=f"{type(exc).__name__}: {exc}",
                )
            except Exception:
                logger.exception(
                    "Device agent failed to release expert_id=%s after training error",
                    expert_id,
                )
            logger.exception(
                "Device agent failed for worker_id=%s expert_id=%s field_name=%s",
                worker_id,
                expert_id,
                field_name,
            )
            if print_queue_status:
                print_status(resolved_status_path)
            raise

    if max_experts_value is not None and len(summaries) >= max_experts_value:
        stop_reason = "max_experts_reached"

    if print_queue_status:
        print_status(resolved_status_path)

    logger.info(
        "Device agent stopped for worker_id=%s reason=%s processed=%s",
        worker_id,
        stop_reason,
        len(summaries),
    )
    return {
        "worker_id": worker_id,
        "processed_experts": len(summaries),
        "max_experts": max_experts_value,
        "stopped_reason": stop_reason,
        "results": summaries,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Claim an expert and train it")
    parser.add_argument("--worker-id", required=True)
    parser.add_argument(
        "--status-path",
        default=os.getenv("YGB_EXPERT_STATUS_PATH", str(DEFAULT_STATUS_PATH)),
    )
    parser.add_argument(
        "--claim-timeout-seconds",
        type=float,
        default=DEFAULT_CLAIM_TIMEOUT_SECONDS,
    )
    parser.add_argument("--max-experts", type=int)
    parser.add_argument("--print-queue-status", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _configure_logging(verbose=bool(args.verbose))
    result = run_device_agent(
        args.worker_id,
        status_path=args.status_path,
        claim_timeout_seconds=args.claim_timeout_seconds,
        print_queue_status=args.print_queue_status,
        max_experts=args.max_experts,
    )
    if result is not None:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
