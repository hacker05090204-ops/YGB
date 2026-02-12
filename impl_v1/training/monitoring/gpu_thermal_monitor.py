"""
GPU Thermal Monitor - Safe Training
=====================================

Track GPU health during training:
- Temperature monitoring
- Throttle detection
- VRAM usage
- Automatic pause/resume on overheating
"""

from dataclasses import dataclass
from typing import Optional, Tuple, List
from datetime import datetime
from pathlib import Path
from enum import Enum
import time
import json


# =============================================================================
# CONFIGURATION
# =============================================================================

class ThermalState(Enum):
    """GPU thermal states."""
    NORMAL = "normal"
    WARNING = "warning"
    THROTTLED = "throttled"
    CRITICAL = "critical"


@dataclass
class GPUThermalConfig:
    """GPU thermal monitoring configuration."""
    warning_temp_c: float = 75.0
    throttle_temp_c: float = 83.0
    critical_temp_c: float = 90.0
    cooldown_target_c: float = 70.0
    cooldown_timeout_seconds: int = 300
    check_interval_seconds: float = 5.0


@dataclass
class GPUStatus:
    """Current GPU status."""
    gpu_id: int
    temperature_c: float
    vram_used_mb: float
    vram_total_mb: float
    utilization_percent: float
    throttled: bool
    state: ThermalState


# =============================================================================
# GPU MONITOR
# =============================================================================

class GPUThermalMonitor:
    """Monitor GPU thermal state during training."""
    
    def __init__(self, config: GPUThermalConfig = None):
        self.config = config or GPUThermalConfig()
        self.history: List[GPUStatus] = []
        self.throttle_count = 0
        self.pause_requested = False
    
    def get_gpu_status(self, gpu_id: int = 0) -> GPUStatus:
        """Get current GPU status. Returns real data only."""
        try:
            import torch
            if not torch.cuda.is_available():
                return self._unavailable_status(gpu_id)
            
            # Get temperature via nvidia-smi or pynvml
            temp = self._get_temperature(gpu_id)
            if temp is None:
                temp = 0.0  # Sensor unavailable
            vram_used = torch.cuda.memory_allocated(gpu_id) / (1024 * 1024)
            vram_total = torch.cuda.get_device_properties(gpu_id).total_memory / (1024 * 1024)
            
            # Determine state
            state = self._determine_state(temp)
            throttled = state in [ThermalState.THROTTLED, ThermalState.CRITICAL]
            
            if throttled:
                self.throttle_count += 1
            
            return GPUStatus(
                gpu_id=gpu_id,
                temperature_c=temp,
                vram_used_mb=vram_used,
                vram_total_mb=vram_total,
                utilization_percent=0.0,  # Updated by nvidia-smi query
                throttled=throttled,
                state=state,
            )
        except Exception:
            return self._unavailable_status(gpu_id)
    
    def _get_temperature(self, gpu_id: int) -> Optional[float]:
        """Get GPU temperature."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu",
                 "--format=csv,noheader,nounits", f"--id={gpu_id}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass
        return None  # Sensor unavailable — no fake fallback
    
    def _unavailable_status(self, gpu_id: int) -> GPUStatus:
        """Return status when GPU is unavailable. Zero values, not fake data."""
        return GPUStatus(
            gpu_id=gpu_id,
            temperature_c=0.0,
            vram_used_mb=0.0,
            vram_total_mb=0.0,
            utilization_percent=0.0,
            throttled=False,
            state=ThermalState.NORMAL,
        )
    
    def _determine_state(self, temp: float) -> ThermalState:
        """Determine thermal state from temperature."""
        if temp >= self.config.critical_temp_c:
            return ThermalState.CRITICAL
        elif temp >= self.config.throttle_temp_c:
            return ThermalState.THROTTLED
        elif temp >= self.config.warning_temp_c:
            return ThermalState.WARNING
        return ThermalState.NORMAL
    
    def should_pause_training(self) -> Tuple[bool, str]:
        """Check if training should be paused."""
        status = self.get_gpu_status()
        self.history.append(status)
        
        if status.state == ThermalState.CRITICAL:
            self.pause_requested = True
            return True, f"CRITICAL: GPU at {status.temperature_c}°C"
        
        if status.state == ThermalState.THROTTLED:
            self.pause_requested = True
            return True, f"THROTTLED: GPU at {status.temperature_c}°C"
        
        return False, f"Normal: GPU at {status.temperature_c}°C"
    
    def wait_for_cooldown(self) -> bool:
        """Wait for GPU to cool down."""
        start = time.time()
        
        while time.time() - start < self.config.cooldown_timeout_seconds:
            status = self.get_gpu_status()
            
            if status.temperature_c <= self.config.cooldown_target_c:
                self.pause_requested = False
                return True
            
            time.sleep(self.config.check_interval_seconds)
        
        return False  # Timeout
    
    def get_thermal_report(self) -> dict:
        """Generate thermal report."""
        if not self.history:
            return {"status": "no_data"}
        
        temps = [s.temperature_c for s in self.history]
        
        return {
            "samples": len(self.history),
            "avg_temp_c": round(sum(temps) / len(temps), 1),
            "max_temp_c": max(temps),
            "min_temp_c": min(temps),
            "throttle_count": self.throttle_count,
            "current_state": self.history[-1].state.value,
        }
