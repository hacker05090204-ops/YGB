"""
Production Readiness Report — Machine-readable rollout/quality report.

Generates a comprehensive report including:
  - Per-field LAB/REAL sample counts
  - Quality metrics (entropy, balance, trust)
  - Sync/recovery status
  - Voice command execution audit
  - SMTP notification status
  - Training mode and strict-real gate status
"""

import json
import os
import logging
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, UTC
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FieldSampleReport:
    """Sample count report for a single field."""
    field_name: str
    lab_count: int
    real_count: int
    lab_meets_min: bool
    real_meets_min: bool
    min_required: int = 125_000


@dataclass
class QualityMetrics:
    """Quality metrics for training data."""
    class_balance_ratio: float
    entropy_bits: float
    duplicate_ratio: float
    source_trust_avg: float
    forbidden_fields_found: bool


@dataclass
class SyncRecoveryStatus:
    """Sync and recovery status for the cluster."""
    cluster_size: int
    all_nodes_alive: bool
    shards_redundant: bool
    last_recovery_event: Optional[str]
    recovery_success: Optional[bool]


@dataclass
class VoiceAuditSummary:
    """Audit summary for voice command execution."""
    total_commands: int
    completed: int
    failed: int
    rejected: int
    awaiting_confirmation: int


@dataclass
class SmtpStatus:
    """SMTP notification status."""
    configured: bool
    last_send_status: Optional[str]
    total_sent: int
    total_failed: int


@dataclass
class ProductionReadinessReport:
    """Complete production readiness report."""
    report_id: str
    generated_at: str
    training_mode: str  # "REAL" or "LAB"
    strict_real_gate_active: bool
    field_samples: List[FieldSampleReport]
    quality_metrics: QualityMetrics
    sync_recovery: SyncRecoveryStatus
    voice_audit: VoiceAuditSummary
    smtp_status: SmtpStatus
    overall_ready: bool
    blocking_reasons: List[str]


def generate_report(
    field_lab_counts: Dict[str, int] = None,
    field_real_counts: Dict[str, int] = None,
    quality: Optional[QualityMetrics] = None,
    sync: Optional[SyncRecoveryStatus] = None,
    voice: Optional[VoiceAuditSummary] = None,
    smtp: Optional[SmtpStatus] = None,
    min_per_field: int = 125_000,
) -> ProductionReadinessReport:
    """
    Generate a comprehensive production readiness report.

    All parameters are optional — report will flag missing data.
    """
    import uuid
    now = datetime.now(UTC).isoformat()
    report_id = f"RPT-{uuid.uuid4().hex[:12].upper()}"
    blocking: List[str] = []

    # Determine training mode
    strict_real = os.environ.get("YGB_STRICT_REAL_MODE", "true").lower() != "false"
    training_mode = "REAL" if strict_real else "LAB"

    # Field sample counts
    field_lab_counts = field_lab_counts or {}
    field_real_counts = field_real_counts or {}
    all_fields = set(list(field_lab_counts.keys()) + list(field_real_counts.keys()))

    field_samples: List[FieldSampleReport] = []
    for fname in sorted(all_fields):
        lab = field_lab_counts.get(fname, 0)
        real = field_real_counts.get(fname, 0)
        lab_ok = lab >= min_per_field
        real_ok = real >= min_per_field

        if not lab_ok:
            blocking.append(f"LAB/{fname}: {lab} < {min_per_field}")
        if not real_ok:
            blocking.append(f"REAL/{fname}: {real} < {min_per_field}")

        field_samples.append(FieldSampleReport(
            field_name=fname,
            lab_count=lab,
            real_count=real,
            lab_meets_min=lab_ok,
            real_meets_min=real_ok,
            min_required=min_per_field,
        ))

    # Quality metrics
    if quality is None:
        quality = QualityMetrics(
            class_balance_ratio=0.0,
            entropy_bits=0.0,
            duplicate_ratio=0.0,
            source_trust_avg=0.0,
            forbidden_fields_found=False,
        )
        blocking.append("Quality metrics not available")

    if quality.forbidden_fields_found:
        blocking.append("Forbidden fields detected in training data")

    # Sync/Recovery
    if sync is None:
        sync = SyncRecoveryStatus(
            cluster_size=0,
            all_nodes_alive=False,
            shards_redundant=False,
            last_recovery_event=None,
            recovery_success=None,
        )
        blocking.append("Sync/recovery status not available")

    if not sync.all_nodes_alive:
        blocking.append("Not all cluster nodes are alive")

    # Voice audit
    if voice is None:
        voice = VoiceAuditSummary(
            total_commands=0,
            completed=0,
            failed=0,
            rejected=0,
            awaiting_confirmation=0,
        )

    # SMTP status
    if smtp is None:
        smtp_configured = bool(os.environ.get("SMTP_PASS") or os.environ.get("SMTP_PASSWORD"))
        smtp = SmtpStatus(
            configured=smtp_configured,
            last_send_status=None,
            total_sent=0,
            total_failed=0,
        )

    overall_ready = len(blocking) == 0

    return ProductionReadinessReport(
        report_id=report_id,
        generated_at=now,
        training_mode=training_mode,
        strict_real_gate_active=strict_real,
        field_samples=field_samples,
        quality_metrics=quality,
        sync_recovery=sync,
        voice_audit=voice,
        smtp_status=smtp,
        overall_ready=overall_ready,
        blocking_reasons=blocking,
    )


def report_to_json(report: ProductionReadinessReport) -> str:
    """Convert report to JSON string."""
    return json.dumps(asdict(report), indent=2, default=str)


def report_to_summary(report: ProductionReadinessReport) -> str:
    """Generate human-readable summary from report."""
    lines = [
        f"═══ Production Readiness Report: {report.report_id} ═══",
        f"Generated: {report.generated_at}",
        f"Mode: {report.training_mode} | Strict Real Gate: {'ACTIVE' if report.strict_real_gate_active else 'INACTIVE'}",
        "",
        f"── Field Sample Counts ──",
    ]

    for f in report.field_samples:
        lab_status = "✓" if f.lab_meets_min else "✗"
        real_status = "✓" if f.real_meets_min else "✗"
        lines.append(
            f"  {f.field_name}: LAB={f.lab_count:>8,} {lab_status} | REAL={f.real_count:>8,} {real_status}"
        )

    lines.extend([
        "",
        f"── Quality ──",
        f"  Balance: {report.quality_metrics.class_balance_ratio:.4f}",
        f"  Entropy: {report.quality_metrics.entropy_bits:.4f} bits",
        f"  Dup ratio: {report.quality_metrics.duplicate_ratio:.4f}",
        f"  Trust: {report.quality_metrics.source_trust_avg:.4f}",
        f"  Forbidden: {'YES ✗' if report.quality_metrics.forbidden_fields_found else 'NO ✓'}",
        "",
        f"── Sync/Recovery ──",
        f"  Cluster: {report.sync_recovery.cluster_size} nodes",
        f"  All alive: {'✓' if report.sync_recovery.all_nodes_alive else '✗'}",
        f"  Redundant: {'✓' if report.sync_recovery.shards_redundant else '✗'}",
        "",
        f"── Voice Audit ──",
        f"  Total: {report.voice_audit.total_commands} | OK: {report.voice_audit.completed} | Failed: {report.voice_audit.failed} | Rejected: {report.voice_audit.rejected}",
        "",
        f"── SMTP ──",
        f"  Configured: {'✓' if report.smtp_status.configured else '✗'}",
        f"  Sent: {report.smtp_status.total_sent} | Failed: {report.smtp_status.total_failed}",
        "",
        f"══ OVERALL: {'READY ✓' if report.overall_ready else 'NOT READY ✗'} ══",
    ])

    if report.blocking_reasons:
        lines.append(f"\nBlocking reasons ({len(report.blocking_reasons)}):")
        for r in report.blocking_reasons:
            lines.append(f"  ✗ {r}")

    return "\n".join(lines)


def save_report(report: ProductionReadinessReport, output_dir: str = "reports") -> str:
    """Save report to disk as JSON."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{report.report_id}.json"
    path.write_text(report_to_json(report), encoding="utf-8")
    logger.info(f"Report saved: {path}")
    return str(path)
