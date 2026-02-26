"""
Dedup + Drift Controls — Duplicate Suppression and Drift Governance

- Exact dedup: CVE ID + content_hash
- Near-dup: simhash with configurable Hamming distance threshold (≤3)
- Schema drift detection per source (field presence/type tracking)
- Distribution drift: KL divergence and PSI for severity distributions
- Label drift: promotion vs quarantine ratio over time
- Weak-source ratio: alert when >20% from low-confidence sources
- Auto-freeze on breach with explicit block reason
"""

import hashlib
import logging
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any

logger = logging.getLogger("ygb.dedup_drift")

SIMHASH_THRESHOLD = 3       # Max Hamming distance for near-dup
WEAK_SOURCE_THRESHOLD = 0.20  # Max fraction from low-confidence sources
LOW_CONFIDENCE_CUTOFF = 0.7   # Below this = weak source
KL_ALERT_THRESHOLD = 0.5     # KL divergence alert threshold
PSI_ALERT_THRESHOLD = 0.25   # PSI alert threshold


# =============================================================================
# SIMHASH
# =============================================================================

def _simhash(text: str, hashbits: int = 64) -> int:
    """Compute simhash of text for near-duplicate detection."""
    v = [0] * hashbits
    tokens = text.lower().split()
    for token in tokens:
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        for i in range(hashbits):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1
    fingerprint = 0
    for i in range(hashbits):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """Hamming distance between two simhash values."""
    return bin(a ^ b).count("1")


# =============================================================================
# KL DIVERGENCE + PSI
# =============================================================================

def kl_divergence(p: Dict[str, float], q: Dict[str, float]) -> float:
    """KL(P || Q) with Laplace smoothing."""
    keys = set(list(p.keys()) + list(q.keys()))
    eps = 1e-10
    total = 0.0
    for k in keys:
        pk = p.get(k, eps)
        qk = q.get(k, eps)
        if pk > 0:
            total += pk * math.log(pk / qk)
    return total


def psi(expected: Dict[str, float],
        actual: Dict[str, float]) -> float:
    """Population Stability Index."""
    keys = set(list(expected.keys()) + list(actual.keys()))
    eps = 1e-10
    total = 0.0
    for k in keys:
        e = expected.get(k, eps)
        a = actual.get(k, eps)
        total += (a - e) * math.log(a / e)
    return total


# =============================================================================
# SCHEMA DRIFT
# =============================================================================

@dataclass
class SchemaProfile:
    """Expected schema profile for a source."""
    source_id: str
    expected_fields: Set[str]
    observed_fields: Set[str] = field(default_factory=set)
    drift_alerts: List[str] = field(default_factory=list)

    def check(self, record_fields: Set[str]) -> List[str]:
        """Check a record against expected schema. Returns alerts."""
        self.observed_fields.update(record_fields)
        alerts = []
        missing = self.expected_fields - record_fields
        extra = record_fields - self.expected_fields
        if missing:
            alert = (
                f"Schema drift: missing fields {missing} "
                f"from source {self.source_id}"
            )
            alerts.append(alert)
            self.drift_alerts.append(alert)
        if extra:
            alert = (
                f"Schema drift: unexpected fields {extra} "
                f"from source {self.source_id}"
            )
            alerts.append(alert)
            self.drift_alerts.append(alert)
        return alerts


# =============================================================================
# DEDUP + DRIFT ENGINE
# =============================================================================

@dataclass
class DriftAlert:
    """A drift or dedup alert."""
    alert_type: str       # NEAR_DUP, SCHEMA_DRIFT, DISTRIBUTION_DRIFT, etc.
    message: str
    severity: str         # INFO, WARNING, CRITICAL
    timestamp: str
    details: Dict[str, Any] = field(default_factory=dict)


class DedupDriftEngine:
    """Duplicate suppression and drift governance engine."""

    def __init__(self):
        self._exact_hashes: Dict[str, str] = {}    # content_hash -> cve_id
        self._simhashes: Dict[str, int] = {}        # cve_id -> simhash
        self._schema_profiles: Dict[str, SchemaProfile] = {}
        self._severity_baseline: Optional[Dict[str, float]] = None
        self._severity_current: Counter = Counter()
        self._source_confidence: Dict[str, List[float]] = defaultdict(list)
        self._promotion_history: List[bool] = []  # True=promoted, False=quarantined
        self._alerts: List[DriftAlert] = []
        self._freeze_reasons: Dict[str, str] = {}

    # ─── Exact Dedup ─────────────────────────────────────────────────

    def is_exact_duplicate(self, content_hash: str, cve_id: str) -> bool:
        """Check if content hash already exists."""
        if content_hash in self._exact_hashes:
            existing_cve = self._exact_hashes[content_hash]
            return existing_cve != cve_id  # Same CVE update is OK
        self._exact_hashes[content_hash] = cve_id
        return False

    # ─── Near-Dup ────────────────────────────────────────────────────

    def check_near_duplicate(self, cve_id: str, text: str) -> Optional[str]:
        """Check for near-duplicates via simhash.

        Returns the CVE ID of the near-dup match, or None.
        """
        sh = _simhash(text)
        for existing_id, existing_sh in self._simhashes.items():
            if existing_id == cve_id:
                continue
            dist = hamming_distance(sh, existing_sh)
            if dist <= SIMHASH_THRESHOLD:
                self._alerts.append(DriftAlert(
                    alert_type="NEAR_DUP",
                    message=(
                        f"Near-duplicate detected: {cve_id} ≈ {existing_id} "
                        f"(hamming={dist})"
                    ),
                    severity="WARNING",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    details={
                        "cve_id": cve_id,
                        "near_dup_of": existing_id,
                        "hamming_distance": dist,
                    },
                ))
                return existing_id
        self._simhashes[cve_id] = sh
        return None

    # ─── Schema Drift ────────────────────────────────────────────────

    def register_schema(self, source_id: str,
                        expected_fields: Set[str]):
        """Register expected schema for a source."""
        self._schema_profiles[source_id] = SchemaProfile(
            source_id=source_id,
            expected_fields=expected_fields,
        )

    def check_schema_drift(self, source_id: str,
                           record_fields: Set[str]) -> List[str]:
        """Check record fields against source schema."""
        profile = self._schema_profiles.get(source_id)
        if not profile:
            return []
        alerts = profile.check(record_fields)
        for alert_msg in alerts:
            self._alerts.append(DriftAlert(
                alert_type="SCHEMA_DRIFT",
                message=alert_msg,
                severity="WARNING",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))
        return alerts

    # ─── Distribution Drift ──────────────────────────────────────────

    def set_severity_baseline(self, distribution: Dict[str, float]):
        """Set severity distribution baseline."""
        self._severity_baseline = distribution

    def record_severity(self, severity: str):
        """Record a severity observation."""
        self._severity_current[severity] += 1

    def check_distribution_drift(self) -> Optional[DriftAlert]:
        """Check severity distribution drift via KL divergence + PSI."""
        if not self._severity_baseline:
            return None
        total = sum(self._severity_current.values())
        if total < 10:
            return None

        current_dist = {
            k: v / total for k, v in self._severity_current.items()
        }
        kl = kl_divergence(self._severity_baseline, current_dist)
        psi_val = psi(self._severity_baseline, current_dist)

        if kl > KL_ALERT_THRESHOLD or psi_val > PSI_ALERT_THRESHOLD:
            alert = DriftAlert(
                alert_type="DISTRIBUTION_DRIFT",
                message=(
                    f"Severity distribution drift: "
                    f"KL={kl:.4f}, PSI={psi_val:.4f}"
                ),
                severity="CRITICAL" if kl > 1.0 else "WARNING",
                timestamp=datetime.now(timezone.utc).isoformat(),
                details={
                    "kl_divergence": round(kl, 4),
                    "psi": round(psi_val, 4),
                    "baseline": self._severity_baseline,
                    "current": current_dist,
                },
            )
            self._alerts.append(alert)
            return alert
        return None

    # ─── Weak Source Ratio ───────────────────────────────────────────

    def record_source_confidence(self, source_name: str,
                                 confidence: float):
        """Record a source confidence observation."""
        self._source_confidence[source_name].append(confidence)

    def check_weak_source_ratio(self) -> Optional[DriftAlert]:
        """Check if too many records come from low-confidence sources."""
        total = 0
        weak = 0
        for source, confs in self._source_confidence.items():
            for c in confs:
                total += 1
                if c < LOW_CONFIDENCE_CUTOFF:
                    weak += 1

        if total == 0:
            return None
        ratio = weak / total
        if ratio > WEAK_SOURCE_THRESHOLD:
            alert = DriftAlert(
                alert_type="WEAK_SOURCE_RATIO",
                message=(
                    f"Weak source ratio {ratio:.2%} exceeds threshold "
                    f"{WEAK_SOURCE_THRESHOLD:.0%}"
                ),
                severity="CRITICAL",
                timestamp=datetime.now(timezone.utc).isoformat(),
                details={
                    "weak_count": weak,
                    "total_count": total,
                    "ratio": round(ratio, 4),
                    "threshold": WEAK_SOURCE_THRESHOLD,
                },
            )
            self._alerts.append(alert)
            return alert
        return None

    # ─── Label Drift ─────────────────────────────────────────────────

    def record_promotion_decision(self, promoted: bool):
        """Record a promotion/quarantine decision for label drift."""
        self._promotion_history.append(promoted)

    def check_label_drift(self, window: int = 100) -> Optional[DriftAlert]:
        """Check promotion ratio drift over recent window."""
        if len(self._promotion_history) < window:
            return None
        recent = self._promotion_history[-window:]
        ratio = sum(1 for p in recent if p) / len(recent)
        # Alert if promotion rate drops below 30% or exceeds 95%
        if ratio < 0.30:
            alert = DriftAlert(
                alert_type="LABEL_DRIFT",
                message=(
                    f"Low promotion rate: {ratio:.2%} over last "
                    f"{window} decisions"
                ),
                severity="WARNING",
                timestamp=datetime.now(timezone.utc).isoformat(),
                details={"promotion_rate": round(ratio, 4), "window": window},
            )
            self._alerts.append(alert)
            return alert
        if ratio > 0.95:
            alert = DriftAlert(
                alert_type="LABEL_DRIFT",
                message=(
                    f"Unusually high promotion rate: {ratio:.2%} over last "
                    f"{window} decisions"
                ),
                severity="WARNING",
                timestamp=datetime.now(timezone.utc).isoformat(),
                details={"promotion_rate": round(ratio, 4), "window": window},
            )
            self._alerts.append(alert)
            return alert
        return None

    # ─── Freeze on Breach ────────────────────────────────────────────

    def should_freeze_promotion(self) -> Tuple[bool, str]:
        """Check if promotion should be auto-frozen due to governance breaches."""
        critical_alerts = [
            a for a in self._alerts if a.severity == "CRITICAL"
        ]
        if critical_alerts:
            latest = critical_alerts[-1]
            reason = (
                f"Auto-freeze: {latest.alert_type} — {latest.message}"
            )
            return True, reason
        return False, ""

    # ─── Status ──────────────────────────────────────────────────────

    def get_alerts(self, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        alerts = self._alerts
        if severity:
            alerts = [a for a in alerts if a.severity == severity.upper()]
        return [
            {
                "alert_type": a.alert_type,
                "message": a.message,
                "severity": a.severity,
                "timestamp": a.timestamp,
                "details": a.details,
            }
            for a in alerts
        ]

    def get_status(self) -> Dict[str, Any]:
        total_alerts = len(self._alerts)
        critical = sum(1 for a in self._alerts if a.severity == "CRITICAL")
        return {
            "total_alerts": total_alerts,
            "critical_alerts": critical,
            "exact_hashes_tracked": len(self._exact_hashes),
            "simhashes_tracked": len(self._simhashes),
            "schema_profiles": len(self._schema_profiles),
            "promotion_decisions": len(self._promotion_history),
        }


# =============================================================================
# SINGLETON
# =============================================================================

_engine: Optional[DedupDriftEngine] = None


def get_dedup_drift_engine() -> DedupDriftEngine:
    global _engine
    if _engine is None:
        _engine = DedupDriftEngine()
    return _engine
