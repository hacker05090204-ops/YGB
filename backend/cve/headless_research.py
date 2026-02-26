"""
Headless Edge Research Layer — Playwright + Edge Headless

For research/enrichment/fallback ONLY.
- Stores page snapshot hash, extracted fields, source URL, extraction version,
  timestamp, confidence.
- If extraction confidence < 0.7 or schema fails → RESEARCH_PENDING quarantine.
- NEVER promotes headless-only facts to canonical truth.
- Aligned with native/browser_curriculum/edge_headless_engine.cpp domain whitelist.
"""

import hashlib
import logging
import re
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger("ygb.headless_research")

EXTRACTION_VERSION = "1.0.0"

# Domain whitelist — aligned with edge_headless_engine.cpp
ALLOWED_DOMAINS = frozenset([
    "nvd.nist.gov", "services.nvd.nist.gov",
    "cve.org", "www.cve.org", "cveawg.mitre.org",
    "owasp.org", "www.owasp.org", "cheatsheetseries.owasp.org",
    "cwe.mitre.org", "capec.mitre.org",
    "www.cvedetails.com", "cvedetails.com",
    "portswigger.net", "www.portswigger.net",
    "blog.cloudflare.com", "security.googleblog.com",
    "msrc.microsoft.com",
])

BLOCKED_PATTERNS = [
    "login", "signin", "signup", "register", "oauth",
    "auth/", "account", "password", "credential", "session",
    ".exe", ".msi", ".bat", ".ps1", ".sh",
    "exploit-db.com", "pastebin.com",
]

CONFIDENCE_THRESHOLD = 0.7


class ResearchStatus(Enum):
    RESEARCH_PENDING = "RESEARCH_PENDING"
    EXTRACTED = "EXTRACTED"
    QUARANTINED = "QUARANTINED"
    SCHEMA_FAIL = "SCHEMA_FAIL"


@dataclass
class ResearchSnapshot:
    """A research page snapshot with extracted data."""
    snapshot_id: str
    source_url: str
    page_hash: str               # SHA-256 of page content
    extracted_fields: Dict[str, Any]
    extraction_version: str
    timestamp: str
    confidence: float            # 0.0 - 1.0
    status: ResearchStatus
    quarantine_reason: str = ""
    cve_ids_found: List[str] = field(default_factory=list)


class HeadlessResearchEngine:
    """Headless Edge browser research engine for CVE enrichment.

    GOVERNANCE: Research-only. Never promotes unverified to canonical.
    """

    def __init__(self):
        self._snapshots: Dict[str, ResearchSnapshot] = {}
        self._quarantine: List[ResearchSnapshot] = []

    def is_url_allowed(self, url: str) -> bool:
        """Check if URL is allowed per domain whitelist."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.hostname or ""
            if domain not in ALLOWED_DOMAINS:
                return False
            # Check blocked patterns
            lower_url = url.lower()
            for pattern in BLOCKED_PATTERNS:
                if pattern in lower_url:
                    return False
            # HTTPS only
            if parsed.scheme != "https":
                return False
            return True
        except Exception:
            return False

    def extract_cve_ids(self, content: str) -> List[str]:
        """Extract CVE IDs from page content."""
        pattern = r"CVE-\d{4}-\d{4,}"
        matches = re.findall(pattern, content, re.IGNORECASE)
        return list(set(m.upper() for m in matches))

    def compute_page_hash(self, content: str) -> str:
        """SHA-256 of sanitized page content."""
        # Strip whitespace for stable hash
        sanitized = re.sub(r"\s+", " ", content.strip())
        return hashlib.sha256(sanitized.encode("utf-8")).hexdigest()

    def compute_extraction_confidence(
        self, extracted: Dict[str, Any]
    ) -> float:
        """Score extraction confidence based on field completeness."""
        required_fields = [
            "cve_id", "description", "severity",
        ]
        optional_fields = [
            "cvss_score", "affected_products", "references",
            "published_date",
        ]

        score = 0.0
        total_weight = 0.0

        for f in required_fields:
            total_weight += 2.0
            val = extracted.get(f)
            if val and str(val).strip():
                score += 2.0

        for f in optional_fields:
            total_weight += 1.0
            val = extracted.get(f)
            if val and str(val).strip():
                score += 1.0

        if total_weight == 0:
            return 0.0
        return round(score / total_weight, 4)

    def validate_schema(self, extracted: Dict[str, Any]) -> bool:
        """Validate extracted data has minimum required schema."""
        cve_id = extracted.get("cve_id", "")
        if not cve_id or not re.match(
            r"^CVE-\d{4}-\d{4,}$", cve_id, re.IGNORECASE
        ):
            return False
        if not extracted.get("description"):
            return False
        return True

    def create_snapshot(
        self,
        source_url: str,
        page_content: str,
        extracted_fields: Dict[str, Any],
    ) -> ResearchSnapshot:
        """Create a research snapshot from fetched page.

        Returns snapshot with status:
        - EXTRACTED if confidence >= threshold and schema valid
        - QUARANTINED if confidence < threshold
        - SCHEMA_FAIL if required fields missing
        """
        page_hash = self.compute_page_hash(page_content)
        confidence = self.compute_extraction_confidence(extracted_fields)
        cve_ids = self.extract_cve_ids(page_content)
        snapshot_id = f"RS-{page_hash[:16].upper()}"

        # Schema validation
        if not self.validate_schema(extracted_fields):
            snapshot = ResearchSnapshot(
                snapshot_id=snapshot_id,
                source_url=source_url,
                page_hash=page_hash,
                extracted_fields=extracted_fields,
                extraction_version=EXTRACTION_VERSION,
                timestamp=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                status=ResearchStatus.SCHEMA_FAIL,
                quarantine_reason="Required fields missing or invalid",
                cve_ids_found=cve_ids,
            )
            self._quarantine.append(snapshot)
            self._snapshots[snapshot_id] = snapshot
            logger.warning(
                f"[HEADLESS] Schema fail for {source_url}: "
                f"conf={confidence}"
            )
            return snapshot

        # Confidence check
        if confidence < CONFIDENCE_THRESHOLD:
            snapshot = ResearchSnapshot(
                snapshot_id=snapshot_id,
                source_url=source_url,
                page_hash=page_hash,
                extracted_fields=extracted_fields,
                extraction_version=EXTRACTION_VERSION,
                timestamp=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                status=ResearchStatus.QUARANTINED,
                quarantine_reason=(
                    f"Confidence {confidence} < threshold "
                    f"{CONFIDENCE_THRESHOLD}"
                ),
                cve_ids_found=cve_ids,
            )
            self._quarantine.append(snapshot)
            self._snapshots[snapshot_id] = snapshot
            logger.warning(
                f"[HEADLESS] Quarantined {source_url}: "
                f"conf={confidence}"
            )
            return snapshot

        # Good extraction
        snapshot = ResearchSnapshot(
            snapshot_id=snapshot_id,
            source_url=source_url,
            page_hash=page_hash,
            extracted_fields=extracted_fields,
            extraction_version=EXTRACTION_VERSION,
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=confidence,
            status=ResearchStatus.EXTRACTED,
            cve_ids_found=cve_ids,
        )
        self._snapshots[snapshot_id] = snapshot
        logger.info(
            f"[HEADLESS] Extracted from {source_url}: "
            f"conf={confidence}, cves={len(cve_ids)}"
        )
        return snapshot

    def get_quarantined(self) -> List[ResearchSnapshot]:
        """Get all quarantined snapshots."""
        return list(self._quarantine)

    def get_all_snapshots(self) -> Dict[str, ResearchSnapshot]:
        """Get all snapshots."""
        return dict(self._snapshots)

    def get_status(self) -> Dict[str, Any]:
        """Get engine status."""
        total = len(self._snapshots)
        quarantined = len(self._quarantine)
        extracted = sum(
            1 for s in self._snapshots.values()
            if s.status == ResearchStatus.EXTRACTED
        )
        return {
            "total_snapshots": total,
            "extracted": extracted,
            "quarantined": quarantined,
            "schema_fails": total - extracted - quarantined,
            "allowed_domains": len(ALLOWED_DOMAINS),
        }


# =============================================================================
# SINGLETON
# =============================================================================

_engine: Optional[HeadlessResearchEngine] = None


def get_research_engine() -> HeadlessResearchEngine:
    """Get or create the headless research engine singleton."""
    global _engine
    if _engine is None:
        _engine = HeadlessResearchEngine()
    return _engine
