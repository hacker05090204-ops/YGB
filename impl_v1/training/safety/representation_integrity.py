"""
Representation Integrity Check
===============================

Monitor internal model representations:
- Layer weight mean/std
- Gradient norm
- Activation entropy
- Embedding variance

Flag suspicious checkpoints if deviation > 20%.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import math
import hashlib


# =============================================================================
# REPRESENTATION PROFILE
# =============================================================================

@dataclass
class LayerProfile:
    """Profile of a single layer."""
    layer_name: str
    weight_mean: float
    weight_std: float
    gradient_norm: float
    activation_entropy: float


@dataclass
class CheckpointProfile:
    """Profile of a checkpoint's representations."""
    checkpoint_id: str
    timestamp: str
    layer_profiles: Dict[str, LayerProfile]
    embedding_variance: float
    is_suspicious: bool = False
    suspicious_reason: str = ""


# =============================================================================
# REPRESENTATION MONITOR
# =============================================================================

class RepresentationIntegrityMonitor:
    """Monitor representation integrity across checkpoints."""
    
    DEVIATION_THRESHOLD = 0.20  # 20%
    
    def __init__(self):
        self.baseline: Optional[CheckpointProfile] = None
        self.history: List[CheckpointProfile] = []
        self.rolling_means: Dict[str, Dict[str, float]] = {}
    
    def compute_profile(self, model, checkpoint_id: str) -> CheckpointProfile:
        """Compute representation profile for a model."""
        try:
            import torch
            
            layer_profiles = {}
            total_embedding_var = 0.0
            layer_count = 0
            
            for name, param in model.named_parameters():
                if param.requires_grad:
                    weight_mean = param.data.mean().item()
                    weight_std = param.data.std().item()
                    
                    # Gradient norm (if available)
                    grad_norm = 0.0
                    if param.grad is not None:
                        grad_norm = param.grad.norm().item()
                    
                    # Entropy approximation
                    flat = param.data.flatten()
                    probs = torch.softmax(flat, dim=0)
                    entropy = -(probs * torch.log(probs + 1e-10)).sum().item()
                    
                    layer_profiles[name] = LayerProfile(
                        layer_name=name,
                        weight_mean=weight_mean,
                        weight_std=weight_std,
                        gradient_norm=grad_norm,
                        activation_entropy=entropy,
                    )
                    
                    total_embedding_var += param.data.var().item()
                    layer_count += 1
            
            avg_embedding_var = total_embedding_var / layer_count if layer_count > 0 else 0
            
            return CheckpointProfile(
                checkpoint_id=checkpoint_id,
                timestamp=datetime.now().isoformat(),
                layer_profiles=layer_profiles,
                embedding_variance=avg_embedding_var,
            )
        
        except ImportError:
            return self._unavailable_profile(checkpoint_id)
    
    def _unavailable_profile(self, checkpoint_id: str) -> CheckpointProfile:
        """Return profile when PyTorch is unavailable. No fake layer data."""
        return CheckpointProfile(
            checkpoint_id=checkpoint_id,
            timestamp=datetime.now().isoformat(),
            layer_profiles={},
            embedding_variance=0.0,
            is_suspicious=True,
            suspicious_reason="pytorch_unavailable",
        )
    
    def set_baseline(self, profile: CheckpointProfile) -> None:
        """Set baseline profile."""
        self.baseline = profile
        self._update_rolling_means(profile)
    
    def _update_rolling_means(self, profile: CheckpointProfile) -> None:
        """Update rolling means."""
        for name, layer in profile.layer_profiles.items():
            if name not in self.rolling_means:
                self.rolling_means[name] = {
                    "weight_mean": layer.weight_mean,
                    "weight_std": layer.weight_std,
                    "gradient_norm": layer.gradient_norm,
                }
            else:
                # Exponential moving average
                alpha = 0.1
                for key in ["weight_mean", "weight_std", "gradient_norm"]:
                    old = self.rolling_means[name][key]
                    new = getattr(layer, key)
                    self.rolling_means[name][key] = alpha * new + (1 - alpha) * old
    
    def check_integrity(self, profile: CheckpointProfile) -> Tuple[bool, str]:
        """
        Check if profile shows suspicious deviation.
        
        Returns:
            Tuple of (is_valid, reason)
        """
        if not self.rolling_means:
            self._update_rolling_means(profile)
            self.history.append(profile)
            return True, "No baseline yet"
        
        deviations = []
        
        for name, layer in profile.layer_profiles.items():
            if name not in self.rolling_means:
                continue
            
            baseline = self.rolling_means[name]
            
            # Check weight std deviation
            if baseline["weight_std"] > 0:
                std_deviation = abs(layer.weight_std - baseline["weight_std"]) / baseline["weight_std"]
                if std_deviation > self.DEVIATION_THRESHOLD:
                    deviations.append(f"{name}: weight_std deviation {std_deviation:.2%}")
            
            # Check gradient norm deviation
            if baseline["gradient_norm"] > 0:
                grad_deviation = abs(layer.gradient_norm - baseline["gradient_norm"]) / baseline["gradient_norm"]
                if grad_deviation > self.DEVIATION_THRESHOLD:
                    deviations.append(f"{name}: gradient_norm deviation {grad_deviation:.2%}")
        
        self._update_rolling_means(profile)
        
        if deviations:
            profile.is_suspicious = True
            profile.suspicious_reason = "; ".join(deviations)
            self.history.append(profile)
            return False, profile.suspicious_reason
        
        self.history.append(profile)
        return True, "Profile within normal range"
    
    def has_suspicious_checkpoints(self) -> Tuple[bool, int]:
        """Check if any checkpoints are suspicious."""
        suspicious = [p for p in self.history if p.is_suspicious]
        return len(suspicious) > 0, len(suspicious)
