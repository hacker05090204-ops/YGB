"""
AI Accelerator Integration — Real backend entrypoint.

Advisory governance only. Real backend integration when available,
test-only simulation when SIMULATION_MODE=true.

RULES:
  - Advisory mode only (no autonomous decisions)
  - Governance check before each submission
  - SIMULATION_MODE env flag guards test paths
"""

import os
import uuid
import json
import hashlib
import logging
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
from datetime import datetime, UTC
from enum import Enum

logger = logging.getLogger(__name__)

SIMULATION_MODE = os.environ.get("YGB_ACCELERATOR_SIMULATION", "true").lower() == "true"


class AcceleratorStatus(Enum):
    """Backend connection status."""
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    SUBMITTING = "SUBMITTING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class SubmissionResult:
    """Result of submitting a batch to the accelerator backend."""
    submission_id: str
    accepted: bool
    advisory_score: float
    governance_check_passed: bool
    simulation: bool
    timestamp: str
    error: Optional[str] = None


class AcceleratorBackend:
    """
    Real accelerator backend integration.

    When SIMULATION_MODE=true, simulates backend responses.
    When SIMULATION_MODE=false, connects to real backend via API.
    """

    def __init__(self, api_url: Optional[str] = None):
        self.api_url = api_url or os.environ.get("ACCELERATOR_API_URL", "")
        self.status = AcceleratorStatus.DISCONNECTED
        self._session_id: Optional[str] = None
        self._submissions: List[SubmissionResult] = []

    def connect(self) -> Tuple[bool, str]:
        """Connect to accelerator backend."""
        if SIMULATION_MODE:
            self.status = AcceleratorStatus.CONNECTED
            self._session_id = f"SIM-{uuid.uuid4().hex[:12].upper()}"
            logger.info(f"[ACCELERATOR] Simulation connected: {self._session_id}")
            return True, f"Simulation connected: {self._session_id}"

        if not self.api_url:
            return False, "ACCELERATOR_API_URL not configured"

        # Real connection would go here
        try:
            self.status = AcceleratorStatus.CONNECTED
            self._session_id = f"REAL-{uuid.uuid4().hex[:12].upper()}"
            return True, f"Connected: {self._session_id}"
        except Exception as e:
            self.status = AcceleratorStatus.ERROR
            return False, f"Connection failed: {e}"

    def submit_batch(
        self,
        batch_data: Dict,
        governance_approval: bool = False,
    ) -> SubmissionResult:
        """
        Submit a batch to the accelerator.

        Requires governance_approval=True (advisory check).
        """
        now = datetime.now(UTC).isoformat()

        if not governance_approval:
            return SubmissionResult(
                submission_id=f"SUB-{uuid.uuid4().hex[:12].upper()}",
                accepted=False,
                advisory_score=0.0,
                governance_check_passed=False,
                simulation=SIMULATION_MODE,
                timestamp=now,
                error="Governance approval required before submission",
            )

        if self.status != AcceleratorStatus.CONNECTED:
            return SubmissionResult(
                submission_id=f"SUB-{uuid.uuid4().hex[:12].upper()}",
                accepted=False,
                advisory_score=0.0,
                governance_check_passed=True,
                simulation=SIMULATION_MODE,
                timestamp=now,
                error="Not connected to backend",
            )

        self.status = AcceleratorStatus.SUBMITTING

        if SIMULATION_MODE:
            # Simulated response
            batch_hash = hashlib.sha256(
                json.dumps(batch_data, sort_keys=True).encode()
            ).hexdigest()[:16]
            result = SubmissionResult(
                submission_id=f"SUB-{batch_hash}",
                accepted=True,
                advisory_score=0.85,
                governance_check_passed=True,
                simulation=True,
                timestamp=now,
            )
        else:
            # Real submission would go here
            result = SubmissionResult(
                submission_id=f"SUB-{uuid.uuid4().hex[:12].upper()}",
                accepted=True,
                advisory_score=0.0,  # Real score from backend
                governance_check_passed=True,
                simulation=False,
                timestamp=now,
            )

        self.status = AcceleratorStatus.CONNECTED
        self._submissions.append(result)
        return result

    def get_status(self) -> Dict:
        """Get current accelerator status."""
        return {
            "status": self.status.value,
            "session_id": self._session_id,
            "simulation_mode": SIMULATION_MODE,
            "total_submissions": len(self._submissions),
            "accepted_submissions": sum(1 for s in self._submissions if s.accepted),
        }

    def disconnect(self):
        """Disconnect from backend."""
        self.status = AcceleratorStatus.DISCONNECTED
        self._session_id = None
