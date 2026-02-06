"""
Resource Partitioning (C++ Specification)
==========================================

GPU scheduler:
- Max GPU utilization cap (70%)
- Gradient accumulation throttling
- Dynamic batch resizing

CPU:
- nice(10) for training
- Inference always priority
"""

from dataclasses import dataclass
from typing import Tuple
from datetime import datetime
from pathlib import Path
import json


# =============================================================================
# RESOURCE LIMITS
# =============================================================================

@dataclass
class ResourceLimits:
    """Resource limit configuration."""
    max_gpu_utilization: float = 0.70  # 70%
    max_gpu_memory_fraction: float = 0.80
    training_nice_value: int = 10  # Lower priority
    inference_nice_value: int = 0  # Highest priority
    max_batch_size: int = 64
    min_batch_size: int = 8
    gradient_accumulation_steps: int = 4


# =============================================================================
# GPU SCHEDULER (C++ Specification)
# =============================================================================

class GPUScheduler:
    """
    GPU resource scheduler.
    
    NOTE: This is a Python specification for the C++ fast path.
    Actual GPU scheduling happens in C++.
    """
    
    CONFIG_FILE = Path("impl_v1/enterprise/GPU_SCHEDULER_CONFIG.json")
    
    def __init__(self, limits: ResourceLimits = None):
        self.limits = limits or ResourceLimits()
        self.current_utilization = 0.0
        self.current_batch_size = self.limits.max_batch_size
        self._generate_config()
    
    def _generate_config(self) -> None:
        """Generate config file for C++ engine."""
        self.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.CONFIG_FILE, "w") as f:
            json.dump({
                "max_gpu_utilization": self.limits.max_gpu_utilization,
                "max_gpu_memory_fraction": self.limits.max_gpu_memory_fraction,
                "gradient_accumulation_steps": self.limits.gradient_accumulation_steps,
                "batch_size": {
                    "initial": self.limits.max_batch_size,
                    "min": self.limits.min_batch_size,
                    "max": self.limits.max_batch_size,
                },
                "priority": {
                    "training_nice": self.limits.training_nice_value,
                    "inference_nice": self.limits.inference_nice_value,
                },
            }, f, indent=2)
    
    def throttle_training(self, current_utilization: float) -> Tuple[int, int]:
        """
        Throttle training based on current utilization.
        
        Returns:
            Tuple of (new_batch_size, accumulation_steps)
        """
        self.current_utilization = current_utilization
        
        if current_utilization > self.limits.max_gpu_utilization:
            # Reduce batch size
            new_batch = max(
                self.limits.min_batch_size,
                int(self.current_batch_size * 0.75)
            )
            # Increase accumulation
            new_accum = min(16, self.limits.gradient_accumulation_steps + 2)
            
            self.current_batch_size = new_batch
            return new_batch, new_accum
        
        return self.current_batch_size, self.limits.gradient_accumulation_steps
    
    def get_inference_priority(self) -> dict:
        """Get inference priority settings."""
        return {
            "nice_value": self.limits.inference_nice_value,
            "gpu_priority": "high",
            "preempt_training": True,
        }


# =============================================================================
# PERFORMANCE GUARD
# =============================================================================

class PerformanceGuard:
    """
    Guard inference performance.
    
    Auto-throttle training if:
    - Inference latency > 20% baseline
    - Memory > threshold
    - GPU thermal > 83°C
    """
    
    STATE_FILE = Path("reports/performance_guard.json")
    
    def __init__(self):
        self.baseline_latency_ms = 100.0
        self.memory_threshold_mb = 8000
        self.thermal_threshold_c = 83
        self.training_throttled = False
    
    def check_and_throttle(
        self,
        current_latency_ms: float,
        current_memory_mb: float,
        current_temp_c: float,
    ) -> Tuple[bool, str]:
        """
        Check metrics and throttle training if needed.
        
        Returns:
            Tuple of (should_throttle, reason)
        """
        reasons = []
        
        # Latency check (20% above baseline)
        latency_limit = self.baseline_latency_ms * 1.20
        if current_latency_ms > latency_limit:
            reasons.append(f"Latency {current_latency_ms:.1f}ms > {latency_limit:.1f}ms")
        
        # Memory check
        if current_memory_mb > self.memory_threshold_mb:
            reasons.append(f"Memory {current_memory_mb:.0f}MB > {self.memory_threshold_mb}MB")
        
        # Thermal check
        if current_temp_c > self.thermal_threshold_c:
            reasons.append(f"Temp {current_temp_c:.1f}°C > {self.thermal_threshold_c}°C")
        
        should_throttle = len(reasons) > 0
        
        if should_throttle:
            self.training_throttled = True
            self._log_event("throttle", reasons)
        
        return should_throttle, "; ".join(reasons) if reasons else "OK"
    
    def _log_event(self, event_type: str, reasons: list) -> None:
        """Log performance event."""
        self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.STATE_FILE, "a") as f:
            f.write(json.dumps({
                "event": event_type,
                "reasons": reasons,
                "timestamp": datetime.now().isoformat(),
            }) + "\n")
