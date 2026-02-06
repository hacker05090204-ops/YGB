"""
Model Registry + Version Governance
=====================================

Only registered models may run.
Unregistered → abort.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from pathlib import Path
import json
import hashlib


# =============================================================================
# MODEL ENTRY
# =============================================================================

@dataclass
class ModelEntry:
    """Entry in the model registry."""
    model_id: str
    version: str
    model_hash: str
    dataset_hash: str
    calibration_metrics: Dict[str, float]
    drift_history: List[dict]
    deployment_date: str
    rollback_reference: Optional[str]
    is_active: bool


# =============================================================================
# MODEL REGISTRY
# =============================================================================

class ModelRegistry:
    """Registry for validated models."""
    
    REGISTRY_FILE = Path("impl_v1/governance/MODEL_REGISTRY.json")
    MAX_AGE_DAYS = 365  # Annual revalidation
    
    def __init__(self):
        self.models: Dict[str, ModelEntry] = {}
        self._load_registry()
    
    def _load_registry(self) -> None:
        """Load registry from file."""
        if self.REGISTRY_FILE.exists():
            try:
                with open(self.REGISTRY_FILE, "r") as f:
                    data = json.load(f)
                
                for model_id, entry in data.get("models", {}).items():
                    self.models[model_id] = ModelEntry(**entry)
            except Exception:
                pass
    
    def _save_registry(self) -> None:
        """Save registry to file."""
        self.REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.REGISTRY_FILE, "w") as f:
            json.dump({
                "models": {
                    model_id: {
                        "model_id": m.model_id,
                        "version": m.version,
                        "model_hash": m.model_hash,
                        "dataset_hash": m.dataset_hash,
                        "calibration_metrics": m.calibration_metrics,
                        "drift_history": m.drift_history,
                        "deployment_date": m.deployment_date,
                        "rollback_reference": m.rollback_reference,
                        "is_active": m.is_active,
                    }
                    for model_id, m in self.models.items()
                },
                "last_updated": datetime.now().isoformat(),
            }, f, indent=2)
    
    def register_model(
        self,
        model_id: str,
        version: str,
        model_path: Path,
        dataset_hash: str,
        calibration_metrics: Dict[str, float],
        rollback_reference: Optional[str] = None,
    ) -> ModelEntry:
        """Register a new model."""
        # Compute model hash
        model_hash = self._compute_hash(model_path)
        
        entry = ModelEntry(
            model_id=model_id,
            version=version,
            model_hash=model_hash,
            dataset_hash=dataset_hash,
            calibration_metrics=calibration_metrics,
            drift_history=[],
            deployment_date=datetime.now().isoformat(),
            rollback_reference=rollback_reference,
            is_active=True,
        )
        
        self.models[model_id] = entry
        self._save_registry()
        
        return entry
    
    def _compute_hash(self, path: Path) -> str:
        """Compute SHA256 hash of model file."""
        if not path.exists():
            return "MOCK_HASH_" + path.name
        
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def is_registered(self, model_id: str, model_hash: str = None) -> Tuple[bool, str]:
        """Check if model is registered."""
        if model_id not in self.models:
            return False, "Model not in registry"
        
        entry = self.models[model_id]
        
        if model_hash and entry.model_hash != model_hash:
            return False, "Model hash mismatch - possible tampering"
        
        if not entry.is_active:
            return False, "Model is deactivated"
        
        return True, "Model registered"
    
    def validate_for_execution(self, model_id: str) -> Tuple[bool, str]:
        """Validate model can be executed."""
        registered, msg = self.is_registered(model_id)
        
        if not registered:
            return False, f"ABORT: {msg}"
        
        # Check age
        entry = self.models[model_id]
        deployment = datetime.fromisoformat(entry.deployment_date)
        age = datetime.now() - deployment
        
        if age.days > self.MAX_AGE_DAYS:
            return False, f"ABORT: Model expired ({age.days} days old). Revalidation required."
        
        return True, "Model validated for execution"
    
    def record_drift(self, model_id: str, drift_event: dict) -> None:
        """Record a drift event."""
        if model_id in self.models:
            self.models[model_id].drift_history.append({
                **drift_event,
                "timestamp": datetime.now().isoformat(),
            })
            self._save_registry()
    
    def deactivate_model(self, model_id: str, reason: str) -> None:
        """Deactivate a model."""
        if model_id in self.models:
            self.models[model_id].is_active = False
            self.record_drift(model_id, {"event": "deactivated", "reason": reason})
    
    def get_active_model(self) -> Optional[ModelEntry]:
        """Get the currently active model."""
        for entry in self.models.values():
            if entry.is_active:
                return entry
        return None
