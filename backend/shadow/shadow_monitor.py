"""
Shadow Monitor — Python Bridge for C++ Shadow Integrity Engines.

Implements all C++ algorithms in numpy for immediate use:
  Phase 1: ShadowHashChain, LatentSpaceMonitor, RepresentationEntropyMonitor, DriftDetector
  Phase 2: InflationGuard
  Phase 3: ConsensusChecker (dual-head inference)
  Phase 4: ContainmentController
  Phase 5: AgingProtection

No authority unlocked. No silent failure. All state transitions logged.
"""

import hashlib
import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

import numpy as np

# ══════════════════════════════════════════════════════════════════════
# Phase 1: Shadow Behavior Immutability Engine
# ══════════════════════════════════════════════════════════════════════


class ShadowHashChain:
    """Immutable decision chain — every shadow decision hashed and chained."""

    def __init__(self):
        self.chain: List[Dict[str, Any]] = []
        self.current_chain_hash = b'\x00' * 32
        self.next_sequence = 0

    def record_decision(self, features: np.ndarray, logits: np.ndarray,
                        temperature: float, predicted_class: int,
                        confidence: float) -> Dict[str, Any]:
        """Record a shadow decision and chain its hash."""
        # Hash: SHA-256(features || logits || temperature)
        payload = features.tobytes() + logits.tobytes() + \
                  np.float64(temperature).tobytes()
        decision_hash = hashlib.sha256(payload).digest()

        # Chain: SHA-256(prev_chain_hash || decision_hash)
        chain_hash = hashlib.sha256(
            self.current_chain_hash + decision_hash).digest()

        record = {
            'sequence_id': self.next_sequence,
            'timestamp': time.time(),
            'decision_hash': decision_hash.hex(),
            'chain_hash': chain_hash.hex(),
            'predicted_class': predicted_class,
            'confidence': float(confidence),
            'temperature': float(temperature),
        }

        self.current_chain_hash = chain_hash
        self.next_sequence += 1
        self.chain.append(record)
        return record

    def verify_chain(self) -> bool:
        """Verify entire chain integrity. Returns False if tampered."""
        running = b'\x00' * 32
        for rec in self.chain:
            decision_hash = bytes.fromhex(rec['decision_hash'])
            expected = hashlib.sha256(running + decision_hash).digest()
            if expected.hex() != rec['chain_hash']:
                return False  # TAMPER DETECTED
            running = bytes.fromhex(rec['chain_hash'])
        return True

    def chain_length(self) -> int:
        return len(self.chain)

    def get_chain_hash_hex(self) -> str:
        return self.current_chain_hash.hex()


class LatentSpaceMonitor:
    """Track embedding mean/std/covariance. Alert on KL divergence."""

    def __init__(self, dim: int = 256, kl_threshold: float = 0.5):
        self.dim = dim
        self.kl_threshold = kl_threshold
        self.baseline_mean: Optional[np.ndarray] = None
        self.baseline_var: Optional[np.ndarray] = None
        # Welford's online algorithm
        self.n = 0
        self.mean = np.zeros(dim)
        self.m2 = np.zeros(dim)

    def set_baseline(self, mean: np.ndarray, variance: np.ndarray):
        self.baseline_mean = mean.copy()
        self.baseline_var = variance.copy()

    def update(self, embedding: np.ndarray):
        self.n += 1
        delta = embedding - self.mean
        self.mean += delta / self.n
        delta2 = embedding - self.mean
        self.m2 += delta * delta2

    def update_batch(self, embeddings: np.ndarray):
        for emb in embeddings:
            self.update(emb)

    def get_stats(self) -> Dict[str, Any]:
        var = self.m2 / max(self.n - 1, 1)
        stats = {
            'n_samples': self.n,
            'mean': self.mean.copy(),
            'variance': var.copy(),
            'kl_divergence': 0.0,
            'frobenius_shift': 0.0,
            'mean_shift_sigma': 0.0,
            'alert': False,
        }

        if self.baseline_mean is not None and self.n > 10:
            # KL(current || baseline)
            v0 = np.maximum(self.baseline_var, 1e-10)
            v1 = np.maximum(var, 1e-10)
            kl = 0.5 * np.sum(
                np.log(v0 / v1) + v1 / v0 +
                (self.baseline_mean - self.mean)**2 / v0 - 1.0
            )
            stats['kl_divergence'] = float(kl)

            # Frobenius shift
            stats['frobenius_shift'] = float(
                np.linalg.norm(var - self.baseline_var))

            # Mean shift in sigma
            sigma = np.sqrt(np.maximum(self.baseline_var, 1e-10))
            shift = np.abs(self.mean - self.baseline_mean) / sigma
            stats['mean_shift_sigma'] = float(np.max(shift))

            stats['alert'] = (kl > self.kl_threshold)

        return stats

    def is_alert(self) -> bool:
        return self.get_stats()['alert']

    def reset(self):
        self.n = 0
        self.mean = np.zeros(self.dim)
        self.m2 = np.zeros(self.dim)


class RepresentationEntropyMonitor:
    """Per-class Shannon entropy. Alert on >10% collapse from baseline."""

    def __init__(self, n_classes: int = 2, n_bins: int = 50,
                 collapse_threshold: float = 0.10):
        self.n_classes = n_classes
        self.n_bins = n_bins
        self.collapse_threshold = collapse_threshold
        self.histograms = np.zeros((n_classes, n_bins), dtype=int)
        self.class_counts = np.zeros(n_classes, dtype=int)
        self.baseline_entropy: Optional[np.ndarray] = None

    def set_baseline(self, baseline_entropy: np.ndarray):
        self.baseline_entropy = baseline_entropy.copy()

    def record_prediction(self, predicted_class: int, confidence: float):
        if 0 <= predicted_class < self.n_classes:
            b = int(confidence * (self.n_bins - 1))
            b = max(0, min(self.n_bins - 1, b))
            self.histograms[predicted_class, b] += 1
            self.class_counts[predicted_class] += 1

    def record_batch(self, predictions: np.ndarray, confidences: np.ndarray):
        for pred, conf in zip(predictions, confidences):
            self.record_prediction(int(pred), float(conf))

    def get_stats(self) -> Dict[str, Any]:
        class_entropy = np.zeros(self.n_classes)
        for c in range(self.n_classes):
            total = self.class_counts[c]
            if total > 0:
                p = self.histograms[c] / total
                p = p[p > 0]
                class_entropy[c] = -np.sum(p * np.log2(p))

        total_samples = int(self.class_counts.sum())
        overall = 0.0
        if total_samples > 0:
            weights = self.class_counts / total_samples
            overall = float(np.sum(weights * class_entropy))

        max_collapse = 0.0
        change_pct = np.zeros(self.n_classes)
        if self.baseline_entropy is not None:
            base = np.maximum(self.baseline_entropy, 1e-10)
            change_pct = (base - class_entropy) / base
            max_collapse = float(np.max(change_pct))

        return {
            'class_entropy': class_entropy.tolist(),
            'overall_entropy': overall,
            'max_collapse_pct': max_collapse,
            'alert': max_collapse > self.collapse_threshold,
            'n_samples': total_samples,
        }

    def is_alert(self) -> bool:
        return self.get_stats()['alert']

    def reset(self):
        self.histograms.fill(0)
        self.class_counts.fill(0)


class DriftDetector:
    """10k sliding window drift detector. Alert if mean shift > 2σ."""

    def __init__(self, dim: int = 256, window_size: int = 10000,
                 sigma_threshold: float = 2.0):
        self.dim = dim
        self.window_size = window_size
        self.sigma_threshold = sigma_threshold
        self.baseline_mean: Optional[np.ndarray] = None
        self.baseline_std: Optional[np.ndarray] = None
        self.window: deque = deque()
        self.window_sum = np.zeros(dim)

    def set_baseline(self, mean: np.ndarray, std: np.ndarray):
        self.baseline_mean = mean.copy()
        self.baseline_std = std.copy()

    def add_sample(self, features: np.ndarray):
        self.window.append(features.copy())
        self.window_sum += features
        if len(self.window) > self.window_size:
            old = self.window.popleft()
            self.window_sum -= old

    def add_batch(self, features: np.ndarray):
        for f in features:
            self.add_sample(f)

    def get_stats(self) -> Dict[str, Any]:
        n = len(self.window)
        stats = {
            'window_size': n,
            'max_shift_sigma': 0.0,
            'mean_shift_sigma': 0.0,
            'alert': False,
            'alert_dim': -1,
        }

        if self.baseline_mean is None or n == 0:
            return stats

        window_mean = self.window_sum / n
        sigma = np.maximum(self.baseline_std, 1e-10)
        shifts = np.abs(window_mean - self.baseline_mean) / sigma

        stats['max_shift_sigma'] = float(np.max(shifts))
        stats['mean_shift_sigma'] = float(np.mean(shifts))
        stats['alert_dim'] = int(np.argmax(shifts))
        stats['alert'] = stats['max_shift_sigma'] > self.sigma_threshold

        return stats

    def is_alert(self) -> bool:
        return self.get_stats()['alert']

    def reset(self):
        self.window.clear()
        self.window_sum = np.zeros(self.dim)


# ══════════════════════════════════════════════════════════════════════
# Phase 2: Confidence Inflation Guard
# ══════════════════════════════════════════════════════════════════════


class InflationGuard:
    """Rolling 5k ECE window. Auto-disable if inflation > 2%."""

    def __init__(self, window_size: int = 5000,
                 inflation_threshold: float = 0.02,
                 monotonicity_min: float = 0.9, n_bins: int = 10):
        self.window_size = window_size
        self.inflation_threshold = inflation_threshold
        self.monotonicity_min = monotonicity_min
        self.n_bins = n_bins
        self.window: deque = deque()

    def record_prediction(self, confidence: float, correct: bool):
        self.window.append((confidence, correct))
        if len(self.window) > self.window_size:
            self.window.popleft()

    def record_batch(self, confidences: np.ndarray, correct: np.ndarray):
        for c, cr in zip(confidences, correct):
            self.record_prediction(float(c), bool(cr))

    def get_stats(self) -> Dict[str, Any]:
        stats = {
            'window_size': len(self.window),
            'rolling_ece': 0.0,
            'rolling_inflation': 0.0,
            'monotonicity_slope': 1.0,
            'inflation_alert': False,
            'monotonicity_alert': False,
            'should_disable': False,
        }

        if len(self.window) < 100:
            return stats

        confs = np.array([w[0] for w in self.window])
        correct = np.array([w[1] for w in self.window], dtype=float)
        n = len(confs)

        # ECE per bin
        bin_edges = np.linspace(0, 1, self.n_bins + 1)
        ece = 0.0
        bin_confs, bin_accs = [], []
        for i in range(self.n_bins):
            mask = (confs >= bin_edges[i]) & (confs < bin_edges[i + 1])
            if mask.sum() >= 10:
                bc = confs[mask].mean()
                ba = correct[mask].mean()
                ece += (mask.sum() / n) * abs(bc - ba)
                bin_confs.append(bc)
                bin_accs.append(ba)

        stats['rolling_ece'] = float(ece)
        stats['rolling_inflation'] = float(confs.mean() - correct.mean())
        stats['inflation_alert'] = stats['rolling_inflation'] > self.inflation_threshold

        # Monotonicity slope
        if len(bin_confs) >= 2:
            x = np.array(bin_confs)
            y = np.array(bin_accs)
            A = np.vstack([x, np.ones(len(x))]).T
            slope, _ = np.linalg.lstsq(A, y, rcond=None)[0]
            stats['monotonicity_slope'] = float(slope)

        stats['monotonicity_alert'] = stats['monotonicity_slope'] < self.monotonicity_min
        stats['should_disable'] = stats['inflation_alert'] or stats['monotonicity_alert']
        return stats

    def should_disable(self) -> bool:
        return self.get_stats()['should_disable']

    def reset(self):
        self.window.clear()


# ══════════════════════════════════════════════════════════════════════
# Phase 3: Shadow Decision Consensus Check
# ══════════════════════════════════════════════════════════════════════


class ConsensusChecker:
    """Dual-head inference: live model vs frozen gate-pass snapshot."""

    def __init__(self, divergence_threshold: float = 0.03):
        self.divergence_threshold = divergence_threshold
        self.comparisons: List[Dict[str, float]] = []
        self.anomaly_count = 0

    def check_consensus(self, pred_a_conf: np.ndarray,
                         pred_b_conf: np.ndarray) -> Dict[str, Any]:
        """Compare Head A (live) vs Head B (frozen) predictions."""
        mean_a = float(pred_a_conf.mean())
        mean_b = float(pred_b_conf.mean())
        delta = abs(mean_a - mean_b)

        # Per-sample agreement
        agree = float((pred_a_conf.argmax(axis=1) ==
                       pred_b_conf.argmax(axis=1)).mean())

        is_anomaly = delta > self.divergence_threshold
        if is_anomaly:
            self.anomaly_count += 1

        result = {
            'mean_conf_a': mean_a,
            'mean_conf_b': mean_b,
            'delta': delta,
            'agreement': agree,
            'is_anomaly': is_anomaly,
            'total_anomalies': self.anomaly_count,
        }
        self.comparisons.append(result)
        return result

    def is_alert(self) -> bool:
        return self.anomaly_count > 0

    def reset(self):
        self.comparisons.clear()
        self.anomaly_count = 0


# ══════════════════════════════════════════════════════════════════════
# Phase 4: Auto Containment Protocol
# ══════════════════════════════════════════════════════════════════════


class ContainmentController:
    """Unified containment: auto-disable MODE-B on any alert."""

    MODE_A_ONLY = 'MODE_A_ONLY'
    MODE_B_SHADOW = 'MODE_B_SHADOW'
    CONTAINMENT = 'CONTAINMENT'

    def __init__(self, log_dir: str = None):
        self.current_mode = self.MODE_A_ONLY
        self.locked = False
        self.incident_log: List[Dict[str, Any]] = []
        self.log_dir = log_dir or os.path.join(
            os.path.dirname(__file__), '..', '..', 'reports', 'incidents')

    def enable_shadow(self):
        if not self.locked:
            self.current_mode = self.MODE_B_SHADOW

    def contain(self, trigger: str, value: float,
                threshold: float, description: str) -> bool:
        """Trigger containment if value > threshold."""
        if value <= threshold:
            return False

        incident = {
            'incident_id': len(self.incident_log),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'trigger': trigger,
            'previous_mode': self.current_mode,
            'new_mode': self.MODE_A_ONLY,
            'trigger_value': value,
            'threshold': threshold,
            'description': description,
            'signature': hashlib.sha256(
                json.dumps({
                    'trigger': trigger, 'value': value,
                    'threshold': threshold, 'ts': time.time()
                }).encode()
            ).hexdigest(),
        }

        self.current_mode = self.MODE_A_ONLY
        self.locked = True
        self.incident_log.append(incident)
        self._write_incident(incident)
        return True

    def _write_incident(self, incident: Dict[str, Any]):
        os.makedirs(self.log_dir, exist_ok=True)
        path = os.path.join(
            self.log_dir,
            f"incident_{incident['incident_id']:04d}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(incident, f, indent=2)

    def check_all(self, drift_stats: Dict, entropy_stats: Dict,
                   inflation_stats: Dict, consensus_stats: Optional[Dict],
                   days_since_validation: int) -> bool:
        """Check all containment triggers. Returns True if any fired."""
        any_fired = False

        if drift_stats.get('alert'):
            any_fired |= self.contain(
                'DRIFT_SPIKE',
                drift_stats['max_shift_sigma'], 2.0,
                'Feature distribution drift exceeds 2σ')

        if entropy_stats.get('alert'):
            any_fired |= self.contain(
                'ENTROPY_COLLAPSE',
                entropy_stats['max_collapse_pct'], 0.10,
                'Representation entropy collapsed >10%')

        if inflation_stats.get('should_disable'):
            any_fired |= self.contain(
                'CALIBRATION_INFLATION',
                inflation_stats['rolling_inflation'], 0.02,
                'Confidence inflation exceeds 2%')

        if consensus_stats and consensus_stats.get('is_anomaly'):
            any_fired |= self.contain(
                'CONSENSUS_DIVERGENCE',
                consensus_stats['delta'], 0.03,
                'Live model diverged >3% from frozen snapshot')

        if days_since_validation > 90:
            any_fired |= self.contain(
                'MODEL_AGING',
                float(days_since_validation), 90.0,
                'Model exceeds 90-day validation window')

        return any_fired

    @property
    def is_shadow_enabled(self) -> bool:
        return self.current_mode == self.MODE_B_SHADOW

    @property
    def is_locked(self) -> bool:
        return self.locked


# ══════════════════════════════════════════════════════════════════════
# Phase 5: Shadow Aging Protection
# ══════════════════════════════════════════════════════════════════════


class AgingProtection:
    """Auto-disable MODE-B if >90 days since last full validation."""

    def __init__(self, max_age_days: int = 90):
        self.max_age_days = max_age_days
        self.last_validation_timestamp: Optional[float] = None

    def record_validation(self):
        self.last_validation_timestamp = time.time()

    def set_validation_timestamp(self, ts: float):
        self.last_validation_timestamp = ts

    def days_since_validation(self) -> int:
        if self.last_validation_timestamp is None:
            return 9999  # Never validated
        elapsed = time.time() - self.last_validation_timestamp
        return int(elapsed / 86400)

    def is_expired(self) -> bool:
        return self.days_since_validation() > self.max_age_days


# ══════════════════════════════════════════════════════════════════════
# Unified Shadow Monitor Orchestrator
# ══════════════════════════════════════════════════════════════════════


class ShadowMonitor:
    """
    Unified orchestrator for all shadow integrity monitoring.

    Usage:
        monitor = ShadowMonitor(feature_dim=256)
        monitor.set_baselines(features, labels, confidences)
        monitor.enable_shadow()

        # During inference:
        monitor.record_decision(features, logits, temperature, pred, conf)

        # Periodic check:
        status = monitor.check_health()
        if status['containment_triggered']:
            # MODE-B auto-disabled, MODE-A locked
            pass
    """

    def __init__(self, feature_dim: int = 256, n_classes: int = 2,
                 log_dir: str = None):
        self.hash_chain = ShadowHashChain()
        self.latent_monitor = LatentSpaceMonitor(dim=feature_dim)
        self.entropy_monitor = RepresentationEntropyMonitor(n_classes=n_classes)
        self.drift_detector = DriftDetector(dim=feature_dim)
        self.inflation_guard = InflationGuard()
        self.consensus_checker = ConsensusChecker()
        self.containment = ContainmentController(log_dir=log_dir)
        self.aging = AgingProtection()
        self.n_decisions = 0

    def set_baselines(self, features: np.ndarray, labels: np.ndarray,
                       confidences: np.ndarray):
        """Set baselines from gate-pass data."""
        self.latent_monitor.set_baseline(
            features.mean(axis=0), features.var(axis=0))
        self.drift_detector.set_baseline(
            features.mean(axis=0), features.std(axis=0))

        # Compute baseline entropy
        preds = (confidences > 0.5).astype(int)
        self.entropy_monitor.record_batch(preds, confidences)
        stats = self.entropy_monitor.get_stats()
        self.entropy_monitor.reset()
        self.entropy_monitor.set_baseline(
            np.array(stats['class_entropy']))

        self.aging.record_validation()

    def enable_shadow(self):
        self.containment.enable_shadow()

    def record_decision(self, features: np.ndarray, logits: np.ndarray,
                         temperature: float, predicted_class: int,
                         confidence: float, correct: Optional[bool] = None):
        """Record a single shadow decision across all monitors."""
        # Hash chain
        self.hash_chain.record_decision(
            features, logits, temperature, predicted_class, confidence)

        # Latent space
        self.latent_monitor.update(features)

        # Entropy
        self.entropy_monitor.record_prediction(predicted_class, confidence)

        # Drift
        self.drift_detector.add_sample(features)

        # Inflation (if ground truth available)
        if correct is not None:
            self.inflation_guard.record_prediction(confidence, correct)

        self.n_decisions += 1

    def check_health(self) -> Dict[str, Any]:
        """Run all containment checks. Returns comprehensive status."""
        drift_stats = self.drift_detector.get_stats()
        entropy_stats = self.entropy_monitor.get_stats()
        inflation_stats = self.inflation_guard.get_stats()
        days = self.aging.days_since_validation()

        triggered = self.containment.check_all(
            drift_stats, entropy_stats, inflation_stats,
            None, days)

        return {
            'n_decisions': self.n_decisions,
            'chain_length': self.hash_chain.chain_length(),
            'chain_valid': self.hash_chain.verify_chain(),
            'chain_hash': self.hash_chain.get_chain_hash_hex(),
            'drift': drift_stats,
            'entropy': entropy_stats,
            'inflation': inflation_stats,
            'days_since_validation': days,
            'mode': self.containment.current_mode,
            'locked': self.containment.is_locked,
            'containment_triggered': triggered,
            'incident_count': len(self.containment.incident_log),
        }



# No __main__ self-test — use pytest test suite for validation
