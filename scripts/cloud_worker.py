from __future__ import annotations

import argparse
import json
import logging
import time

from backend.ingestion.industrial_autograbber import IndustrialAutoGrabber
from backend.ingestion.parallel_autograbber import ParallelAutoGrabberConfig

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("ygb.cloud_worker")


class CloudGPUWorker:
    """Local or cloud worker entrypoint for real-data industrial ingestion cycles."""

    def __init__(self, config: ParallelAutoGrabberConfig | None = None) -> None:
        self.config = config or ParallelAutoGrabberConfig(sources=["nvd", "cisa", "osv", "github"])
        self.grabber = IndustrialAutoGrabber(self.config)

    def run_once(self) -> dict[str, object]:
        result = self.grabber.run_cycle()
        payload = dict(result.__dict__) if hasattr(result, "__dict__") else dict(result)
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
