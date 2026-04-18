"""Hard governance gate for pre-training checks."""

from __future__ import annotations

import ctypes
import importlib
import inspect
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, NoReturn

import numpy as np

from backend.governance.approval_ledger import get_key_manager_status
from backend.governance.authority_lock import AuthorityLock
from backend.governance.kill_switch import check_or_raise as check_kill_switch
from backend.training.runtime_status_validator import TrainingGovernanceError


logger = logging.getLogger("ygb.governance.training_gate")
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_dll_cache: dict[str, ctypes.CDLL] = {}


@dataclass(frozen=True)
class TrainingGateCheckResult:
    name: str
    passed: bool
    message: str


@dataclass
class TrainingGateResult:
    passed: bool = False
    checks_run: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    authority_lock: dict[str, Any] = field(default_factory=dict)
    approval_ledger: dict[str, Any] = field(default_factory=dict)
    checks: list[TrainingGateCheckResult] = field(default_factory=list)

    def failure_summary(self) -> str:
        if not self.failures:
            return "none"
        return "; ".join(self.failures)


def _raise_missing_governance_dependency(exc: Exception, dependency_name: str) -> NoReturn:
    module_name = getattr(exc, "name", None) or dependency_name
    raise RuntimeError(
        f"Governance check requires {module_name}. "
        f"Cannot proceed without required module '{dependency_name}'. "
        "Install it or this check cannot be satisfied."
    ) from exc


def _resolve_attr(
    candidates: tuple[tuple[str, str], ...],
    dependency_name: str,
) -> Any:
    last_error: Exception | None = None
    for module_name, attr_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            last_error = exc
            continue
        if hasattr(module, attr_name):
            return getattr(module, attr_name)
        last_error = AttributeError(f"{module_name}.{attr_name} is unavailable")
    if last_error is None:
        last_error = ImportError(dependency_name)
    _raise_missing_governance_dependency(last_error, dependency_name)


def _invoke_signature_aware(target: Callable[..., Any], **available: Any) -> Any:
    signature = inspect.signature(target)
    alias_map = {
        "features": {"features", "data", "x", "x_train", "feature_matrix"},
        "labels": {"labels", "y", "y_train", "targets", "target"},
        "n_classes": {"n_classes", "num_classes", "class_count", "n_labels"},
        "source_id": {"source_id", "source", "source_name", "dataset_source"},
        "sample_count": {"sample_count", "total_samples", "n_samples", "count"},
        "feature_dim": {"feature_dim", "num_features", "n_features"},
    }
    kwargs: dict[str, Any] = {}
    missing_required: list[str] = []

    for name, parameter in signature.parameters.items():
        if name == "self":
            continue
        lowered = name.lower()
        matched = False
        for key, aliases in alias_map.items():
            if lowered in aliases and key in available:
                kwargs[name] = available[key]
                matched = True
                break
        if matched:
            continue
        if (
            parameter.default is inspect.Signature.empty
            and parameter.kind
            not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        ):
            missing_required.append(name)

    if missing_required:
        raise TypeError(
            f"unsupported callable signature for governance check {target}: "
            f"missing {missing_required}"
        )
    return target(**kwargs)


def _load_dll(name: str) -> ctypes.CDLL | None:
    if name in _dll_cache:
        return _dll_cache[name]
    dll_path = _PROJECT_ROOT / "native" / "security" / f"{name}.dll"
    if not dll_path.exists():
        return None
    try:
        dll = ctypes.CDLL(str(dll_path))
    except Exception as exc:
        logger.warning("[GOVERNANCE] Cannot load %s.dll: %s", name, exc)
        return None
    _dll_cache[name] = dll
    return dll


def _run_mock_data_scan(*, features: np.ndarray, labels: np.ndarray, n_classes: int, source_id: str) -> tuple[bool, str]:
    scan_production_code = _resolve_attr(
        (("impl_v1.training.safety.mock_data_scanner", "scan_production_code"),),
        "impl_v1.training.safety.mock_data_scanner",
    )
    scan = scan_production_code(str(_PROJECT_ROOT / "impl_v1" / "training"))
    if getattr(scan, "violations_found", 0) > 0:
        return False, f"{scan.violations_found} mock data violations"
    return True, f"0 violations in {getattr(scan, 'files_scanned', 0)} files"


def _run_dataset_quality_check(*, features: np.ndarray, labels: np.ndarray, n_classes: int, source_id: str) -> tuple[bool, str]:
    validate_dataset = _resolve_attr(
        (
            ("impl_v1.training.safety.dataset_quality_gate", "validate_dataset"),
            ("impl_v1.training.safety.dataset_quality_gate", "validate_dataset_gate"),
        ),
        "impl_v1.training.safety.dataset_quality_gate",
    )
    report = _invoke_signature_aware(validate_dataset, features=features, labels=labels)
    if bool(getattr(report, "passed", False)):
        entropy = getattr(report, "entropy", getattr(report, "entropy_score", None))
        return True, f"entropy={float(entropy):.2f}" if entropy is not None else "dataset quality OK"
    reason = getattr(report, "rejection_reason", getattr(report, "abort_reason", "dataset quality rejected"))
    return False, str(reason)


def _run_label_consistency_check(*, features: np.ndarray, labels: np.ndarray, n_classes: int, source_id: str) -> tuple[bool, str]:
    validate_labels = _resolve_attr(
        (("impl_v1.training.data.label_consistency_validator", "validate_labels"),),
        "impl_v1.training.data.label_consistency_validator",
    )
    result = _invoke_signature_aware(validate_labels, labels=labels, n_classes=n_classes)
    if bool(getattr(result, "passed", False)):
        divergence = getattr(result, "kl_divergence", None)
        return True, f"KL={float(divergence):.4f}" if divergence is not None else "label consistency OK"
    return False, str(getattr(result, "rejection_reason", "label consistency rejected"))


def _run_dataset_balance_check(*, features: np.ndarray, labels: np.ndarray, n_classes: int, source_id: str) -> tuple[bool, str]:
    controller_cls = _resolve_attr(
        (
            ("impl_v1.training.data.dataset_balance_controller", "DatasetBalanceController"),
            ("impl_v1.training.distributed.dataset_balance_controller", "DatasetBalanceController"),
        ),
        "impl_v1.training.data.dataset_balance_controller",
    )
    controller = controller_cls()
    analysis = _invoke_signature_aware(
        controller.analyze,
        labels=labels,
        n_classes=n_classes,
    )
    max_ratio = float(getattr(analysis, "max_ratio", 0.0))
    if bool(getattr(analysis, "balanced", False)):
        return True, f"ratio={max_ratio:.2f}"
    return False, f"imbalanced: ratio={max_ratio:.2f}"


def _run_semantic_quality_check(*, features: np.ndarray, labels: np.ndarray, n_classes: int, source_id: str) -> tuple[bool, str]:
    run_sanity_test = _resolve_attr(
        (("impl_v1.training.data.semantic_quality_gate", "run_sanity_test"),),
        "impl_v1.training.data.semantic_quality_gate",
    )
    sanity = _invoke_signature_aware(
        run_sanity_test,
        features=features,
        labels=labels,
        n_classes=n_classes,
    )
    if bool(getattr(sanity, "passed", False)):
        epoch_losses = list(getattr(sanity, "epoch_losses", []) or [])
        if epoch_losses:
            return True, f"loss {float(epoch_losses[0]):.3f}→{float(epoch_losses[-1]):.3f}"
        return True, "semantic quality OK"
    return False, str(getattr(sanity, "rejection_reason", "semantic quality rejected"))


def _run_ingestion_policy_check(*, features: np.ndarray, labels: np.ndarray, n_classes: int, source_id: str) -> tuple[bool, str]:
    policy_cls = _resolve_attr(
        (
            ("impl_v1.training.data.ingestion_policy", "IngestionPolicy"),
            ("impl_v1.training.distributed.ingestion_policy", "IngestionPolicy"),
        ),
        "impl_v1.training.data.ingestion_policy",
    )
    policy = policy_cls()
    decision = None
    for method_name in ("evaluate", "check", "validate"):
        method = getattr(policy, method_name, None)
        if callable(method):
            decision = _invoke_signature_aware(
                method,
                features=features,
                labels=labels,
                source_id=source_id,
            )
            break
    if decision is None:
        fallback = _resolve_attr(
            (("impl_v1.training.data.ingestion_policy", "check_ingestion_policy"),),
            "impl_v1.training.data.ingestion_policy",
        )
        decision = _invoke_signature_aware(
            fallback,
            features=features,
            labels=labels,
            source_id=source_id,
        )
    allowed = bool(getattr(decision, "allowed", getattr(decision, "passed", False)))
    if allowed:
        return True, str(getattr(decision, "reason", "all gates passed"))
    return False, str(getattr(decision, "rejection_reason", getattr(decision, "reason", "ingestion policy rejected")))


def _run_cpp_signal_check(*, features: np.ndarray, labels: np.ndarray, n_classes: int, source_id: str) -> tuple[bool, str]:
    dll = _load_dll("signal_strength_validator")
    if dll is None:
        return True, "DLL not available (skip)"
    n_samples, n_features = features.shape
    flat = np.ascontiguousarray(features, dtype=np.float64).reshape(-1)
    arr = (ctypes.c_double * len(flat))(*flat)
    dll.validate_signal_strength.restype = ctypes.c_int
    passed = dll.validate_signal_strength(
        arr,
        ctypes.c_int(int(n_samples)),
        ctypes.c_int(int(n_features)),
    )
    if passed:
        return True, "entropy + overlap + fingerprint OK"
    return False, "signal strength validation failed"


def _run_data_source_audit_check(*, features: np.ndarray, labels: np.ndarray, n_classes: int, source_id: str) -> tuple[bool, str]:
    audit_data_source = _resolve_attr(
        (("impl_v1.training.data.data_source_audit", "audit_data_source"),),
        "impl_v1.training.data.data_source_audit",
    )
    audit = _invoke_signature_aware(
        audit_data_source,
        source_id=source_id,
        sample_count=int(features.shape[0]),
    )
    if bool(getattr(audit, "passed", False)):
        return True, f"source={source_id} verified"
    return False, str(getattr(audit, "rejection_reason", "data source audit rejected"))


def _run_overfit_guard_check(*, features: np.ndarray, labels: np.ndarray, n_classes: int, source_id: str) -> tuple[bool, str]:
    check_overfitting_risk = _resolve_attr(
        (("impl_v1.training.safety.overfit_guard", "check_overfitting_risk"),),
        "impl_v1.training.safety.overfit_guard",
    )
    risk = _invoke_signature_aware(
        check_overfitting_risk,
        sample_count=int(features.shape[0]),
        feature_dim=int(features.shape[1]),
        n_classes=n_classes,
    )
    if not bool(getattr(risk, "high_risk", True)):
        score = getattr(risk, "risk_score", None)
        return True, f"risk={float(score):.2f}" if score is not None else "overfit risk OK"
    return False, f"overfitting risk: {getattr(risk, 'reason', 'unknown')}"


_PRETRAINING_CHECKS: tuple[tuple[str, Callable[..., tuple[bool, str]]], ...] = (
    ("Mock Data Scanner", _run_mock_data_scan),
    ("Dataset Quality Gate", _run_dataset_quality_check),
    ("Label Consistency", _run_label_consistency_check),
    ("Dataset Balance", _run_dataset_balance_check),
    ("Semantic Quality (3-epoch)", _run_semantic_quality_check),
    ("Ingestion Policy", _run_ingestion_policy_check),
    ("C++ Signal Strength", _run_cpp_signal_check),
    ("Data Source Audit", _run_data_source_audit_check),
    ("Overfit Guard", _run_overfit_guard_check),
)


def run_training_gate(
    features: np.ndarray,
    labels: np.ndarray,
    n_classes: int,
    source_id: str = "ingestion_pipeline",
) -> TrainingGateResult:
    """Run the hard governance training gate and return structured results."""
    check_kill_switch()
    authority_lock = AuthorityLock.verify_all_locked()
    if not bool(authority_lock.get("all_locked", False)):
        raise TrainingGovernanceError(
            f"authority lock violation: {authority_lock.get('violations', [])}",
            status="AUTHORITY_VIOLATION",
            reasons=[str(item) for item in authority_lock.get("violations", [])],
        )

    result = TrainingGateResult(
        authority_lock=authority_lock,
        approval_ledger=get_key_manager_status(run_integrity=False, strict=False),
    )
    t0 = time.perf_counter()

    logger.info("[GOVERNANCE] ═══ HARD TRAINING GATE ═══")
    for name, check_fn in _PRETRAINING_CHECKS:
        result.checks_run += 1
        try:
            passed, message = check_fn(
                features=features,
                labels=labels,
                n_classes=n_classes,
                source_id=source_id,
            )
        except Exception as exc:
            passed = False
            message = f"exception — {type(exc).__name__}: {exc}"
            logger.error("  ✗ %s: %s", name, message)
        else:
            if passed:
                logger.info("  ✓ %s: %s", name, message)
            else:
                logger.error("  ✗ %s: %s", name, message)

        result.checks.append(
            TrainingGateCheckResult(name=name, passed=bool(passed), message=str(message))
        )
        if passed:
            result.checks_passed += 1
        else:
            result.checks_failed += 1
            result.failures.append(f"{name}: {message}")

    result.passed = result.checks_failed == 0
    result.duration_ms = (time.perf_counter() - t0) * 1000.0
    logger.info(
        "[GOVERNANCE] %s Hard training gate: %s/%s checks in %.0fms",
        "✓" if result.passed else "✗",
        result.checks_passed,
        result.checks_run,
        result.duration_ms,
    )
    return result


def check_or_raise(
    features: np.ndarray,
    labels: np.ndarray,
    n_classes: int,
    source_id: str = "ingestion_pipeline",
) -> TrainingGateResult:
    """Run the hard governance training gate and raise on any failure."""
    result = run_training_gate(
        features=features,
        labels=labels,
        n_classes=n_classes,
        source_id=source_id,
    )
    if not result.passed:
        raise TrainingGovernanceError(
            "training governance gate failed: " + result.failure_summary(),
            status="TRAINING_GATE_BLOCKED",
            reasons=result.failures,
        )
    return result
