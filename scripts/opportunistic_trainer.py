from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import signal
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from impl_v1.phase49.runtime.idle_detector import get_idle_info, is_power_connected
from scripts.device_manager import (
    AUTO_DEVICE,
    DEFAULT_MIXED_PRECISION,
    DeviceConfiguration,
    resolve_device_configuration,
)
from scripts.expert_task_queue import (
    DEFAULT_CLAIM_TIMEOUT_SECONDS,
    DEFAULT_STATUS_PATH,
    STATUS_COMPLETED,
    STATUS_FAILED,
    ExpertTaskQueue,
)

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None

logger = logging.getLogger(__name__)

DEFAULT_IDLE_SECONDS_THRESHOLD = 60.0
DEFAULT_CPU_PERCENT_THRESHOLD = 25.0
DEFAULT_POLL_INTERVAL_SECONDS = 30.0
DEFAULT_ERROR_BACKOFF_SECONDS = 5.0


@dataclass(frozen=True)
class IdleStatus:
    idle_seconds: int
    idle_method: str
    cpu_percent: Optional[float]
    power_connected: bool
    is_idle: bool
    reason: str
    checked_at_epoch: float
    idle_seconds_threshold: float
    cpu_percent_threshold: Optional[float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _configure_logging(*, verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
    )


def build_default_worker_id(prefix: str = "opportunistic") -> str:
    host = str(platform.node() or os.getenv("COMPUTERNAME") or "local").strip()
    return f"{prefix}-{host}-{os.getpid()}"


def train_single_expert(expert_id: int, field_name: str):
    from training_controller import train_single_expert as controller_train_single_expert

    return controller_train_single_expert(expert_id, field_name)


def _get_result_value(result: Any, key: str, default: Any = None) -> Any:
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:
        return None
    return numeric


def _normalize_training_status(result: Any) -> str:
    status_text = str(_get_result_value(result, "status", STATUS_COMPLETED) or STATUS_COMPLETED)
    return STATUS_FAILED if status_text.upper().strip() == STATUS_FAILED else STATUS_COMPLETED


def _build_result_error_text(result: Any, final_status: str) -> str:
    if final_status != STATUS_FAILED:
        return ""
    for key in ("error", "reason", "message"):
        value = str(_get_result_value(result, key, "") or "").strip()
        if value:
            return value
    return "training_result_failed"


class DeviceIdleDetector:
    """Cross-platform idle detector with optional CPU utilization sampling."""

    def __init__(
        self,
        *,
        idle_seconds_threshold: float = DEFAULT_IDLE_SECONDS_THRESHOLD,
        cpu_percent_threshold: Optional[float] = DEFAULT_CPU_PERCENT_THRESHOLD,
        require_power_connected: bool = False,
        sample_cpu_percent: bool = True,
    ) -> None:
        if float(idle_seconds_threshold) < 0.0:
            raise ValueError("idle_seconds_threshold must be >= 0")
        if cpu_percent_threshold is not None and float(cpu_percent_threshold) < 0.0:
            raise ValueError("cpu_percent_threshold must be >= 0 when provided")
        self.idle_seconds_threshold = float(idle_seconds_threshold)
        self.cpu_percent_threshold = (
            None
            if cpu_percent_threshold is None
            else float(cpu_percent_threshold)
        )
        self.require_power_connected = bool(require_power_connected)
        self.sample_cpu_percent = bool(sample_cpu_percent)
        self._missing_psutil_warning_emitted = False
        self._cpu_probe_warning_emitted = False

    def _read_cpu_percent(self) -> Optional[float]:
        if not self.sample_cpu_percent:
            return None
        if psutil is None:
            if (
                self.cpu_percent_threshold is not None
                and not self._missing_psutil_warning_emitted
            ):
                logger.warning(
                    "DeviceIdleDetector: psutil unavailable; CPU utilization threshold will be skipped"
                )
                self._missing_psutil_warning_emitted = True
            return None
        try:
            return float(psutil.cpu_percent(interval=0.0))
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            if not self._cpu_probe_warning_emitted:
                logger.warning(
                    "DeviceIdleDetector: failed to sample CPU utilization via psutil: %s",
                    exc,
                )
                self._cpu_probe_warning_emitted = True
            return None

    def get_status(self) -> IdleStatus:
        checked_at_epoch = time.time()
        idle_seconds, idle_method = get_idle_info()
        power_connected = is_power_connected()
        cpu_percent = self._read_cpu_percent()

        blocking_reasons: list[str] = []
        if float(idle_seconds) < self.idle_seconds_threshold:
            blocking_reasons.append(
                f"idle {idle_seconds}s < {self.idle_seconds_threshold:.0f}s threshold"
            )
        if self.require_power_connected and not power_connected:
            blocking_reasons.append("system is not on AC power")
        if (
            self.cpu_percent_threshold is not None
            and cpu_percent is not None
            and float(cpu_percent) > self.cpu_percent_threshold
        ):
            blocking_reasons.append(
                f"cpu {cpu_percent:.1f}% > {self.cpu_percent_threshold:.1f}% threshold"
            )

        is_idle_now = not blocking_reasons
        if is_idle_now:
            positive_reasons = [
                f"idle threshold met ({idle_seconds}s via {idle_method})"
            ]
            if self.require_power_connected:
                positive_reasons.append("AC power connected")
            if self.cpu_percent_threshold is not None:
                if cpu_percent is None:
                    positive_reasons.append(
                        "CPU utilization unavailable; proceeding with OS idle signal only"
                    )
                else:
                    positive_reasons.append(
                        f"cpu {cpu_percent:.1f}% <= {self.cpu_percent_threshold:.1f}%"
                    )
            reason = "; ".join(positive_reasons)
        else:
            reason = "; ".join(blocking_reasons)

        return IdleStatus(
            idle_seconds=int(idle_seconds),
            idle_method=str(idle_method),
            cpu_percent=cpu_percent,
            power_connected=bool(power_connected),
            is_idle=bool(is_idle_now),
            reason=reason,
            checked_at_epoch=checked_at_epoch,
            idle_seconds_threshold=self.idle_seconds_threshold,
            cpu_percent_threshold=self.cpu_percent_threshold,
        )

    def sample(self) -> IdleStatus:
        return self.get_status()

    def is_idle(self) -> bool:
        return self.get_status().is_idle


TrainExpertFn = Callable[[int, str], Any]


class OpportunisticTrainer:
    """Passive loop that opportunistically trains the next available expert when idle."""

    def __init__(
        self,
        worker_id: str,
        *,
        status_path: Path | str = DEFAULT_STATUS_PATH,
        claim_timeout_seconds: float = DEFAULT_CLAIM_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        error_backoff_seconds: float = DEFAULT_ERROR_BACKOFF_SECONDS,
        idle_detector: Optional[DeviceIdleDetector] = None,
        preferred_device: str | None = AUTO_DEVICE,
        mixed_precision: str | None = DEFAULT_MIXED_PRECISION,
        train_expert_fn: Optional[TrainExpertFn] = None,
        queue: Optional[ExpertTaskQueue] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        worker_text = str(worker_id or "").strip()
        if not worker_text:
            raise ValueError("worker_id is required")
        if float(claim_timeout_seconds) <= 0.0:
            raise ValueError("claim_timeout_seconds must be > 0")
        if float(poll_interval_seconds) < 0.0:
            raise ValueError("poll_interval_seconds must be >= 0")
        if float(error_backoff_seconds) < 0.0:
            raise ValueError("error_backoff_seconds must be >= 0")

        self.worker_id = worker_text
        self.status_path = Path(status_path).resolve()
        self.claim_timeout_seconds = float(claim_timeout_seconds)
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.error_backoff_seconds = float(error_backoff_seconds)
        self.idle_detector = idle_detector or DeviceIdleDetector()
        self.stop_event = stop_event or threading.Event()
        self.train_expert_fn = train_expert_fn or train_single_expert
        self.queue = queue or ExpertTaskQueue(
            self.status_path,
            claim_timeout_seconds=self.claim_timeout_seconds,
        )
        self.device_configuration = resolve_device_configuration(
            preferred_device,
            mixed_precision=mixed_precision,
            configure_runtime=True,
        )

        logger.info(
            "Initialized opportunistic trainer worker_id=%s device=%s mixed_precision=%s status_path=%s",
            self.worker_id,
            self.device_configuration.selected_device,
            self.device_configuration.mixed_precision,
            self.status_path,
        )
        if self.device_configuration.fallback_reason:
            logger.info(
                "Device selection fallback for worker_id=%s: %s",
                self.worker_id,
                self.device_configuration.fallback_reason,
            )

    def request_stop(self, reason: str = "requested") -> None:
        if not self.stop_event.is_set():
            logger.info(
                "Stop requested for opportunistic trainer worker_id=%s reason=%s",
                self.worker_id,
                reason,
            )
        self.stop_event.set()

    def should_stop(self) -> bool:
        return self.stop_event.is_set()

    def _release_failure(
        self,
        claimed: dict[str, Any],
        *,
        error_text: str,
    ) -> Optional[dict[str, Any]]:
        expert_id = int(claimed["expert_id"])
        try:
            return self.queue.release_expert(
                expert_id,
                worker_id=self.worker_id,
                status=STATUS_FAILED,
                error=error_text,
            )
        except Exception:
            logger.exception(
                "Failed to release expert_id=%s after opportunistic training error",
                expert_id,
            )
            return None

    def run_once(self) -> dict[str, Any]:
        idle_status = self.idle_detector.sample()
        idle_payload = idle_status.to_dict()
        base_result = {
            "worker_id": self.worker_id,
            "idle_status": idle_payload,
            "device_configuration": self.device_configuration.to_dict(),
        }

        if not idle_status.is_idle:
            logger.info(
                "Skipping opportunistic training for worker_id=%s: %s",
                self.worker_id,
                idle_status.reason,
            )
            return {
                **base_result,
                "action": "not_idle",
                "status": "SKIPPED",
                "reason": idle_status.reason,
            }

        claimed: Optional[dict[str, Any]] = None
        started_at = time.time()
        try:
            claimed = self.queue.claim_next_expert(
                self.worker_id,
                claim_timeout_seconds=self.claim_timeout_seconds,
            )
            if claimed is None:
                logger.info(
                    "No expert available for opportunistic worker_id=%s",
                    self.worker_id,
                )
                return {
                    **base_result,
                    "action": "queue_empty",
                    "status": "SKIPPED",
                    "reason": "queue_empty",
                }

            expert_id = int(claimed["expert_id"])
            field_name = str(claimed["field_name"])
            logger.info(
                "Opportunistic worker_id=%s claimed expert_id=%s field_name=%s",
                self.worker_id,
                expert_id,
                field_name,
            )

            training_result = self.train_expert_fn(expert_id, field_name)
            final_status = _normalize_training_status(training_result)
            checkpoint_path = str(_get_result_value(training_result, "checkpoint_path", "") or "")
            error_text = _build_result_error_text(training_result, final_status)
            queue_record = self.queue.release_expert(
                expert_id,
                worker_id=self.worker_id,
                status=final_status,
                val_f1=_coerce_float(_get_result_value(training_result, "val_f1")),
                val_precision=_coerce_float(_get_result_value(training_result, "val_precision")),
                val_recall=_coerce_float(_get_result_value(training_result, "val_recall")),
                checkpoint_path=checkpoint_path,
                error=error_text,
            )

            elapsed = time.time() - started_at
            if final_status == STATUS_FAILED:
                logger.error(
                    "Opportunistic training returned FAILED for expert_id=%s field_name=%s error=%s",
                    expert_id,
                    field_name,
                    error_text,
                )
            else:
                logger.info(
                    "Opportunistic training completed for expert_id=%s field_name=%s checkpoint=%s",
                    expert_id,
                    field_name,
                    checkpoint_path or "-",
                )

            return {
                **base_result,
                "action": "trained",
                "expert_id": expert_id,
                "field_name": field_name,
                "status": final_status,
                "duration_seconds": round(elapsed, 3),
                "val_f1": _coerce_float(_get_result_value(training_result, "val_f1")),
                "val_precision": _coerce_float(_get_result_value(training_result, "val_precision")),
                "val_recall": _coerce_float(_get_result_value(training_result, "val_recall")),
                "checkpoint_path": checkpoint_path,
                "error": error_text,
                "queue_record": queue_record,
            }
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            release_record = None
            if claimed is not None:
                release_record = self._release_failure(claimed, error_text=error_text)
            logger.exception(
                "Opportunistic trainer cycle failed for worker_id=%s",
                self.worker_id,
            )
            return {
                **base_result,
                "action": "error",
                "status": STATUS_FAILED,
                "expert_id": int(claimed["expert_id"]) if claimed is not None else None,
                "field_name": str(claimed["field_name"]) if claimed is not None else "",
                "error": error_text,
                "queue_record": release_record,
            }

    def run_forever(self, *, max_cycles: Optional[int] = None) -> dict[str, Any]:
        history: list[dict[str, Any]] = []
        cycles = 0
        stop_reason = "stop_requested"

        logger.info(
            "Starting opportunistic trainer loop worker_id=%s poll_interval=%.1fs",
            self.worker_id,
            self.poll_interval_seconds,
        )

        while not self.should_stop():
            if max_cycles is not None and cycles >= int(max_cycles):
                stop_reason = "max_cycles_reached"
                break

            cycle_result = self.run_once()
            history.append(cycle_result)
            cycles += 1

            action = str(cycle_result.get("action", "")).strip().lower()
            if self.should_stop():
                stop_reason = "stop_requested"
                break

            if action == "error":
                sleep_seconds = self.error_backoff_seconds
            elif action == "trained":
                sleep_seconds = 0.0
            else:
                sleep_seconds = self.poll_interval_seconds

            if sleep_seconds > 0.0 and self.stop_event.wait(sleep_seconds):
                stop_reason = "stop_requested"
                break
        else:
            stop_reason = "stop_requested"

        processed_experts = sum(1 for item in history if item.get("action") == "trained")
        logger.info(
            "Opportunistic trainer stopped worker_id=%s reason=%s cycles=%s processed=%s",
            self.worker_id,
            stop_reason,
            cycles,
            processed_experts,
        )
        return {
            "worker_id": self.worker_id,
            "stopped_reason": stop_reason,
            "cycles": cycles,
            "processed_experts": processed_experts,
            "results": history,
        }


def _install_signal_handlers(trainer: OpportunisticTrainer) -> None:
    def _handle_signal(signum, _frame) -> None:
        trainer.request_stop(reason=f"signal_{signum}")

    for signal_name in ("SIGINT", "SIGTERM"):
        signum = getattr(signal, signal_name, None)
        if signum is None:
            continue
        try:
            signal.signal(signum, _handle_signal)
        except (OSError, RuntimeError, ValueError):  # pragma: no cover - environment-specific
            logger.debug("Unable to install %s handler for opportunistic trainer", signal_name)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Passive opportunistic expert trainer.",
    )
    parser.add_argument(
        "--worker-id",
        default=build_default_worker_id(),
        help="Unique worker identifier used for queue claims.",
    )
    parser.add_argument(
        "--status-path",
        default=os.getenv("YGB_EXPERT_STATUS_PATH", str(DEFAULT_STATUS_PATH)),
        help="Path to experts status JSON.",
    )
    parser.add_argument(
        "--claim-timeout-seconds",
        type=float,
        default=DEFAULT_CLAIM_TIMEOUT_SECONDS,
        help="Claim expiry used while training a single expert.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="Delay between idle checks when no work is run.",
    )
    parser.add_argument(
        "--error-backoff-seconds",
        type=float,
        default=DEFAULT_ERROR_BACKOFF_SECONDS,
        help="Delay after queue or training errors before retrying.",
    )
    parser.add_argument(
        "--idle-seconds-threshold",
        type=float,
        default=DEFAULT_IDLE_SECONDS_THRESHOLD,
        help="Minimum OS idle time required before claiming work.",
    )
    parser.add_argument(
        "--cpu-percent-threshold",
        type=float,
        default=DEFAULT_CPU_PERCENT_THRESHOLD,
        help="Optional CPU usage threshold used when psutil is available.",
    )
    parser.add_argument(
        "--require-power-connected",
        action="store_true",
        help="Require AC power before claiming work.",
    )
    parser.add_argument(
        "--device",
        default=AUTO_DEVICE,
        help="Preferred device for runtime environment configuration.",
    )
    parser.add_argument(
        "--mixed-precision",
        default=DEFAULT_MIXED_PRECISION,
        help="Preferred mixed precision policy.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one idle check + one optional training cycle, then exit.",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        help="Optional maximum number of loop iterations before exit.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _configure_logging(verbose=bool(args.verbose))

    idle_detector = DeviceIdleDetector(
        idle_seconds_threshold=args.idle_seconds_threshold,
        cpu_percent_threshold=args.cpu_percent_threshold,
        require_power_connected=bool(args.require_power_connected),
    )
    trainer = OpportunisticTrainer(
        args.worker_id,
        status_path=args.status_path,
        claim_timeout_seconds=args.claim_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        error_backoff_seconds=args.error_backoff_seconds,
        idle_detector=idle_detector,
        preferred_device=args.device,
        mixed_precision=args.mixed_precision,
    )
    _install_signal_handlers(trainer)

    if args.once:
        result = trainer.run_once()
    else:
        result = trainer.run_forever(max_cycles=args.max_cycles)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
