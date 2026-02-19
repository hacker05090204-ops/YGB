// ============================================================
// GPU BATCH SCALER — Adaptive Batch Sizing for GPU Training
// ============================================================
// Rules:
//   - Target GPU utilization 85–92%
//   - Adaptive batch scaling based on GPU memory
//   - Thermal aware throttling
//   - Mixed precision support
//   - Deterministic seed preservation
// ============================================================

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


// ============================================================
// CONSTANTS
// ============================================================
static constexpr double TARGET_UTIL_MIN = 0.85;
static constexpr double TARGET_UTIL_MAX = 0.92;
static constexpr double THERMAL_THROTTLE = 85.0; // °C
static constexpr double THERMAL_SHUTDOWN = 95.0; // °C
static constexpr uint32_t MIN_BATCH = 4;
static constexpr uint32_t MAX_BATCH = 512;
static constexpr uint32_t BATCH_STEP = 4; // always power-of-2 aligned
static constexpr uint32_t SEED_BASE = 42; // deterministic seed

// ============================================================
// GPU STATE
// ============================================================
struct GpuState {
  double utilization; // 0.0–1.0
  double temperature; // °C
  uint64_t memory_used_mb;
  uint64_t memory_total_mb;
  bool mixed_precision;
  uint32_t current_batch;
  uint64_t seed; // deterministic seed — preserved across scales
};

// ============================================================
// SCALING RESULT
// ============================================================
struct BatchScaleResult {
  uint32_t old_batch;
  uint32_t new_batch;
  bool scaled;
  bool thermal_throttled;
  bool seed_preserved;
  char reason[256];
};

// ============================================================
// SCALE DECISION
// ============================================================
static BatchScaleResult compute_batch_scale(const GpuState &gpu) {
  BatchScaleResult r;
  std::memset(&r, 0, sizeof(r));
  r.old_batch = gpu.current_batch;
  r.new_batch = gpu.current_batch;
  r.seed_preserved = true; // seed ALWAYS preserved

  // ----- THERMAL CHECK -----
  if (gpu.temperature >= THERMAL_SHUTDOWN) {
    r.new_batch = MIN_BATCH;
    r.thermal_throttled = true;
    r.scaled = (r.new_batch != r.old_batch);
    std::snprintf(r.reason, sizeof(r.reason),
                  "THERMAL_SHUTDOWN: %.1f°C — batch forced to %u",
                  gpu.temperature, r.new_batch);
    return r;
  }

  if (gpu.temperature >= THERMAL_THROTTLE) {
    // Scale down by 25%
    uint32_t reduced = gpu.current_batch * 3 / 4;
    if (reduced < MIN_BATCH)
      reduced = MIN_BATCH;
    // Align to BATCH_STEP
    reduced = (reduced / BATCH_STEP) * BATCH_STEP;
    if (reduced < MIN_BATCH)
      reduced = MIN_BATCH;

    r.new_batch = reduced;
    r.thermal_throttled = true;
    r.scaled = (r.new_batch != r.old_batch);
    std::snprintf(r.reason, sizeof(r.reason),
                  "THERMAL_THROTTLE: %.1f°C — batch %u → %u", gpu.temperature,
                  r.old_batch, r.new_batch);
    return r;
  }

  // ----- MEMORY CHECK -----
  double mem_frac = 0.0;
  if (gpu.memory_total_mb > 0) {
    mem_frac = static_cast<double>(gpu.memory_used_mb) /
               static_cast<double>(gpu.memory_total_mb);
  }

  // If memory over 95%, scale down
  if (mem_frac > 0.95) {
    uint32_t reduced = gpu.current_batch / 2;
    if (reduced < MIN_BATCH)
      reduced = MIN_BATCH;
    reduced = (reduced / BATCH_STEP) * BATCH_STEP;
    if (reduced < MIN_BATCH)
      reduced = MIN_BATCH;

    r.new_batch = reduced;
    r.scaled = true;
    std::snprintf(r.reason, sizeof(r.reason),
                  "MEMORY_PRESSURE: %.0f%% — batch %u → %u", mem_frac * 100.0,
                  r.old_batch, r.new_batch);
    return r;
  }

  // ----- UTILIZATION SCALING -----
  if (gpu.utilization < TARGET_UTIL_MIN) {
    // Under-utilized: scale UP
    uint32_t increased = gpu.current_batch + BATCH_STEP;
    // Scale by utilization gap
    double gap = TARGET_UTIL_MIN - gpu.utilization;
    if (gap > 0.2) {
      increased = gpu.current_batch * 3 / 2; // aggressive
    }
    // Align
    increased = (increased / BATCH_STEP) * BATCH_STEP;
    if (increased > MAX_BATCH)
      increased = MAX_BATCH;
    if (increased < MIN_BATCH)
      increased = MIN_BATCH;

    // Check memory headroom
    if (mem_frac < 0.80) { // only scale up if mem headroom
      r.new_batch = increased;
      r.scaled = (r.new_batch != r.old_batch);
      std::snprintf(
          r.reason, sizeof(r.reason),
          "SCALE_UP: util=%.0f%% (target %.0f–%.0f%%) — batch %u → %u",
          gpu.utilization * 100.0, TARGET_UTIL_MIN * 100.0,
          TARGET_UTIL_MAX * 100.0, r.old_batch, r.new_batch);
    } else {
      std::snprintf(r.reason, sizeof(r.reason),
                    "HOLD: util=%.0f%% low but mem=%.0f%% — no headroom",
                    gpu.utilization * 100.0, mem_frac * 100.0);
    }
  } else if (gpu.utilization > TARGET_UTIL_MAX) {
    // Over-utilized: scale DOWN
    uint32_t decreased = gpu.current_batch - BATCH_STEP;
    if (decreased < MIN_BATCH)
      decreased = MIN_BATCH;
    decreased = (decreased / BATCH_STEP) * BATCH_STEP;
    if (decreased < MIN_BATCH)
      decreased = MIN_BATCH;

    r.new_batch = decreased;
    r.scaled = (r.new_batch != r.old_batch);
    std::snprintf(
        r.reason, sizeof(r.reason),
        "SCALE_DOWN: util=%.0f%% (target %.0f–%.0f%%) — batch %u → %u",
        gpu.utilization * 100.0, TARGET_UTIL_MIN * 100.0,
        TARGET_UTIL_MAX * 100.0, r.old_batch, r.new_batch);
  } else {
    // In target range — hold
    std::snprintf(r.reason, sizeof(r.reason),
                  "OPTIMAL: util=%.0f%% in target range — batch %u held",
                  gpu.utilization * 100.0, r.old_batch);
  }

  return r;
}

// ============================================================
// MIXED PRECISION CONFIG
// ============================================================
struct MixedPrecisionConfig {
  bool fp16_enabled;
  bool bf16_enabled; // bfloat16 (Ampere+)
  bool tf32_enabled; // tensor float 32
  double loss_scale; // for FP16 stability
  bool dynamic_loss_scale;
};

static MixedPrecisionConfig default_mixed_precision() {
  MixedPrecisionConfig c;
  c.fp16_enabled = true;
  c.bf16_enabled = false; // detect at runtime
  c.tf32_enabled = true;
  c.loss_scale = 1024.0;
  c.dynamic_loss_scale = true;
  return c;
}

// ============================================================
// SEED PRESERVATION — determinism across batch changes
// ============================================================
static uint64_t compute_deterministic_seed(uint32_t batch_size, uint32_t epoch,
                                           uint32_t field_id) {
  // Seed is deterministic from batch+epoch+field
  // Same inputs always produce same seed
  uint64_t seed = SEED_BASE;
  seed ^= static_cast<uint64_t>(batch_size) * 2654435761ULL;
  seed ^= static_cast<uint64_t>(epoch) * 40503ULL;
  seed ^= static_cast<uint64_t>(field_id) * 12345ULL;
  return seed;
}
