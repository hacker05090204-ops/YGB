from __future__ import annotations

import argparse
import json
import logging
import time

from backend.ingestion.industrial_autograbber import IndustrialAutoGrabber
from backend.ingestion.parallel_autograbber import ParallelAutoGrabberConfig
from scripts.device_manager import get_config
from scripts.expert_task_queue import ExpertTaskQueue, STATUS_COMPLETED, STATUS_FAILED
from training_controller import train_single_expert

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("ygb.cloud_worker")


class CloudGPUWorker:
    """Local or cloud worker entrypoint for real-data expert training and ingestion cycles."""

    def __init__(self, config: ParallelAutoGrabberConfig | None = None) -> None:
        self.config = config or ParallelAutoGrabberConfig(sources=["nvd", "cisa", "osv", "github"])
        self.grabber = IndustrialAutoGrabber(self.config)
        self.device_config = get_config()
        self.queue = ExpertTaskQueue()
        self.worker_id = f"cloud-{self.device_config.device}-{self.device_config.device_name}"

    def _train_next_expert(self) -> dict[str, object] | None:
        claimed = self.queue.claim_next_expert(worker_id=self.worker_id)
        if claimed is None:
            logger.info("cloud_worker_no_expert_available worker_id=%s", self.worker_id)
            return None
        expert_id = int(claimed["expert_id"])
        field_name = str(claimed["field_name"])
        logger.info(
            "cloud_worker_claimed expert_id=%s field_name=%s device=%s batch_size=%s amp=%s",
            expert_id,
            field_name,
            self.device_config.device,
            self.device_config.batch_size,
            self.device_config.use_amp,
        )
        try:
            result = train_single_expert(expert_id, field_name)
            released = self.queue.release_expert(
                expert_id,
                worker_id=self.worker_id,
                status=STATUS_COMPLETED,
                val_f1=float(result.val_f1),
                val_precision=float(result.val_precision),
                val_recall=float(result.val_recall),
                checkpoint_path=str(result.checkpoint_path),
            )
            payload = {
                "expert_id": expert_id,
                "field_name": field_name,
                "status": STATUS_COMPLETED,
                "val_f1": float(result.val_f1),
                "val_precision": float(result.val_precision),
                "val_recall": float(result.val_recall),
                "checkpoint_path": str(result.checkpoint_path),
                "queue_record": released,
            }
            logger.info("cloud_worker_training_complete=%s", json.dumps(payload, default=str))
            return payload
        except Exception as exc:
            released = self.queue.release_expert(
                expert_id,
                worker_id=self.worker_id,
                status=STATUS_FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )
            logger.exception(
                "cloud_worker_training_failed expert_id=%s field_name=%s reason=%s",
                expert_id,
                field_name,
                exc,
            )
            return {
                "expert_id": expert_id,
                "field_name": field_name,
                "status": STATUS_FAILED,
                "error": f"{type(exc).__name__}: {exc}",
                "queue_record": released,
            }

    def run_once(self) -> dict[str, object]:
        training_payload = self._train_next_expert()
        ingestion_result = self.grabber.run_cycle()
        ingestion_payload = (
            dict(ingestion_result.__dict__)
            if hasattr(ingestion_result, "__dict__")
            else dict(ingestion_result)
        )
        payload = {
            "worker_id": self.worker_id,
            "device": self.device_config.to_dict(),
            "training": training_payload,
            "ingestion": ingestion_payload,
        }
        logger.info("cloud_worker_cycle=%s", json.dumps(payload, default=str))
        return payload

    def run_forever(self, *, sleep_seconds: float | None = None) -> None:
        interval = float(sleep_seconds if sleep_seconds is not None else self.config.cycle_interval_seconds)
        while True:
            self.run_once()
            time.sleep(max(interval, 1.0))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run industrial ingestion worker cycles.")
    parser.add_argument("--loop", action="store_true", help="Run continuously instead of a single cycle")
    parser.add_argument("--sleep-seconds", type=float, default=None, help="Override sleep interval between cycles")
    args = parser.parse_args()

    worker = CloudGPUWorker()
    if args.loop:
        worker.run_forever(sleep_seconds=args.sleep_seconds)
        return
    worker.run_once()


if __name__ == "__main__":
    main()
