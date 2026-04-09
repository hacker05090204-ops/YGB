"""Startup wiring for the fully automatic ingestion-to-training pipeline."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass

from backend.ingestion.autograbber import (
    AutoGrabber,
    AutoGrabberConfig,
    initialize_autograbber,
)
from backend.api.system_status import seed_system_status_cache
from backend.training.auto_train_controller import (
    AutoTrainController,
    get_auto_train_controller,
)

logger = logging.getLogger(__name__)

AUTOGRAB_INTERVAL_ENV_VARS = (
    "YGB_AUTOGRABBER_GRAB_INTERVAL_SECONDS",
    "YGB_AUTOGRABBER_CYCLE_INTERVAL_SECONDS",
)

FULLY_AUTOMATIC_PIPELINE_PATH = (
    "AutoGrabber public-source ingestion -> normalization/quality gate -> "
    "feature shard persistence -> bridge publication -> "
    "AutoTrainController scheduled training"
)


@dataclass(frozen=True)
class PipelineBootstrapResult:
    autograbber: AutoGrabber
    auto_train_controller: AutoTrainController
    autograbber_config: AutoGrabberConfig
    autograbber_started: bool
    auto_train_started: bool


_bootstrap_lock = threading.Lock()


def _refresh_sync_index_background() -> None:
    try:
        from backend.sync.sync_engine import get_local_sync_index

        get_local_sync_index().refresh()
        logger.info("[BOOT] Local sync index refreshed")
    except Exception as exc:
        logger.warning("[BOOT] Local sync index refresh failed: %s", exc)


def _resolve_positive_int_env(var_names: tuple[str, ...], default: int) -> int:
    for var_name in var_names:
        raw_value = os.environ.get(var_name, "").strip()
        if not raw_value:
            continue
        try:
            parsed_value = int(raw_value)
        except ValueError as exc:
            raise ValueError(
                f"{var_name} must be an integer greater than zero; received {raw_value!r}"
            ) from exc
        if parsed_value <= 0:
            raise ValueError(
                f"{var_name} must be greater than zero; received {parsed_value}"
            )
        logger.info(
            "[BOOT] AutoGrabber interval override detected %s=%d",
            var_name,
            parsed_value,
        )
        return parsed_value
    return default


def _resolve_autograbber_config() -> AutoGrabberConfig:
    base_config = AutoGrabberConfig()
    interval_seconds = _resolve_positive_int_env(
        AUTOGRAB_INTERVAL_ENV_VARS,
        base_config.cycle_interval_seconds,
    )
    return AutoGrabberConfig(
        sources=list(base_config.sources),
        cycle_interval_seconds=interval_seconds,
        quality_threshold=base_config.quality_threshold,
        max_per_cycle=base_config.max_per_cycle,
        dedup_enabled=base_config.dedup_enabled,
    )


def _controller_running(controller: AutoTrainController) -> bool:
    status_method = getattr(controller, "is_scheduled_running", None)
    if callable(status_method):
        return bool(status_method())
    return False


def _controller_interval_seconds(controller: AutoTrainController) -> float | None:
    config = getattr(controller, "config", None)
    interval_seconds = getattr(config, "check_interval_seconds", None)
    if interval_seconds is None:
        return None
    try:
        return float(interval_seconds)
    except (TypeError, ValueError):
        return None


def initialize_workflow_orchestrator(*, autograbber, auto_train_controller):
    from backend.tasks.industrial_agent import initialize_workflow_orchestrator as _init

    return _init(
        autograbber=autograbber,
        auto_train_controller=auto_train_controller,
    )


def bootstrap_pipeline() -> PipelineBootstrapResult:
    """Initialize and start the automatic ingestion-to-training pipeline."""
    with _bootstrap_lock:
        autograbber = None
        controller = None
        controller_started_now = False

        try:
            autograbber_config = _resolve_autograbber_config()
            autograbber = initialize_autograbber(autograbber_config)
            autograbber.start_scheduled()

            controller = get_auto_train_controller()
            controller_started_now = bool(controller.start())
            controller_running = controller_started_now or _controller_running(controller)

            logger.info(
                "[BOOT] Fully automatic pipeline path enabled: %s",
                FULLY_AUTOMATIC_PIPELINE_PATH,
            )
            logger.info(
                "[BOOT] AutoGrabber scheduler started sources=%s interval_seconds=%d "
                "max_per_cycle=%d quality_threshold=%.3f dedup_enabled=%s",
                ",".join(autograbber_config.sources),
                autograbber_config.cycle_interval_seconds,
                autograbber_config.max_per_cycle,
                autograbber_config.quality_threshold,
                autograbber_config.dedup_enabled,
            )

            controller_interval = _controller_interval_seconds(controller)
            if controller_interval is None:
                logger.info(
                    "[BOOT] AutoTrainController scheduler running=%s started_now=%s",
                    controller_running,
                    controller_started_now,
                )
            else:
                logger.info(
                    "[BOOT] AutoTrainController scheduler running=%s started_now=%s "
                    "interval_seconds=%.3f",
                    controller_running,
                    controller_started_now,
                    controller_interval,
                )
            workflow_orchestrator = initialize_workflow_orchestrator(
                autograbber=autograbber,
                auto_train_controller=controller,
            )
            logger.info(
                "[BOOT] Autonomous workflow orchestrator initialized history_size=%s",
                workflow_orchestrator.get_status().get("history_size", 0),
            )
            seed_started = seed_system_status_cache()
            logger.info(
                "[BOOT] System status cache seed started=%s",
                seed_started,
            )
            threading.Thread(
                target=_refresh_sync_index_background,
                name="ygb-sync-index-refresh",
                daemon=True,
            ).start()
            logger.info("[BOOT] Local sync index refresh scheduled")

            return PipelineBootstrapResult(
                autograbber=autograbber,
                auto_train_controller=controller,
                autograbber_config=autograbber_config,
                autograbber_started=True,
                auto_train_started=controller_running,
            )
        except Exception as exc:
            if controller is not None and controller_started_now:
                try:
                    controller.stop(timeout=1.0)
                except Exception as stop_exc:
                    logger.exception(
                        "[BOOT] Failed to stop AutoTrainController after bootstrap error: %s",
                        stop_exc,
                    )
            if autograbber is not None:
                try:
                    autograbber.stop()
                except Exception as stop_exc:
                    logger.exception(
                        "[BOOT] Failed to stop AutoGrabber after bootstrap error: %s",
                        stop_exc,
                    )
            logger.exception("[BOOT] Fully automatic pipeline bootstrap failed: %s", exc)
            raise
