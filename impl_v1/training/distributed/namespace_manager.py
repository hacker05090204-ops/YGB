"""
namespace_manager.py — Data Growth Management (Phase 7)

Separate shard namespace per field:
- Each field independent 110GB cap
- Auto-create namespace for new field
- Track per-namespace usage
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_LIMIT_GB = 110.0


@dataclass
class Namespace:
    """A shard namespace (per field)."""
    namespace_id: str
    field_name: str
    limit_gb: float
    used_bytes: int = 0
    shard_count: int = 0
    created_at: str = ""


@dataclass
class NamespaceReport:
    """Report of all namespaces."""
    total_namespaces: int
    total_used_gb: float
    namespaces: List[Namespace]
    warnings: List[str]


class NamespaceManager:
    """Manages per-field shard namespaces.

    Each field (e.g., vulnerability, pattern, feature) gets its own
    independent 110GB cap.
    """

    def __init__(self, default_limit_gb: float = DEFAULT_LIMIT_GB):
        self.default_limit_gb = default_limit_gb
        self._namespaces: Dict[str, Namespace] = {}

    def get_or_create(self, field_name: str) -> Namespace:
        """Get existing namespace or auto-create."""
        ns_id = f"ns_{field_name}"

        if ns_id not in self._namespaces:
            self._namespaces[ns_id] = Namespace(
                namespace_id=ns_id,
                field_name=field_name,
                limit_gb=self.default_limit_gb,
                created_at=datetime.now().isoformat(),
            )
            logger.info(
                f"[NAMESPACE] Created: {ns_id} "
                f"limit={self.default_limit_gb}GB"
            )

        return self._namespaces[ns_id]

    def add_shard(
        self,
        field_name: str,
        shard_size_bytes: int,
    ) -> bool:
        """Add a shard to a namespace.

        Returns False if would exceed limit.
        """
        ns = self.get_or_create(field_name)
        limit_bytes = int(ns.limit_gb * 1024 ** 3)

        if ns.used_bytes + shard_size_bytes > limit_bytes:
            logger.warning(
                f"[NAMESPACE] {ns.namespace_id}: "
                f"would exceed {ns.limit_gb}GB limit"
            )
            return False

        ns.used_bytes += shard_size_bytes
        ns.shard_count += 1

        logger.info(
            f"[NAMESPACE] {ns.namespace_id}: "
            f"+{shard_size_bytes / (1024**2):.1f}MB "
            f"({ns.used_bytes / (1024**3):.2f}GB / {ns.limit_gb}GB)"
        )
        return True

    def remove_shard(self, field_name: str, shard_size_bytes: int):
        """Remove shard accounting from namespace."""
        ns_id = f"ns_{field_name}"
        if ns_id in self._namespaces:
            ns = self._namespaces[ns_id]
            ns.used_bytes = max(0, ns.used_bytes - shard_size_bytes)
            ns.shard_count = max(0, ns.shard_count - 1)

    def get_report(self) -> NamespaceReport:
        """Get status of all namespaces."""
        warnings = []
        total_gb = 0.0

        for ns in self._namespaces.values():
            used_gb = ns.used_bytes / (1024 ** 3)
            total_gb += used_gb
            pct = (used_gb / ns.limit_gb * 100) if ns.limit_gb > 0 else 0

            if pct > 85:
                warnings.append(
                    f"{ns.namespace_id}: {pct:.1f}% capacity"
                )

        return NamespaceReport(
            total_namespaces=len(self._namespaces),
            total_used_gb=round(total_gb, 4),
            namespaces=list(self._namespaces.values()),
            warnings=warnings,
        )

    def list_namespaces(self) -> List[str]:
        return list(self._namespaces.keys())
