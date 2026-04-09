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
from training_controller import train_single_expert

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def run_device_agent(
    worker_id: str,
    *,
    status_path: Path | str = DEFAULT_STATUS_PATH,
    claim_timeout_seconds: float = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    print_queue_status: bool = False,
) -> Optional[dict[str, Any]]:
    resolved_status_path = Path(status_path)
    claimed = claim_next_expert(
        worker_id,
        status_path=resolved_status_path,
        claim_timeout_seconds=claim_timeout_seconds,
    )
    if claimed is None:
        logger.info("No expert available for worker_id=%s", worker_id)
        if print_queue_status:
            print_status(resolved_status_path)
        return None

    expert_id = int(claimed["expert_id"])
    field_name = str(claimed["field_name"])
    logger.info(
        "Claimed expert_id=%s field_name=%s for worker_id=%s",
        expert_id,
        field_name,
        worker_id,
    )

    try:
        result = train_single_expert(expert_id, field_name)
        result_status = str(getattr(result, "status", STATUS_COMPLETED) or STATUS_COMPLETED).upper()
        final_status = STATUS_FAILED if result_status == STATUS_FAILED else STATUS_COMPLETED
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
        if print_queue_status:
            print_status(resolved_status_path)
        return summary
    except Exception as exc:
        release_expert(
            expert_id,
            status_path=resolved_status_path,
            worker_id=worker_id,
            status=STATUS_FAILED,
            error=f"{type(exc).__name__}: {exc}",
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
    parser.add_argument("--print-queue-status", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = run_device_agent(
        args.worker_id,
        status_path=Path(args.status_path),
        claim_timeout_seconds=args.claim_timeout_seconds,
        print_queue_status=args.print_queue_status,
    )
    if result is not None:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
