from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional


def get_runtime_status_payload(
    *,
    project_root: Path,
    g38_available: bool,
    get_auto_trainer: Callable[[], Any],
    repair_runtime_artifacts_if_needed: Callable[..., dict],
    read_validated_telemetry: Callable[
        [Path], tuple[Optional[Dict[str, Any]], Optional[str]]
    ],
    get_runtime_status_cached: Callable[[], Optional[Dict[str, Any]]],
    store_runtime_status_cached: Callable[[Dict[str, Any]], Dict[str, Any]],
    logger,
) -> Dict[str, Any]:
    cached_payload = get_runtime_status_cached()
    if cached_payload is not None:
        return cached_payload

    telemetry_path = project_root / "reports" / "training_telemetry.json"
    live_status = None
    training_active = False

    if g38_available:
        try:
            trainer = get_auto_trainer()
            live_status = trainer.get_status()
            training_active = bool(live_status.get("is_training", False))
        except Exception:
            logger.exception("runtime_status live trainer probe failed")
            live_status = None

    repair_status = {"repaired": False, "issues": []}
    try:
        repair_status = repair_runtime_artifacts_if_needed(
            training_active=training_active
        )
    except Exception:
        logger.exception("runtime_status auto-repair failed")
        repair_status = {"repaired": False, "issues": ["auto_repair_failed"]}

    if not telemetry_path.exists():
        if live_status is not None:
            try:
                import time as _time
                import subprocess as _sp

                trainer = get_auto_trainer()
                status = live_status
                is_training = bool(status.get("is_training", False))
                epoch = status.get("epoch", 0)
                total_epochs = status.get("total_epochs", 0)
                loss = float(status.get("last_loss", 0.0) or 0.0)
                accuracy = float(status.get("last_accuracy", 0.0) or 0.0)
                gpu_mem = float(status.get("gpu_mem_allocated_mb", 0.0) or 0.0)
                gpu_reserved = float(status.get("gpu_mem_reserved_mb", 0.0) or 0.0)
                samples_sec = float(status.get("samples_per_sec", 0.0) or 0.0)
                dataset_size = int(status.get("dataset_size", 0) or 0)
                events_count = int(status.get("events_count", 0) or 0)
                is_continuous = bool(status.get("continuous_mode", False))

                checkpoint_count = 0
                safetensors_count = 0
                try:
                    import glob as _glob

                    g38_dir = project_root / "reports" / "g38_training"
                    if g38_dir.exists():
                        checkpoint_count = len(_glob.glob(str(g38_dir / "*.json")))
                    safetensors_count = len(
                        _glob.glob(str(project_root / "*.safetensors"))
                    )
                    safetensors_count += len(
                        _glob.glob(str(project_root / "training" / "*.safetensors"))
                    )
                except Exception:
                    pass

                duration_seconds = 0.0
                wall_clock = _time.time()
                try:
                    session = getattr(trainer, "_current_session", None)
                    if session and hasattr(session, "started_at"):
                        from datetime import datetime as _dt, timezone as _tz

                        start = _dt.fromisoformat(str(session.started_at))
                        duration_seconds = (_dt.now(_tz.utc) - start).total_seconds()
                except Exception:
                    try:
                        if trainer.events and len(trainer.events) > 0:
                            first_event = trainer.events[0]
                            if hasattr(first_event, "timestamp"):
                                from datetime import datetime as _dt2, timezone as _tz2

                                ts = _dt2.fromisoformat(str(first_event.timestamp))
                                duration_seconds = (
                                    _dt2.now(_tz2.utc) - ts
                                ).total_seconds()
                    except Exception:
                        pass

                gpu_temp = 0.0
                gpu_util_pct = 0.0
                try:
                    smi = _sp.run(
                        [
                            "nvidia-smi",
                            "--query-gpu=temperature.gpu,utilization.gpu",
                            "--format=csv,noheader,nounits",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if smi.returncode == 0:
                        parts = smi.stdout.strip().split(",")
                        gpu_temp = float(parts[0].strip())
                        gpu_util_pct = float(parts[1].strip())
                except Exception:
                    pass

                cpu_util = 0.0
                try:
                    import psutil

                    cpu_util = psutil.cpu_percent(interval=0)
                except Exception:
                    pass

                progress_pct = float(status.get("progress", 0) or 0)
                if is_continuous and is_training:
                    progress_pct = round(accuracy * 100, 1)

                return store_runtime_status_cached(
                    {
                        "api_version": 2,
                        "status": "active" if is_training else "idle",
                        "runtime": {
                            "total_epochs": total_epochs,
                            "completed_epochs": epoch,
                            "current_loss": loss,
                            "precision": accuracy,
                            "ece": None,
                            "drift_kl": None,
                            "duplicate_rate": None,
                            "gpu_util": gpu_util_pct,
                            "cpu_util": cpu_util,
                            "temperature": gpu_temp,
                            "determinism_status": None,
                            "freeze_status": None,
                            "mode": "CONTINUOUS"
                            if is_continuous
                            else status.get("training_mode", "MANUAL"),
                            "progress_pct": progress_pct,
                            "loss_trend": None,
                            "wall_clock_unix": wall_clock,
                            "monotonic_start_time": wall_clock - duration_seconds
                            if wall_clock
                            else 0,
                            "training_duration_seconds": duration_seconds,
                            "samples_per_sec": samples_sec,
                            "dataset_size": dataset_size,
                            "gpu_mem_allocated_mb": gpu_mem,
                            "gpu_mem_reserved_mb": gpu_reserved,
                            "events_count": events_count,
                            "checkpoints_saved": checkpoint_count,
                            "safetensors_files": safetensors_count,
                            "training_state": status.get("state", "IDLE"),
                            "continuous_mode": is_continuous,
                            "is_measured": True,
                        },
                        "determinism_ok": None,
                        "stale": False,
                        "last_update_ms": 0,
                        "signature": None,
                        "source": "g38_live",
                        "auto_repaired": repair_status.get("repaired", False),
                        "repair_issues": repair_status.get("issues", []),
                    }
                )
            except Exception:
                logger.exception("runtime_status G38 fallback failed")

        return store_runtime_status_cached(
            {
                "api_version": 2,
                "status": "unavailable",
                "reason": "No telemetry source available",
                "runtime": None,
                "determinism_ok": None,
                "stale": True,
                "last_update_ms": 0,
                "signature": None,
                "source": "none",
                "is_measured": False,
                "auto_repaired": repair_status.get("repaired", False),
                "repair_issues": repair_status.get("issues", []),
            }
        )

    try:
        import time as _time

        data, validation_error = read_validated_telemetry(telemetry_path)
        if data is None:
            try:
                telemetry_path.unlink(missing_ok=True)
            except OSError:
                pass

            if live_status is not None:
                logger.warning(
                    "Telemetry file validation failed (%s), falling back to G38 live trainer",
                    validation_error,
                )
                trainer = get_auto_trainer()
                status = live_status
                is_training = bool(status.get("is_training", False))
                epoch = status.get("epoch", 0)
                total_epochs_val = status.get("total_epochs", 0)
                loss_val = float(status.get("last_loss", 0.0) or 0.0)
                accuracy_val = float(status.get("last_accuracy", 0.0) or 0.0)
                wall_clock = _time.time()
                duration_seconds = 0.0
                try:
                    session = getattr(trainer, "_current_session", None)
                    if session and hasattr(session, "started_at"):
                        from datetime import datetime as _dt, timezone as _tz

                        start = _dt.fromisoformat(str(session.started_at))
                        duration_seconds = (_dt.now(_tz.utc) - start).total_seconds()
                except Exception:
                    pass
                cpu_util_val = 0.0
                try:
                    import psutil

                    cpu_util_val = psutil.cpu_percent(interval=0)
                except Exception:
                    pass
                gpu_temp_val = 0.0
                gpu_util_val = 0.0
                try:
                    import subprocess as _sp

                    smi = _sp.run(
                        [
                            "nvidia-smi",
                            "--query-gpu=temperature.gpu,utilization.gpu",
                            "--format=csv,noheader,nounits",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if smi.returncode == 0:
                        parts = smi.stdout.strip().split(",")
                        gpu_temp_val = float(parts[0].strip())
                        gpu_util_val = float(parts[1].strip())
                except Exception:
                    pass
                return store_runtime_status_cached(
                    {
                        "api_version": 2,
                        "status": "active" if is_training else "idle",
                        "runtime": {
                            "total_epochs": total_epochs_val,
                            "completed_epochs": epoch,
                            "current_loss": loss_val,
                            "precision": accuracy_val,
                            "ece": None,
                            "drift_kl": None,
                            "duplicate_rate": None,
                            "gpu_util": gpu_util_val,
                            "cpu_util": cpu_util_val,
                            "temperature": gpu_temp_val,
                            "determinism_status": None,
                            "freeze_status": None,
                            "mode": str(status.get("training_mode", "IDLE") or "IDLE"),
                            "progress_pct": round(accuracy_val * 100, 1)
                            if is_training
                            else 0,
                            "loss_trend": None,
                            "wall_clock_unix": wall_clock,
                            "monotonic_start_time": wall_clock - duration_seconds,
                            "training_duration_seconds": duration_seconds,
                            "training_state": str(
                                status.get("state", "IDLE") or "IDLE"
                            ),
                            "samples_per_sec": float(
                                status.get("samples_per_sec", 0.0) or 0.0
                            ),
                            "dataset_size": int(status.get("dataset_size", 0) or 0),
                            "is_measured": True,
                        },
                        "determinism_ok": None,
                        "stale": False,
                        "last_update_ms": 0,
                        "signature": None,
                        "source": "g38_live",
                        "auto_repaired": repair_status.get("repaired", False),
                        "repair_issues": repair_status.get("issues", []),
                    }
                )

            return store_runtime_status_cached(
                {
                    "status": "error",
                    "reason": validation_error
                    or "Telemetry integrity validation failed",
                    "runtime": None,
                    "determinism_ok": False,
                    "stale": True,
                    "last_update_ms": 0,
                    "signature": None,
                    "source": "telemetry_file",
                    "auto_repaired": repair_status.get("repaired", False),
                    "repair_issues": repair_status.get("issues", []),
                }
            )

        mod_time = telemetry_path.stat().st_mtime
        age_ms = int((_time.time() - mod_time) * 1000)
        is_stale = training_active and age_ms > 60000
        runtime_mode = "IDLE"
        training_state = "IDLE"
        samples_per_second = data.get("samples_per_second", 0.0)
        dataset_size = data.get("dataset_size", 0)
        checkpoints_saved = 0
        safetensors_files = 0
        if live_status is not None:
            runtime_mode = str(live_status.get("training_mode", "IDLE") or "IDLE")
            training_state = str(live_status.get("state", "IDLE") or "IDLE")
            samples_per_second = live_status.get("samples_per_sec", samples_per_second)
            dataset_size = live_status.get("dataset_size", dataset_size)
            checkpoints_saved = int(live_status.get("events_count", 0) or 0)
        status_value = "active" if training_active else "idle"

        return store_runtime_status_cached(
            {
                "status": status_value,
                "runtime": {
                    "total_epochs": data.get("total_epochs", 100),
                    "completed_epochs": data.get("epoch", 0),
                    "current_loss": data.get("loss", 0.0),
                    "precision": data.get("precision", 0.0),
                    "ece": data.get("ece", 0.0),
                    "drift_kl": data.get("kl_divergence", 0.0),
                    "duplicate_rate": data.get("duplicate_rate", 0.0),
                    "gpu_util": data.get("gpu_util", 0.0),
                    "cpu_util": data.get("cpu_util", 0.0),
                    "temperature": data.get("gpu_temperature", 0.0),
                    "determinism_status": data.get("determinism_status", False),
                    "freeze_status": data.get("freeze_status", False),
                    "mode": runtime_mode,
                    "progress_pct": min(
                        100.0,
                        (data.get("epoch", 0) / max(data.get("total_epochs", 100), 1))
                        * 100,
                    ),
                    "loss_trend": data.get("loss_trend", 0.0),
                    "wall_clock_unix": data.get("wall_clock_unix", 0),
                    "monotonic_start_time": data.get("monotonic_start_time", 0),
                    "training_duration_seconds": data.get(
                        "training_duration_seconds", 0.0
                    ),
                    "training_state": training_state,
                    "samples_per_sec": samples_per_second,
                    "dataset_size": dataset_size,
                    "checkpoints_saved": checkpoints_saved,
                    "safetensors_files": safetensors_files,
                },
                "determinism_ok": data.get("determinism_status", False),
                "stale": is_stale,
                "last_update_ms": age_ms,
                "signature": data.get("hmac", None),
                "source": "telemetry_file_self_healed"
                if repair_status.get("repaired")
                else "telemetry_file",
                "auto_repaired": repair_status.get("repaired", False),
                "repair_issues": repair_status.get("issues", []),
            }
        )
    except Exception:
        logger.exception("runtime_status failed")
        return store_runtime_status_cached(
            {
                "status": "error",
                "reason": "Internal error",
                "runtime": None,
                "determinism_ok": False,
                "stale": True,
                "last_update_ms": 0,
                "signature": None,
                "source": "telemetry_file",
                "auto_repaired": repair_status.get("repaired", False),
                "repair_issues": repair_status.get("issues", []),
            }
        )


def get_accuracy_snapshot_payload(
    *,
    project_root: Path,
    g38_available: bool,
    get_auto_trainer: Callable[[], Any],
    read_validated_telemetry: Callable[
        [Path], tuple[Optional[Dict[str, Any]], Optional[str]]
    ],
    logger,
) -> Dict[str, Any]:
    telemetry_path = project_root / "reports" / "training_telemetry.json"
    unavailable_response = {
        "api_version": 2,
        "precision": None,
        "recall": None,
        "ece_score": None,
        "dup_suppression_rate": None,
        "scope_compliance": None,
        "source": "unavailable",
        "is_measured": False,
        "reason": "No telemetry data available",
    }

    if not telemetry_path.exists():
        if g38_available:
            try:
                trainer = get_auto_trainer()
                status = trainer.get_status()
                accuracy = status.get("last_accuracy", 0.0)
                is_training = status.get("is_training", False)
                dataset_size = status.get("dataset_size", 0)
                return {
                    "api_version": 2,
                    "precision": accuracy,
                    "recall": None,
                    "ece_score": None,
                    "dup_suppression_rate": None,
                    "scope_compliance": 1.0 if is_training or accuracy > 0 else None,
                    "source": "g38_live",
                    "is_measured": accuracy > 0,
                    "training_active": is_training,
                    "dataset_size": dataset_size,
                }
            except Exception:
                logger.exception("accuracy_snapshot G38 fallback failed")
        return unavailable_response

    try:
        data, validation_error = read_validated_telemetry(telemetry_path)
        if data is None:
            logger.warning("accuracy_snapshot: validation failed: %s", validation_error)
            return {
                **unavailable_response,
                "reason": validation_error or "Validation failed",
            }
        return {
            "api_version": 2,
            "precision": data.get("precision"),
            "recall": data.get("recall"),
            "ece_score": data.get("ece"),
            "dup_suppression_rate": data.get("dup_suppression_rate"),
            "scope_compliance": data.get("scope_compliance"),
            "source": "telemetry_file",
            "is_measured": True,
        }
    except Exception:
        logger.exception("accuracy_snapshot failed")
        return {**unavailable_response, "reason": "Internal error reading telemetry"}
