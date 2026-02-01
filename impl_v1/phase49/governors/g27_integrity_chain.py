# G27: Evidence Integrity Chain Governor
"""
Tamper-proof evidence verification via hash chaining.

Chain-of-custody model:
- Every evidence item gets SHA-256 hash
- Hash chain links prev → next
- Session-bound integrity
- Report invalidation on mismatch

FAILURE = REPORT INVALID
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
import hashlib
import uuid
from datetime import datetime, UTC


class ChainStatus(Enum):
    """CLOSED ENUM - Chain verification status."""
    VALID = "VALID"
    INVALID = "INVALID"
    BROKEN = "BROKEN"
    EMPTY = "EMPTY"


class IntegrityViolation(Enum):
    """CLOSED ENUM - Types of integrity violations."""
    HASH_MISMATCH = "HASH_MISMATCH"
    CHAIN_BREAK = "CHAIN_BREAK"
    MISSING_LINK = "MISSING_LINK"
    TIMESTAMP_ANOMALY = "TIMESTAMP_ANOMALY"
    SESSION_MISMATCH = "SESSION_MISMATCH"


@dataclass(frozen=True)
class ChainLink:
    """Single link in the integrity chain."""
    link_id: str
    evidence_id: str
    content_hash: str
    prev_hash: Optional[str]  # None for genesis
    link_hash: str  # Hash of (content_hash + prev_hash)
    timestamp: str
    session_id: str
    sequence: int


@dataclass(frozen=True)
class ChainVerificationResult:
    """Result of chain verification."""
    chain_id: str
    status: ChainStatus
    total_links: int
    verified_links: int
    violations: Tuple["IntegrityViolationRecord", ...]
    computed_root_hash: Optional[str]
    is_valid: bool


@dataclass(frozen=True)
class IntegrityViolationRecord:
    """Record of an integrity violation."""
    violation_type: IntegrityViolation
    link_id: str
    expected: str
    actual: str
    message: str


@dataclass(frozen=True)
class ReportIntegrityStatus:
    """Report integrity status for embedding in reports."""
    report_id: str
    chain_id: str
    is_valid: bool
    root_hash: str
    evidence_count: int
    verification_timestamp: str


# =============================================================================
# GUARDS (MANDATORY)
# =============================================================================

def can_integrity_skip_verification() -> bool:
    """
    Guard: Can we skip integrity verification?
    
    ANSWER: NEVER.
    """
    return False


def can_integrity_modify_chain() -> bool:
    """
    Guard: Can integrity chain be modified after creation?
    
    ANSWER: NEVER.
    """
    return False


def can_report_bypass_integrity() -> bool:
    """
    Guard: Can a report be generated without integrity check?
    
    ANSWER: NEVER.
    """
    return False


# =============================================================================
# HASH FUNCTIONS
# =============================================================================

def compute_content_hash(content: bytes) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content).hexdigest()


def compute_link_hash(content_hash: str, prev_hash: Optional[str]) -> str:
    """Compute hash of a chain link."""
    combined = content_hash + (prev_hash or "GENESIS")
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def compute_chain_root_hash(chain: List[ChainLink]) -> Optional[str]:
    """Compute root hash of entire chain."""
    if not chain:
        return None
    
    combined = "|".join(link.link_hash for link in chain)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


# =============================================================================
# CHAIN BUILDER
# =============================================================================

class IntegrityChainBuilder:
    """Builder for evidence integrity chain."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.chain_id = f"CHN-{uuid.uuid4().hex[:16].upper()}"
        self._links: List[ChainLink] = []
        self._sequence = 0
    
    def add_evidence(self, evidence_id: str, content: bytes) -> ChainLink:
        """
        Add evidence to the chain.
        
        Returns the created chain link.
        """
        if can_integrity_modify_chain() and len(self._links) > 0:  # pragma: no cover
            raise RuntimeError("SECURITY: Cannot modify existing chain")  # pragma: no cover
        
        content_hash = compute_content_hash(content)
        prev_hash = self._links[-1].link_hash if self._links else None
        link_hash = compute_link_hash(content_hash, prev_hash)
        
        link = ChainLink(
            link_id=f"LNK-{uuid.uuid4().hex[:12].upper()}",
            evidence_id=evidence_id,
            content_hash=content_hash,
            prev_hash=prev_hash,
            link_hash=link_hash,
            timestamp=datetime.now(UTC).isoformat(),
            session_id=self.session_id,
            sequence=self._sequence,
        )
        
        self._links.append(link)
        self._sequence += 1
        
        return link
    
    def get_chain(self) -> Tuple[ChainLink, ...]:
        """Get immutable chain."""
        return tuple(self._links)
    
    def get_root_hash(self) -> Optional[str]:
        """Get root hash of current chain."""
        return compute_chain_root_hash(self._links)


# =============================================================================
# CHAIN VERIFIER
# =============================================================================

class IntegrityChainVerifier:
    """Verifier for integrity chains."""
    
    def verify_chain(
        self,
        chain: Tuple[ChainLink, ...],
        session_id: str,
    ) -> ChainVerificationResult:
        """
        Verify integrity of a chain.
        
        Checks:
        1. Hash chain continuity
        2. Link hash correctness
        3. Session binding
        4. Sequence order
        """
        if can_integrity_skip_verification():  # pragma: no cover
            raise RuntimeError("SECURITY: Cannot skip verification")  # pragma: no cover
        
        chain_id = chain[0].link_id.replace("LNK", "CHN") if chain else "CHN-EMPTY"
        
        if not chain:
            return ChainVerificationResult(
                chain_id=chain_id,
                status=ChainStatus.EMPTY,
                total_links=0,
                verified_links=0,
                violations=(),
                computed_root_hash=None,
                is_valid=True,  # Empty chain is valid
            )
        
        violations: List[IntegrityViolationRecord] = []
        verified_count = 0
        
        for i, link in enumerate(chain):
            # Check session binding
            if link.session_id != session_id:
                violations.append(IntegrityViolationRecord(
                    violation_type=IntegrityViolation.SESSION_MISMATCH,
                    link_id=link.link_id,
                    expected=session_id,
                    actual=link.session_id,
                    message=f"Link {i} bound to wrong session",
                ))
                continue
            
            # Check sequence
            if link.sequence != i:
                violations.append(IntegrityViolationRecord(
                    violation_type=IntegrityViolation.MISSING_LINK,
                    link_id=link.link_id,
                    expected=str(i),
                    actual=str(link.sequence),
                    message=f"Sequence mismatch at position {i}",
                ))
                continue
            
            # Check prev_hash for non-genesis
            if i > 0:
                expected_prev = chain[i - 1].link_hash
                if link.prev_hash != expected_prev:
                    violations.append(IntegrityViolationRecord(
                        violation_type=IntegrityViolation.CHAIN_BREAK,
                        link_id=link.link_id,
                        expected=expected_prev,
                        actual=link.prev_hash or "None",
                        message=f"Chain break at link {i}",
                    ))
                    continue
            else:
                # Genesis link should have no prev_hash
                if link.prev_hash is not None:
                    violations.append(IntegrityViolationRecord(
                        violation_type=IntegrityViolation.CHAIN_BREAK,
                        link_id=link.link_id,
                        expected="None",
                        actual=link.prev_hash,
                        message="Genesis link should not have prev_hash",
                    ))
                    continue
            
            # Verify link hash
            expected_link_hash = compute_link_hash(link.content_hash, link.prev_hash)
            if link.link_hash != expected_link_hash:
                violations.append(IntegrityViolationRecord(
                    violation_type=IntegrityViolation.HASH_MISMATCH,
                    link_id=link.link_id,
                    expected=expected_link_hash,
                    actual=link.link_hash,
                    message=f"Link hash mismatch at {i}",
                ))
                continue
            
            verified_count += 1
        
        is_valid = len(violations) == 0
        status = ChainStatus.VALID if is_valid else ChainStatus.INVALID
        
        if not is_valid and any(
            v.violation_type == IntegrityViolation.CHAIN_BREAK
            for v in violations
        ):
            status = ChainStatus.BROKEN
        
        return ChainVerificationResult(
            chain_id=chain_id,
            status=status,
            total_links=len(chain),
            verified_links=verified_count,
            violations=tuple(violations),
            computed_root_hash=compute_chain_root_hash(list(chain)),
            is_valid=is_valid,
        )


# =============================================================================
# REPORT INTEGRITY
# =============================================================================

def verify_for_report(
    chain: Tuple[ChainLink, ...],
    report_id: str,
    session_id: str,
) -> ReportIntegrityStatus:
    """
    Verify chain and generate report integrity status.
    
    Must be embedded in every report.
    """
    if can_report_bypass_integrity():  # pragma: no cover
        raise RuntimeError("SECURITY: Cannot bypass integrity for report")  # pragma: no cover
    
    verifier = IntegrityChainVerifier()
    result = verifier.verify_chain(chain, session_id)
    
    return ReportIntegrityStatus(
        report_id=report_id,
        chain_id=result.chain_id,
        is_valid=result.is_valid,
        root_hash=result.computed_root_hash or "EMPTY",
        evidence_count=result.total_links,
        verification_timestamp=datetime.now(UTC).isoformat(),
    )


def invalidate_report_on_failure(
    integrity_status: ReportIntegrityStatus,
) -> bool:
    """
    Check if report should be invalidated.
    
    Returns True if report is INVALID.
    """
    return not integrity_status.is_valid
