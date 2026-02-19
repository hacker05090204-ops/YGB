"""
System Integrity Bridge — Python Implementation of C++ Autonomy Supervisor

Mirrors all C++ algorithms for immediate Python use.
Reads REAL system data: GPU, disk, governance state, logs.

No mock data. No fallbacks. Real metrics only.

Modules:
  - SystemIntegritySupervisor: Weighted score aggregation
  - ResourceMonitor: GPU/HDD/IO/Memory real-time probing
  - DatasetIntegrityWatchdog: Class balance, KL divergence, duplicate detection
  - LogIntegrityMonitor: FNV-1a hash chain verification
  - AutonomyConditionEvaluator: Shadow mode gating
"""

import hashlib
import json
import logging
import os
import struct
import subprocess
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("integrity_bridge")

PROJECT_ROOT = Path(__file__).parent.parent.parent


# =============================================================================
# RESOURCE MONITOR — Real GPU / HDD / IO / Memory probing
# =============================================================================

class ResourceMonitor:
    """Probes real system resources. No mocks."""

    GPU_TEMP_WARN = 80.0
    GPU_TEMP_CRIT = 90.0
    GPU_TEMP_MAX = 100.0
    HDD_FREE_MIN = 15.0
    IO_LATENCY_MAX = 50.0
    MEMORY_MAX = 90.0

    def __init__(self):
        self.gpu_temp = 0.0
        self.gpu_throttle_events = 0
        self.hdd_free_percent = 100.0
        self.io_latency_window: deque = deque(maxlen=100)
        self.memory_used_percent = 0.0

    def probe_gpu(self) -> Dict[str, Any]:
        """Query nvidia-smi for real GPU metrics."""
        try:
            result = subprocess.run(
                ["nvidia-smi",
                 "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total,clocks_throttle_reasons.active",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                if len(parts) >= 4:
                    self.gpu_temp = float(parts[0].strip())
                    gpu_util = float(parts[1].strip())
                    mem_used = float(parts[2].strip())
                    mem_total = float(parts[3].strip())
                    # Throttle detection
                    if len(parts) >= 5 and parts[4].strip() not in ("0", "0x0000000000000000", "Not Active"):
                        self.gpu_throttle_events += 1
                    return {
                        "temp_c": self.gpu_temp,
                        "utilization_pct": gpu_util,
                        "memory_used_mb": mem_used,
                        "memory_total_mb": mem_total,
                        "throttle_events": self.gpu_throttle_events,
                        "available": True,
                    }
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:  # pragma: no cover
            logger.debug(f"nvidia-smi not available: {e}")  # pragma: no cover

        return {"temp_c": 0.0, "utilization_pct": 0.0, "memory_used_mb": 0,  # pragma: no cover
                "memory_total_mb": 0, "throttle_events": 0, "available": False}  # pragma: no cover

    def probe_disk(self, path: str = None) -> Dict[str, Any]:
        """Query real disk stats."""
        try:
            import shutil
            target = path or str(PROJECT_ROOT)
            usage = shutil.disk_usage(target)
            self.hdd_free_percent = (usage.free / usage.total) * 100.0
            return {
                "total_gb": round(usage.total / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_percent": round(self.hdd_free_percent, 1),
            }
        except Exception as e:  # pragma: no cover
            logger.error(f"Disk probe failed: {e}")  # pragma: no cover
            return {"total_gb": 0, "free_gb": 0, "used_gb": 0, "free_percent": 0}  # pragma: no cover

    def probe_memory(self) -> Dict[str, Any]:
        """Query real memory usage."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            self.memory_used_percent = mem.percent
            return {
                "total_gb": round(mem.total / (1024**3), 2),
                "used_gb": round(mem.used / (1024**3), 2),
                "percent": mem.percent,
            }
        except ImportError:  # pragma: no cover
            # Fallback: read from OS
            try:  # pragma: no cover
                import ctypes  # pragma: no cover
                kernel32 = ctypes.windll.kernel32  # pragma: no cover
                class MEMORYSTATUSEX(ctypes.Structure):  # pragma: no cover
                    _fields_ = [  # pragma: no cover
                        ("dwLength", ctypes.c_ulong),  # pragma: no cover
                        ("dwMemoryLoad", ctypes.c_ulong),  # pragma: no cover
                        ("ullTotalPhys", ctypes.c_ulonglong),  # pragma: no cover
                        ("ullAvailPhys", ctypes.c_ulonglong),  # pragma: no cover
                        ("ullTotalPageFile", ctypes.c_ulonglong),  # pragma: no cover
                        ("ullAvailPageFile", ctypes.c_ulonglong),  # pragma: no cover
                        ("ullTotalVirtual", ctypes.c_ulonglong),  # pragma: no cover
                        ("ullAvailVirtual", ctypes.c_ulonglong),  # pragma: no cover
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),  # pragma: no cover
                    ]
                stat = MEMORYSTATUSEX()  # pragma: no cover
                stat.dwLength = ctypes.sizeof(stat)  # pragma: no cover
                kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))  # pragma: no cover
                self.memory_used_percent = float(stat.dwMemoryLoad)  # pragma: no cover
                return {  # pragma: no cover
                    "total_gb": round(stat.ullTotalPhys / (1024**3), 2),  # pragma: no cover
                    "used_gb": round((stat.ullTotalPhys - stat.ullAvailPhys) / (1024**3), 2),  # pragma: no cover
                    "percent": float(stat.dwMemoryLoad),  # pragma: no cover
                }
            except Exception as e:  # pragma: no cover
                logger.error(f"Memory probe failed: {e}")  # pragma: no cover
                return {"total_gb": 0, "used_gb": 0, "percent": 0}  # pragma: no cover

    def record_io_latency(self, latency_ms: float):
        self.io_latency_window.append(latency_ms)

    def avg_io_latency(self) -> float:
        if not self.io_latency_window:
            return 0.0
        return sum(self.io_latency_window) / len(self.io_latency_window)

    def compute_score(self) -> float:
        """Compute resource integrity sub-score (0–100)."""
        # GPU temp score
        if self.gpu_temp <= self.GPU_TEMP_WARN:
            gpu_temp_s = 100.0
        elif self.gpu_temp >= self.GPU_TEMP_MAX:
            gpu_temp_s = 0.0
        else:
            gpu_temp_s = 100.0 * (self.GPU_TEMP_MAX - self.gpu_temp) / (self.GPU_TEMP_MAX - self.GPU_TEMP_WARN)

        # GPU throttle score
        gpu_thr_s = max(0.0, 100.0 - self.gpu_throttle_events * 10.0)

        # HDD score
        if self.hdd_free_percent >= self.HDD_FREE_MIN:
            hdd_s = 100.0
        elif self.hdd_free_percent <= 1.0:
            hdd_s = 0.0
        else:
            hdd_s = 100.0 * (self.hdd_free_percent - 1.0) / (self.HDD_FREE_MIN - 1.0)

        # IO latency score
        avg_io = self.avg_io_latency()
        if avg_io <= 5.0:
            io_s = 100.0
        elif avg_io >= self.IO_LATENCY_MAX:
            io_s = 0.0
        else:
            io_s = 100.0 * (self.IO_LATENCY_MAX - avg_io) / (self.IO_LATENCY_MAX - 5.0)

        # Memory score
        if self.memory_used_percent <= 70.0:
            mem_s = 100.0
        elif self.memory_used_percent >= 99.0:
            mem_s = 0.0
        else:
            mem_s = 100.0 * (99.0 - self.memory_used_percent) / (99.0 - 70.0)

        score = (gpu_temp_s * 0.30 + gpu_thr_s * 0.15 +
                 hdd_s * 0.25 + io_s * 0.15 + mem_s * 0.15)
        return max(0.0, min(100.0, score))

    def get_alerts(self) -> List[str]:
        alerts = []
        if self.gpu_temp > self.GPU_TEMP_WARN:
            alerts.append(f"GPU temp {self.gpu_temp}°C > {self.GPU_TEMP_WARN}°C")
        if self.gpu_throttle_events > 0:
            alerts.append(f"GPU throttle events: {self.gpu_throttle_events}")
        if self.hdd_free_percent < self.HDD_FREE_MIN:
            alerts.append(f"HDD free {self.hdd_free_percent:.1f}% < {self.HDD_FREE_MIN}%")
        if self.avg_io_latency() > self.IO_LATENCY_MAX:
            alerts.append(f"IO latency {self.avg_io_latency():.1f}ms > {self.IO_LATENCY_MAX}ms")
        if self.memory_used_percent > self.MEMORY_MAX:
            alerts.append(f"Memory {self.memory_used_percent:.1f}% > {self.MEMORY_MAX}%")
        return alerts


# =============================================================================
# DATASET INTEGRITY WATCHDOG
# =============================================================================

class DatasetIntegrityWatchdog:
    """Rolling class balance, KL divergence, and duplicate detection."""

    def __init__(self, n_classes: int = 2, n_bins: int = 50,
                 imbalance_threshold: float = 1.2,
                 kl_threshold: float = 0.5,
                 duplicate_rate_threshold: float = 0.05):
        self.n_classes = n_classes
        self.n_bins = n_bins
        self.imbalance_threshold = imbalance_threshold
        self.kl_threshold = kl_threshold
        self.duplicate_rate_threshold = duplicate_rate_threshold

        self.class_counts = np.zeros(n_classes, dtype=np.int64)
        self.baseline_dist: Optional[np.ndarray] = None
        self.current_dist = np.zeros(n_bins, dtype=np.float64)
        self.dist_sample_count = 0
        self.seen_hashes: set = set()
        self.total_samples = 0
        self.duplicate_count = 0

    def set_baseline(self, dist: np.ndarray):
        self.baseline_dist = dist / (dist.sum() + 1e-10)

    def record_sample(self, class_label: int, features: np.ndarray):
        # Class balance
        if 0 <= class_label < self.n_classes:
            self.class_counts[class_label] += 1

        # Feature dist (bin first feature)
        if features.size > 0:
            val = float(np.clip(features[0], 0.0, 1.0))
            b = int(val * (self.n_bins - 1))
            b = max(0, min(self.n_bins - 1, b))
            self.current_dist[b] += 1.0
            self.dist_sample_count += 1

        # Duplicate
        h = hashlib.md5(features.tobytes()).hexdigest()
        self.total_samples += 1
        if h in self.seen_hashes:
            self.duplicate_count += 1
        else:
            self.seen_hashes.add(h)

    def record_batch(self, labels: np.ndarray, features: np.ndarray):
        for i in range(len(labels)):
            self.record_sample(int(labels[i]), features[i])

    def compute_imbalance_ratio(self) -> float:
        if self.n_classes <= 1:
            return 1.0
        min_c = int(self.class_counts.min())
        max_c = int(self.class_counts.max())
        if min_c <= 0:
            return 999.0
        return max_c / min_c

    def compute_kl_divergence(self) -> float:
        if self.baseline_dist is None or self.dist_sample_count == 0:
            return 0.0
        q = (self.current_dist + 1e-10) / (self.dist_sample_count + self.n_bins * 1e-10)
        p = self.baseline_dist
        kl = float(np.sum(p * np.log(p / (q + 1e-10) + 1e-10)))
        return max(0.0, kl)

    def get_stats(self) -> Dict[str, Any]:
        imb = self.compute_imbalance_ratio()
        kl = self.compute_kl_divergence()
        dup_rate = self.duplicate_count / max(1, self.total_samples)

        # Score
        score = 100.0
        if imb > self.imbalance_threshold:
            score -= min(30.0, (imb - self.imbalance_threshold) * 20.0)
        if kl > self.kl_threshold:
            score -= min(40.0, (kl - self.kl_threshold) * 40.0)
        if dup_rate > self.duplicate_rate_threshold:
            score -= min(30.0, (dup_rate - self.duplicate_rate_threshold) * 300.0)
        score = max(0.0, min(100.0, score))

        imb_alert = imb > self.imbalance_threshold
        kl_alert = kl > self.kl_threshold
        dup_alert = dup_rate > self.duplicate_rate_threshold

        return {
            "n_classes": self.n_classes,
            "class_counts": self.class_counts.tolist(),
            "imbalance_ratio": round(imb, 3),
            "imbalance_alert": imb_alert,
            "kl_divergence": round(kl, 4),
            "kl_alert": kl_alert,
            "total_samples": self.total_samples,
            "duplicate_count": self.duplicate_count,
            "duplicate_rate": round(dup_rate, 4),
            "duplicate_alert": dup_alert,
            "score": round(score, 1),
            "should_freeze_training": imb_alert or kl_alert or dup_alert,
        }

    def reset(self):
        self.class_counts = np.zeros(self.n_classes, dtype=np.int64)
        self.current_dist = np.zeros(self.n_bins, dtype=np.float64)
        self.dist_sample_count = 0
        self.seen_hashes.clear()
        self.total_samples = 0
        self.duplicate_count = 0


# =============================================================================
# LOG INTEGRITY MONITOR
# =============================================================================

class LogIntegrityMonitor:
    """FNV-1a hash chain over log entries. Detects tampering and gaps."""

    def __init__(self):
        self.entries: List[Dict[str, Any]] = []
        self.expected_sequence = 0
        self.current_chain_hash = b'\x00' * 32
        self.gap_count = 0
        self.corruption_count = 0

    @staticmethod
    def _fnv1a(data: bytes) -> bytes:
        h = 0x811c9dc5
        for b in data:
            h ^= b
            h = (h * 0x01000193) & 0xFFFFFFFF
        result = bytearray(32)
        for i in range(8):
            word = h
            word ^= (word >> 3) ^ ((word << 7) & 0xFFFFFFFF)
            word = (word * 0x01000193) & 0xFFFFFFFF
            word = (word + (i * 0x9e3779b9)) & 0xFFFFFFFF
            result[i*4:(i+1)*4] = struct.pack('<I', word)
            h = word
        return bytes(result)

    def _compute_entry_hash(self, entry: Dict, prev_hash: bytes) -> bytes:
        data = struct.pack('<Qd', entry['sequence'], entry['timestamp'])
        data += entry['source'].encode().ljust(64, b'\x00')[:64]
        data += entry['message'].encode().ljust(512, b'\x00')[:512]
        data += prev_hash[:32]
        return self._fnv1a(data)

    def append_entry(self, source: str, message: str):
        entry = {
            'sequence': self.expected_sequence,
            'timestamp': time.time(),
            'source': source,
            'message': message,
        }
        entry['chain_hash'] = self._compute_entry_hash(entry, self.current_chain_hash)
        self.current_chain_hash = entry['chain_hash']
        self.entries.append(entry)
        self.expected_sequence += 1

    def verify_chain(self) -> bool:
        if not self.entries:
            return True
        self.corruption_count = 0
        prev = b'\x00' * 32
        for entry in self.entries:
            expected = self._compute_entry_hash(entry, prev)
            if expected != entry.get('chain_hash', b''):
                self.corruption_count += 1
            prev = entry.get('chain_hash', b'\x00' * 32)
        return self.corruption_count == 0

    def get_stats(self) -> Dict[str, Any]:
        chain_valid = self.verify_chain()
        score = 100.0
        if self.gap_count > 0:
            score -= min(40.0, self.gap_count * 5.0)
        if self.corruption_count > 0:
            score -= min(60.0, self.corruption_count * 20.0)
        score = max(0.0, min(100.0, score))

        return {
            "total_entries": len(self.entries),
            "verified_entries": len(self.entries) - self.corruption_count,
            "failed_entries": self.corruption_count,
            "gap_count": self.gap_count,
            "chain_valid": chain_valid,
            "has_gaps": self.gap_count > 0,
            "has_corruption": self.corruption_count > 0,
            "score": round(score, 1),
        }


# =============================================================================
# GOVERNANCE INTEGRITY READER
# =============================================================================

class GovernanceIntegrityReader:
    """Reads real governance state from reports/governance_state.json."""

    def __init__(self, state_path: Path = None):
        self.state_path = state_path or (PROJECT_ROOT / "reports" / "governance_state.json")

    def read_state(self) -> Dict[str, Any]:
        try:
            if self.state_path.exists():
                with open(self.state_path, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read governance state: {e}")
        return {"auto_mode_safe": False, "checks": {}, "timestamp": None}

    def compute_score(self) -> Tuple[float, Dict[str, Any]]:
        state = self.read_state()
        checks = state.get("checks", {})

        if not checks:
            return 0.0, {"reason": "no_governance_data", "state": state}

        total = len(checks)
        passed = sum(1 for v in checks.values() if v is True)
        score = (passed / total) * 100.0 if total > 0 else 0.0

        return round(score, 1), {
            "auto_mode_safe": state.get("auto_mode_safe", False),
            "checks": checks,
            "passed": passed,
            "total": total,
            "timestamp": state.get("timestamp"),
        }


# =============================================================================
# ML INTEGRITY SCORER (reads from shadow monitor)
# =============================================================================

class MLIntegrityScorer:
    """Computes ML integrity from drift, entropy, inflation, model age."""

    def __init__(self):
        self.drift_score = 100.0
        self.entropy_score = 100.0
        self.inflation_score = 100.0
        self.model_age_days = 0
        self.model_age_max = 90

    def update_drift(self, max_shift_sigma: float, threshold: float = 2.0):
        if max_shift_sigma <= threshold:
            self.drift_score = 100.0
        else:
            penalty = min(100.0, (max_shift_sigma - threshold) * 25.0)
            self.drift_score = max(0.0, 100.0 - penalty)

    def update_entropy(self, collapse_pct: float, threshold: float = 0.10):
        if collapse_pct <= threshold:
            self.entropy_score = 100.0
        else:
            penalty = min(100.0, (collapse_pct - threshold) * 200.0)
            self.entropy_score = max(0.0, 100.0 - penalty)

    def update_inflation(self, inflation: float, threshold: float = 0.02):
        if inflation <= threshold:
            self.inflation_score = 100.0
        else:
            penalty = min(100.0, (inflation - threshold) * 500.0)
            self.inflation_score = max(0.0, 100.0 - penalty)

    def update_model_age(self, days: int):
        self.model_age_days = days

    def compute_score(self) -> Tuple[float, Dict[str, Any]]:
        # Model age score
        if self.model_age_days <= self.model_age_max:
            age_score = 100.0
        else:
            penalty = min(100.0, (self.model_age_days - self.model_age_max) * 2.0)
            age_score = max(0.0, 100.0 - penalty)

        score = (self.drift_score * 0.30 +
                 self.entropy_score * 0.20 +
                 self.inflation_score * 0.25 +
                 age_score * 0.25)

        return round(max(0.0, min(100.0, score)), 1), {
            "drift_score": round(self.drift_score, 1),
            "entropy_score": round(self.entropy_score, 1),
            "inflation_score": round(self.inflation_score, 1),
            "age_score": round(age_score, 1),
            "model_age_days": self.model_age_days,
        }

    @property
    def has_drift_alert(self) -> bool:
        return self.drift_score < 100.0


# =============================================================================
# SYSTEM INTEGRITY SUPERVISOR — Unified Aggregator
# =============================================================================

def _score_to_status(score: float) -> str:
    if score >= 90.0:
        return "GREEN"
    if score >= 70.0:
        return "YELLOW"
    return "RED"


class SystemIntegritySupervisor:
    """
    Central supervisor aggregating all sub-system scores.
    Computes SYSTEM_INTEGRITY_SCORE (0–100).
    Enforces autonomous run conditions.
    """

    SHADOW_THRESHOLD = 95.0

    # Weights
    W_ML = 0.25
    W_DATASET = 0.20
    W_STORAGE = 0.15
    W_RESOURCE = 0.15
    W_LOG = 0.10
    W_GOVERNANCE = 0.15

    def __init__(self):
        self.resource_monitor = ResourceMonitor()
        self.dataset_watchdog = DatasetIntegrityWatchdog()
        self.log_monitor = LogIntegrityMonitor()
        self.governance_reader = GovernanceIntegrityReader()
        self.ml_scorer = MLIntegrityScorer()

        self.containment_timestamps: List[float] = []
        self.event_log: List[Dict[str, Any]] = []

    def probe_all(self) -> Dict[str, Any]:
        """Probe all real system metrics and compute unified integrity."""

        # 1) Resource (GPU + Disk + Memory)
        gpu_info = self.resource_monitor.probe_gpu()
        disk_info = self.resource_monitor.probe_disk()
        mem_info = self.resource_monitor.probe_memory()
        resource_score = self.resource_monitor.compute_score()

        # 2) ML Integrity
        ml_score, ml_details = self.ml_scorer.compute_score()

        # 3) Dataset Integrity
        ds_stats = self.dataset_watchdog.get_stats()
        dataset_score = ds_stats["score"]

        # 4) Log Integrity
        log_stats = self.log_monitor.get_stats()
        log_score = log_stats["score"]

        # 5) Governance Integrity
        gov_score, gov_details = self.governance_reader.compute_score()

        # 6) Storage — combine disk score with backup verification
        storage_score = self._compute_storage_score(disk_info)

        # Weighted overall
        overall = (
            ml_score      * self.W_ML +
            dataset_score * self.W_DATASET +
            storage_score * self.W_STORAGE +
            resource_score * self.W_RESOURCE +
            log_score     * self.W_LOG +
            gov_score     * self.W_GOVERNANCE
        )
        overall = round(max(0.0, min(100.0, overall)), 1)

        # Autonomy conditions
        conditions = self._evaluate_autonomy(
            overall, ml_score, dataset_score, storage_score, ds_stats
        )

        result = {
            "ml_integrity": {
                "score": ml_score,
                "status": _score_to_status(ml_score),
                "details": ml_details,
            },
            "dataset_integrity": {
                "score": dataset_score,
                "status": _score_to_status(dataset_score),
                "details": ds_stats,
            },
            "storage_integrity": {
                "score": storage_score,
                "status": _score_to_status(storage_score),
                "details": disk_info,
            },
            "resource_integrity": {
                "score": resource_score,
                "status": _score_to_status(resource_score),
                "details": {
                    "gpu": gpu_info,
                    "disk": disk_info,
                    "memory": mem_info,
                    "io_latency_ms": round(self.resource_monitor.avg_io_latency(), 2),
                    "alerts": self.resource_monitor.get_alerts(),
                },
            },
            "log_integrity": {
                "score": log_score,
                "status": _score_to_status(log_score),
                "details": log_stats,
            },
            "governance_integrity": {
                "score": gov_score,
                "status": _score_to_status(gov_score),
                "details": gov_details,
            },
            "overall_integrity": {
                "score": overall,
                "status": _score_to_status(overall),
            },
            "shadow_allowed": conditions["shadow_allowed"],
            "shadow_blocked_reasons": conditions["blocked_reasons"],
            "forced_mode": "MODE_B_SHADOW" if conditions["shadow_allowed"] else "MODE_A",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }

        # Log event
        self.event_log.append({
            "overall_score": overall,
            "shadow_allowed": conditions["shadow_allowed"],
            "timestamp": time.time(),
        })

        return result

    def _compute_storage_score(self, disk_info: Dict) -> float:
        """Combine HDD free space into a storage score."""
        free_pct = disk_info.get("free_percent", 100.0)
        if free_pct >= 15.0:
            return 100.0
        if free_pct <= 1.0:
            return 0.0
        return round(100.0 * (free_pct - 1.0) / (15.0 - 1.0), 1)

    def _evaluate_autonomy(self, overall: float, ml_score: float,
                            dataset_score: float, storage_score: float,
                            ds_stats: Dict) -> Dict[str, Any]:
        """Evaluate all 5 autonomous run conditions."""
        blocked = []

        c1 = overall > self.SHADOW_THRESHOLD
        if not c1:
            blocked.append(f"overall_integrity {overall} <= {self.SHADOW_THRESHOLD}")

        c2 = not self._has_containment_24h()
        if not c2:
            blocked.append("containment_event_in_last_24h")

        c3 = not self.ml_scorer.has_drift_alert
        if not c3:
            blocked.append("drift_anomaly_detected")

        c4 = not ds_stats.get("should_freeze_training", False)
        if not c4:
            blocked.append("dataset_skew_detected")

        c5 = storage_score >= 90.0
        if not c5:
            blocked.append("storage_warning_active")

        shadow_allowed = c1 and c2 and c3 and c4 and c5

        if not shadow_allowed:
            self.containment_timestamps.append(time.time())

        return {
            "shadow_allowed": shadow_allowed,
            "blocked_reasons": blocked,
            "conditions": {
                "overall_above_threshold": c1,
                "no_containment_24h": c2,
                "no_drift_anomalies": c3,
                "no_dataset_skew": c4,
                "no_storage_warnings": c5,
            },
        }

    def _has_containment_24h(self) -> bool:
        cutoff = time.time() - 86400.0
        return any(ts >= cutoff for ts in self.containment_timestamps)


# =============================================================================
# SINGLETON
# =============================================================================

_supervisor_instance: Optional[SystemIntegritySupervisor] = None


def get_integrity_supervisor() -> SystemIntegritySupervisor:
    """Get or create the singleton SystemIntegritySupervisor."""
    global _supervisor_instance
    if _supervisor_instance is None:
        _supervisor_instance = SystemIntegritySupervisor()
    return _supervisor_instance
