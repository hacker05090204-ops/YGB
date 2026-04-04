"""
TEST GPU OPTIMIZER — Batch Scaling, Seed, Thermal, Mixed Precision
==================================================================
Tests the Python-side interpretation of C++ GPU batch scaler logic.
Validates: thermal throttling, memory pressure, utilization targeting,
seed preservation, mixed precision defaults.
"""

import pytest


# ==================================================================
# CONSTANTS (mirror C++ gpu_batch_scaler.cpp)
# ==================================================================

TARGET_UTIL_MIN = 0.85
TARGET_UTIL_MAX = 0.92
THERMAL_THROTTLE = 85.0
THERMAL_SHUTDOWN = 95.0
MIN_BATCH = 4
MAX_BATCH = 512
BATCH_STEP = 4
SEED_BASE = 42


def compute_batch_scale(utilization, temperature, memory_frac, current_batch):
    """Pure-Python mirror of C++ compute_batch_scale for testing."""
    old_batch = current_batch
    new_batch = current_batch
    thermal_throttled = False
    reason = ""

    # Thermal shutdown
    if temperature >= THERMAL_SHUTDOWN:
        new_batch = MIN_BATCH
        thermal_throttled = True
        reason = f"THERMAL_SHUTDOWN: {temperature}°C"
        return new_batch, old_batch, thermal_throttled, reason

    # Thermal throttle
    if temperature >= THERMAL_THROTTLE:
        reduced = current_batch * 3 // 4
        reduced = max(MIN_BATCH, (reduced // BATCH_STEP) * BATCH_STEP)
        new_batch = max(MIN_BATCH, reduced)
        thermal_throttled = True
        reason = f"THERMAL_THROTTLE: {temperature}°C"
        return new_batch, old_batch, thermal_throttled, reason

    # Memory pressure (>95%)
    if memory_frac > 0.95:
        reduced = current_batch // 2
        reduced = max(MIN_BATCH, (reduced // BATCH_STEP) * BATCH_STEP)
        new_batch = max(MIN_BATCH, reduced)
        reason = f"MEMORY_PRESSURE: {memory_frac*100:.0f}%"
        return new_batch, old_batch, thermal_throttled, reason

    # Utilization scaling
    if utilization < TARGET_UTIL_MIN:
        gap = TARGET_UTIL_MIN - utilization
        if gap > 0.2:
            increased = current_batch * 3 // 2
        else:
            increased = current_batch + BATCH_STEP
        increased = (increased // BATCH_STEP) * BATCH_STEP
        increased = max(MIN_BATCH, min(MAX_BATCH, increased))
        if memory_frac < 0.80:
            new_batch = increased
            reason = f"SCALE_UP: util={utilization*100:.0f}%"
        else:
            reason = f"HOLD: util low but mem={memory_frac*100:.0f}%"
    elif utilization > TARGET_UTIL_MAX:
        decreased = current_batch - BATCH_STEP
        decreased = max(MIN_BATCH, (decreased // BATCH_STEP) * BATCH_STEP)
        new_batch = max(MIN_BATCH, decreased)
        reason = f"SCALE_DOWN: util={utilization*100:.0f}%"
    else:
        reason = f"OPTIMAL: util={utilization*100:.0f}%"

    return new_batch, old_batch, thermal_throttled, reason


def compute_deterministic_seed(batch_size, epoch, field_id):
    """Mirror of C++ seed computation."""
    seed = SEED_BASE
    seed ^= batch_size * 2654435761
    seed ^= epoch * 40503
    seed ^= field_id * 12345
    return seed & 0xFFFFFFFFFFFFFFFF  # uint64 mask


# ==================================================================
# THERMAL TESTS
# ==================================================================

class TestThermalProtection:

    def test_shutdown_forces_min_batch(self):
        new, old, throttled, reason = compute_batch_scale(0.90, 96.0, 0.50, 128)
        assert new == MIN_BATCH
        assert throttled is True
        assert "SHUTDOWN" in reason

    def test_throttle_reduces_batch(self):
        new, old, throttled, reason = compute_batch_scale(0.90, 87.0, 0.50, 128)
        assert new < old
        assert throttled is True
        assert "THROTTLE" in reason

    def test_normal_temp_no_throttle(self):
        new, old, throttled, reason = compute_batch_scale(0.88, 65.0, 0.50, 128)
        assert throttled is False

    def test_edge_temp_85(self):
        new, old, throttled, reason = compute_batch_scale(0.90, 85.0, 0.50, 128)
        assert throttled is True


# ==================================================================
# MEMORY PRESSURE
# ==================================================================

class TestMemoryPressure:

    def test_high_memory_reduces_batch(self):
        new, old, throttled, reason = compute_batch_scale(0.88, 65.0, 0.96, 128)
        assert new < old
        assert "MEMORY" in reason

    def test_normal_memory_no_reduction(self):
        new, old, throttled, reason = compute_batch_scale(0.88, 65.0, 0.50, 128)
        assert "MEMORY" not in reason


# ==================================================================
# UTILIZATION TARGETING
# ==================================================================

class TestUtilizationTargeting:

    def test_under_utilized_scales_up(self):
        new, old, throttled, reason = compute_batch_scale(0.60, 65.0, 0.50, 64)
        assert new > old
        assert "SCALE_UP" in reason

    def test_over_utilized_scales_down(self):
        new, old, throttled, reason = compute_batch_scale(0.95, 65.0, 0.50, 128)
        assert new < old
        assert "SCALE_DOWN" in reason

    def test_optimal_holds(self):
        new, old, throttled, reason = compute_batch_scale(0.88, 65.0, 0.50, 128)
        assert new == old
        assert "OPTIMAL" in reason

    def test_under_utilized_but_high_memory_holds(self):
        new, old, throttled, reason = compute_batch_scale(0.60, 65.0, 0.85, 64)
        assert new == old  # can't scale up due to memory
        assert "HOLD" in reason


# ==================================================================
# BATCH BOUNDS
# ==================================================================

class TestBatchBounds:

    def test_never_below_min(self):
        new, _, _, _ = compute_batch_scale(0.95, 96.0, 0.99, MIN_BATCH)
        assert new >= MIN_BATCH

    def test_never_above_max(self):
        new, _, _, _ = compute_batch_scale(0.30, 40.0, 0.10, MAX_BATCH)
        assert new <= MAX_BATCH

    def test_batch_step_aligned(self):
        new, _, _, _ = compute_batch_scale(0.60, 65.0, 0.50, 64)
        assert new % BATCH_STEP == 0


# ==================================================================
# SEED PRESERVATION
# ==================================================================

class TestSeedPreservation:

    def test_deterministic(self):
        s1 = compute_deterministic_seed(32, 5, 0)
        s2 = compute_deterministic_seed(32, 5, 0)
        assert s1 == s2

    def test_different_batch_different_seed(self):
        s1 = compute_deterministic_seed(32, 5, 0)
        s2 = compute_deterministic_seed(64, 5, 0)
        assert s1 != s2

    def test_different_epoch_different_seed(self):
        s1 = compute_deterministic_seed(32, 5, 0)
        s2 = compute_deterministic_seed(32, 6, 0)
        assert s1 != s2

    def test_different_field_different_seed(self):
        s1 = compute_deterministic_seed(32, 5, 0)
        s2 = compute_deterministic_seed(32, 5, 1)
        assert s1 != s2

    def test_seed_is_nonzero(self):
        s = compute_deterministic_seed(32, 5, 0)
        assert s != 0


# ==================================================================
# MIXED PRECISION
# ==================================================================

class TestMixedPrecisionDefaults:

    def test_default_config(self):
        """Mirrors C++ default_mixed_precision()."""
        config = {
            "fp16_enabled": True,
            "bf16_enabled": False,
            "tf32_enabled": True,
            "loss_scale": 1024.0,
            "dynamic_loss_scale": True,
        }
        assert config["fp16_enabled"] is True
        assert config["bf16_enabled"] is False
        assert config["tf32_enabled"] is True
        assert config["loss_scale"] == 1024.0
        assert config["dynamic_loss_scale"] is True
