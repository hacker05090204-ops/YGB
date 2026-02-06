"""
Continuous Security Monitor - Phase 49
=======================================

Runtime monitoring for:
1. Memory usage spike detection
2. Unexpected syscall detection
3. Training drift alerts
4. Sandbox escape attempt logging

Logs written to: reports/security/
"""

import os
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import platform


# =============================================================================
# CONFIGURATION
# =============================================================================

REPORTS_DIR = Path("reports/security")
MEMORY_SPIKE_THRESHOLD_MB = 100  # Alert if memory increases by 100MB
DRIFT_THRESHOLD = 0.01  # 1% drift in loss
MAX_LOG_SIZE_MB = 50  # Rotate logs at 50MB


# =============================================================================
# EVENT TYPES
# =============================================================================

class SecurityEventType(Enum):
    """Types of security events."""
    MEMORY_SPIKE = "MEMORY_SPIKE"
    SYSCALL_BLOCKED = "SYSCALL_BLOCKED"
    TRAINING_DRIFT = "TRAINING_DRIFT"
    SANDBOX_ESCAPE = "SANDBOX_ESCAPE"
    CALIBRATION_FAIL = "CALIBRATION_FAIL"
    POLICY_VIOLATION = "POLICY_VIOLATION"


class Severity(Enum):
    """Event severity levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class SecurityEvent:
    """A security event."""
    timestamp: str
    event_type: SecurityEventType
    severity: Severity
    message: str
    details: Dict[str, Any]
    
    def to_log_line(self) -> str:
        """Format as log line."""
        return (
            f"[{self.timestamp}] [{self.severity.value}] "
            f"{self.event_type.value}: {self.message}"
        )


# =============================================================================
# MEMORY MONITOR
# =============================================================================

def get_memory_usage_mb() -> float:
    """Get current process memory usage in MB."""
    try:
        if platform.system() == "Windows":
            import ctypes
            from ctypes import wintypes
            
            kernel32 = ctypes.windll.kernel32
            
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]
            
            psapi = ctypes.windll.psapi
            pmc = PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(pmc)
            
            handle = kernel32.GetCurrentProcess()
            if psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), ctypes.sizeof(pmc)):
                return pmc.WorkingSetSize / (1024 * 1024)
        else:
            # Linux: read from /proc/self/status
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        kb = int(line.split()[1])
                        return kb / 1024
    except Exception:
        pass
    return 0.0


class MemoryMonitor:
    """Monitor memory usage spikes."""
    
    def __init__(self, threshold_mb: float = MEMORY_SPIKE_THRESHOLD_MB):
        self.threshold = threshold_mb
        self.baseline: Optional[float] = None
        self.last_check: Optional[float] = None
    
    def check(self) -> Optional[SecurityEvent]:
        """Check for memory spikes."""
        current = get_memory_usage_mb()
        
        if self.baseline is None:
            self.baseline = current
            self.last_check = current
            return None
        
        delta = current - self.last_check
        self.last_check = current
        
        if delta > self.threshold:
            return SecurityEvent(
                timestamp=datetime.now().isoformat(),
                event_type=SecurityEventType.MEMORY_SPIKE,
                severity=Severity.WARNING,
                message=f"Memory increased by {delta:.1f}MB",
                details={
                    "current_mb": current,
                    "delta_mb": delta,
                    "baseline_mb": self.baseline,
                },
            )
        
        return None


# =============================================================================
# TRAINING DRIFT MONITOR
# =============================================================================

class DriftMonitor:
    """Monitor training for unexpected drift."""
    
    def __init__(self, threshold: float = DRIFT_THRESHOLD):
        self.threshold = threshold
        self.loss_history: List[float] = []
        self.expected_loss: Optional[float] = None
    
    def record_loss(self, loss: float) -> Optional[SecurityEvent]:
        """Record loss and check for drift."""
        self.loss_history.append(loss)
        
        if len(self.loss_history) < 5:
            return None
        
        # Check if loss is increasing unexpectedly
        recent = self.loss_history[-5:]
        if len(recent) >= 5:
            trend = recent[-1] - recent[0]
            if trend > self.threshold:
                return SecurityEvent(
                    timestamp=datetime.now().isoformat(),
                    event_type=SecurityEventType.TRAINING_DRIFT,
                    severity=Severity.WARNING,
                    message=f"Loss increasing: {trend:.4f}",
                    details={
                        "recent_losses": recent,
                        "trend": trend,
                    },
                )
        
        return None


# =============================================================================
# SECURITY LOGGER
# =============================================================================

class SecurityLogger:
    """Log security events to file."""
    
    def __init__(self, log_dir: Path = REPORTS_DIR):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "security_events.log"
        self._event_count = 0
    
    def log(self, event: SecurityEvent) -> None:
        """Log a security event."""
        self._maybe_rotate()
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(event.to_log_line() + "\n")
            
            # Write details for critical events
            if event.severity == Severity.CRITICAL:
                for key, value in event.details.items():
                    f.write(f"    {key}: {value}\n")
        
        self._event_count += 1
    
    def _maybe_rotate(self) -> None:
        """Rotate log if too large."""
        if self.log_file.exists():
            size_mb = self.log_file.stat().st_size / (1024 * 1024)
            if size_mb > MAX_LOG_SIZE_MB:
                # Rename with timestamp
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                archive = self.log_dir / f"security_events_{ts}.log"
                self.log_file.rename(archive)
    
    def get_event_count(self) -> int:
        """Get number of events logged."""
        return self._event_count


# =============================================================================
# SANDBOX ESCAPE DETECTION
# =============================================================================

def detect_sandbox_escape_attempt(syscall: str) -> SecurityEvent:
    """Create event for sandbox escape attempt."""
    return SecurityEvent(
        timestamp=datetime.now().isoformat(),
        event_type=SecurityEventType.SANDBOX_ESCAPE,
        severity=Severity.CRITICAL,
        message=f"Sandbox escape attempt: {syscall}",
        details={
            "syscall": syscall,
            "action": "BLOCKED",
        },
    )


# =============================================================================
# COMBINED MONITOR
# =============================================================================

class SecurityMonitor:
    """Combined security monitor."""
    
    def __init__(self):
        self.memory = MemoryMonitor()
        self.drift = DriftMonitor()
        self.logger = SecurityLogger()
    
    def check_all(self, loss: Optional[float] = None) -> List[SecurityEvent]:
        """Run all monitors and log events."""
        events = []
        
        # Memory check
        mem_event = self.memory.check()
        if mem_event:
            self.logger.log(mem_event)
            events.append(mem_event)
        
        # Drift check
        if loss is not None:
            drift_event = self.drift.record_loss(loss)
            if drift_event:
                self.logger.log(drift_event)
                events.append(drift_event)
        
        return events
    
    def log_sandbox_attempt(self, syscall: str) -> None:
        """Log a sandbox escape attempt."""
        event = detect_sandbox_escape_attempt(syscall)
        self.logger.log(event)
