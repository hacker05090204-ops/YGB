"""
data_scale_config.py — Field Data Scale Up (Phase 7)

Minimum 50,000 samples per field.
Target 100,000 for major fields.
Use synthetic only for bootstrapping.
Replace with real data gradually.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FieldDataConfig:
    """Data configuration for a field."""
    field_name: str
    min_samples: int = 50_000
    target_samples: int = 100_000
    current_samples: int = 0
    real_samples: int = 0
    synthetic_samples: int = 0
    is_major: bool = False
    bootstrap_only: bool = True


@dataclass
class ScaleReport:
    """Report on data scaling status."""
    total_fields: int
    fields_at_minimum: int
    fields_at_target: int
    fields_need_data: int
    total_samples: int
    total_real: int
    total_synthetic: int


# 23 recognized training fields
ALL_FIELDS = [
    "vulnerability_detection",
    "pattern_recognition",
    "anomaly_detection",
    "network_analysis",
    "binary_analysis",
    "malware_classification",
    "threat_intelligence",
    "code_review",
    "log_analysis",
    "incident_response",
    "forensic_analysis",
    "exploit_detection",
    "phishing_detection",
    "data_exfiltration",
    "privilege_escalation",
    "lateral_movement",
    "persistence_detection",
    "command_control",
    "cryptanalysis",
    "web_security",
    "api_security",
    "cloud_security",
    "iot_security",
]

MAJOR_FIELDS = [
    "vulnerability_detection",
    "malware_classification",
    "anomaly_detection",
    "network_analysis",
    "threat_intelligence",
]


class DataScaleManager:
    """Manages dataset scaling across all 23 fields.

    Min 50K samples. 100K target for major fields.
    Synthetic for bootstrap, real data replaces gradually.
    """

    def __init__(self):
        self._configs: Dict[str, FieldDataConfig] = {}
        self._init_fields()

    def _init_fields(self):
        for name in ALL_FIELDS:
            is_major = name in MAJOR_FIELDS
            self._configs[name] = FieldDataConfig(
                field_name=name,
                min_samples=50_000,
                target_samples=100_000 if is_major else 50_000,
                is_major=is_major,
            )

    def generate_bootstrap(
        self,
        field_name: str,
        feature_dim: int = 256,
        num_classes: int = 2,
        seed: int = 42,
    ) -> tuple:
        """Generate synthetic bootstrap data for a field."""
        cfg = self._configs.get(field_name)
        if cfg is None:
            raise ValueError(f"Unknown field: {field_name}")

        n = cfg.min_samples
        rng = np.random.RandomState(seed + hash(field_name) % 10000)
        X = rng.randn(n, feature_dim).astype(np.float32)
        y = rng.randint(0, num_classes, n).astype(np.int64)

        cfg.current_samples = n
        cfg.synthetic_samples = n
        cfg.bootstrap_only = True

        logger.info(
            f"[DATA_SCALE] Bootstrap: {field_name} — "
            f"{n:,} samples, dim={feature_dim}"
        )
        return X, y

    def add_real_data(self, field_name: str, count: int):
        """Record addition of real data samples."""
        cfg = self._configs.get(field_name)
        if cfg:
            cfg.real_samples += count
            cfg.current_samples += count
            if cfg.real_samples > 0:
                cfg.bootstrap_only = False
            logger.info(
                f"[DATA_SCALE] Real data: {field_name} +{count:,} "
                f"(total real={cfg.real_samples:,})"
            )

    def get_report(self) -> ScaleReport:
        """Get data scaling status."""
        at_min = 0
        at_target = 0
        need_data = 0
        total_s, total_r, total_syn = 0, 0, 0

        for cfg in self._configs.values():
            total_s += cfg.current_samples
            total_r += cfg.real_samples
            total_syn += cfg.synthetic_samples

            if cfg.current_samples >= cfg.target_samples:
                at_target += 1
            elif cfg.current_samples >= cfg.min_samples:
                at_min += 1
            else:
                need_data += 1

        return ScaleReport(
            total_fields=len(self._configs),
            fields_at_minimum=at_min,
            fields_at_target=at_target,
            fields_need_data=need_data,
            total_samples=total_s,
            total_real=total_r,
            total_synthetic=total_syn,
        )

    def get_field_config(self, field_name: str) -> FieldDataConfig:
        return self._configs[field_name]

    @property
    def field_count(self) -> int:
        return len(self._configs)

    @property
    def all_field_names(self) -> List[str]:
        return list(self._configs.keys())
