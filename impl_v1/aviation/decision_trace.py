"""
Decision Trace Engine
======================

For every scan, store immutable trace:
- input_hash (SHA256)
- feature_vector_hash
- model_version
- checkpoint_hash
- calibration_snapshot
- confidence_score
- decision_boundary_distance
- entropy_score

Hash-chained and replayable.
"""

from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path
import json
import hashlib


# =============================================================================
# DECISION TRACE
# =============================================================================

@dataclass
class DecisionTrace:
    """Immutable decision trace record."""
    scan_id: str
    timestamp: str
    input_hash: str
    feature_vector_hash: str
    model_version: str
    checkpoint_hash: str
    calibration_snapshot: Dict[str, float]
    confidence_score: float
    decision_boundary_distance: float
    entropy_score: float
    decision: str
    previous_hash: str
    trace_hash: str


# =============================================================================
# TRACE ENGINE
# =============================================================================

class DecisionTraceEngine:
    """Engine for decision tracing."""
    
    TRACE_DIR = Path("reports/decision_trace")
    CHAIN_FILE = Path("reports/decision_trace/chain.json")
    
    def __init__(self):
        self.TRACE_DIR.mkdir(parents=True, exist_ok=True)
        self.last_hash = self._load_chain_head()
    
    def _load_chain_head(self) -> str:
        """Load the last hash in the chain."""
        if self.CHAIN_FILE.exists():
            try:
                with open(self.CHAIN_FILE, "r") as f:
                    data = json.load(f)
                return data.get("last_hash", "GENESIS")
            except Exception:
                pass
        return "GENESIS"
    
    def _save_chain_head(self, hash_value: str) -> None:
        """Save the chain head."""
        with open(self.CHAIN_FILE, "w") as f:
            json.dump({
                "last_hash": hash_value,
                "updated": datetime.now().isoformat(),
            }, f, indent=2)
    
    def compute_hash(self, data: str) -> str:
        """Compute SHA256 hash."""
        return hashlib.sha256(data.encode()).hexdigest()
    
    def create_trace(
        self,
        scan_id: str,
        input_data: str,
        feature_vector: dict,
        model_version: str,
        checkpoint_hash: str,
        calibration: Dict[str, float],
        confidence: float,
        boundary_distance: float,
        entropy: float,
        decision: str,
    ) -> DecisionTrace:
        """Create and store a decision trace."""
        timestamp = datetime.now().isoformat()
        
        # Compute hashes
        input_hash = self.compute_hash(input_data)
        feature_hash = self.compute_hash(json.dumps(feature_vector, sort_keys=True))
        
        # Build trace content for hashing
        trace_content = json.dumps({
            "scan_id": scan_id,
            "timestamp": timestamp,
            "input_hash": input_hash,
            "feature_vector_hash": feature_hash,
            "model_version": model_version,
            "checkpoint_hash": checkpoint_hash,
            "calibration_snapshot": calibration,
            "confidence_score": confidence,
            "decision_boundary_distance": boundary_distance,
            "entropy_score": entropy,
            "decision": decision,
            "previous_hash": self.last_hash,
        }, sort_keys=True)
        
        trace_hash = self.compute_hash(trace_content)
        
        trace = DecisionTrace(
            scan_id=scan_id,
            timestamp=timestamp,
            input_hash=input_hash,
            feature_vector_hash=feature_hash,
            model_version=model_version,
            checkpoint_hash=checkpoint_hash,
            calibration_snapshot=calibration,
            confidence_score=round(confidence, 6),
            decision_boundary_distance=round(boundary_distance, 6),
            entropy_score=round(entropy, 6),
            decision=decision,
            previous_hash=self.last_hash,
            trace_hash=trace_hash,
        )
        
        self._store_trace(trace)
        self.last_hash = trace_hash
        self._save_chain_head(trace_hash)
        
        return trace
    
    def _store_trace(self, trace: DecisionTrace) -> Path:
        """Store trace to file (immutable)."""
        filepath = self.TRACE_DIR / f"{trace.scan_id}.trace.json"
        
        with open(filepath, "w") as f:
            json.dump({
                "scan_id": trace.scan_id,
                "timestamp": trace.timestamp,
                "input_hash": trace.input_hash,
                "feature_vector_hash": trace.feature_vector_hash,
                "model_version": trace.model_version,
                "checkpoint_hash": trace.checkpoint_hash,
                "calibration_snapshot": trace.calibration_snapshot,
                "confidence_score": trace.confidence_score,
                "decision_boundary_distance": trace.decision_boundary_distance,
                "entropy_score": trace.entropy_score,
                "decision": trace.decision,
                "previous_hash": trace.previous_hash,
                "trace_hash": trace.trace_hash,
            }, f, indent=2)
        
        return filepath
    
    def verify_chain(self) -> tuple:
        """Verify entire trace chain integrity."""
        traces = sorted(self.TRACE_DIR.glob("*.trace.json"))
        
        if not traces:
            return True, "No traces to verify"
        
        previous_hash = "GENESIS"
        
        for trace_file in traces:
            with open(trace_file, "r") as f:
                trace = json.load(f)
            
            if trace["previous_hash"] != previous_hash:
                return False, f"Chain broken at {trace_file.name}"
            
            # Verify hash
            content = json.dumps({
                "scan_id": trace["scan_id"],
                "timestamp": trace["timestamp"],
                "input_hash": trace["input_hash"],
                "feature_vector_hash": trace["feature_vector_hash"],
                "model_version": trace["model_version"],
                "checkpoint_hash": trace["checkpoint_hash"],
                "calibration_snapshot": trace["calibration_snapshot"],
                "confidence_score": trace["confidence_score"],
                "decision_boundary_distance": trace["decision_boundary_distance"],
                "entropy_score": trace["entropy_score"],
                "decision": trace["decision"],
                "previous_hash": trace["previous_hash"],
            }, sort_keys=True)
            
            expected_hash = self.compute_hash(content)
            
            if trace["trace_hash"] != expected_hash:
                return False, f"Hash mismatch at {trace_file.name}"
            
            previous_hash = trace["trace_hash"]
        
        return True, "Chain verified"
    
    def replay_trace(self, scan_id: str) -> Optional[DecisionTrace]:
        """Replay a specific trace."""
        filepath = self.TRACE_DIR / f"{scan_id}.trace.json"
        
        if not filepath.exists():
            return None
        
        with open(filepath, "r") as f:
            data = json.load(f)
        
        return DecisionTrace(**data)
