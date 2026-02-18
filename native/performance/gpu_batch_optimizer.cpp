/**
 * gpu_batch_optimizer.cpp — GPU Batch Size Optimizer
 *
 * Auto-scales batch size to achieve 75–85% GPU utilization.
 * Adapts per device: RTX 3050 (4GB), RTX 2050 (4GB), M1 (8GB shared).
 *
 * NO cross-field contamination. NO authority unlock.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace performance {

// =========================================================================
// GPU DEVICE PROFILE
// =========================================================================

struct GpuDeviceProfile {
  char name[64];
  uint32_t vram_mb;
  uint32_t cuda_cores;
  double clock_ghz;
  double target_utilization_min; // 0.75
  double target_utilization_max; // 0.85
  uint32_t max_batch_size;
  uint32_t min_batch_size;
};

static GpuDeviceProfile make_rtx3050() {
  GpuDeviceProfile p;
  std::strncpy(p.name, "RTX_3050", 63);
  p.vram_mb = 4096;
  p.cuda_cores = 2560;
  p.clock_ghz = 1.78;
  p.target_utilization_min = 0.75;
  p.target_utilization_max = 0.85;
  p.max_batch_size = 128;
  p.min_batch_size = 8;
  return p;
}

static GpuDeviceProfile make_rtx2050() {
  GpuDeviceProfile p;
  std::strncpy(p.name, "RTX_2050", 63);
  p.vram_mb = 4096;
  p.cuda_cores = 2048;
  p.clock_ghz = 1.48;
  p.target_utilization_min = 0.75;
  p.target_utilization_max = 0.85;
  p.max_batch_size = 96;
  p.min_batch_size = 8;
  return p;
}

// =========================================================================
// BATCH OPTIMIZATION RESULT
// =========================================================================

struct BatchOptResult {
  uint32_t recommended_batch;
  double estimated_utilization;
  double estimated_vram_mb;
  bool vram_constrained;
  bool within_target;
  char reason[256];
};

// =========================================================================
// GPU BATCH OPTIMIZER
// =========================================================================

class GpuBatchOptimizer {
public:
  static constexpr double THERMAL_THROTTLE_C = 83.0;
  static constexpr double UTILIZATION_MIN = 0.75;
  static constexpr double UTILIZATION_MAX = 0.85;

  BatchOptResult optimize(const GpuDeviceProfile &dev,
                          double current_utilization, uint32_t current_batch,
                          double current_vram_mb, double gpu_temp_c) {
    BatchOptResult r;
    std::memset(&r, 0, sizeof(r));

    // Thermal throttle
    if (gpu_temp_c >= THERMAL_THROTTLE_C) {
      r.recommended_batch = current_batch > dev.min_batch_size
                                ? current_batch / 2
                                : dev.min_batch_size;
      r.estimated_utilization = current_utilization * 0.5;
      r.vram_constrained = false;
      r.within_target = false;
      std::snprintf(r.reason, sizeof(r.reason),
                    "THERMAL_THROTTLE: %.1fC >= %.1fC, batch %u->%u",
                    gpu_temp_c, THERMAL_THROTTLE_C, current_batch,
                    r.recommended_batch);
      return r;
    }

    // Scale batch to hit utilization target
    if (current_utilization < UTILIZATION_MIN) {
      // Under-utilized: increase batch
      double scale = UTILIZATION_MIN / std::max(current_utilization, 0.01);
      uint32_t new_batch = static_cast<uint32_t>(current_batch * scale);
      if (new_batch > dev.max_batch_size)
        new_batch = dev.max_batch_size;

      // VRAM check
      double est_vram = current_vram_mb * (double)new_batch / current_batch;
      if (est_vram > dev.vram_mb * 0.90) {
        new_batch = static_cast<uint32_t>(
            current_batch * (dev.vram_mb * 0.90 / current_vram_mb));
        r.vram_constrained = true;
      }

      r.recommended_batch = new_batch;
      r.estimated_utilization =
          current_utilization * (double)new_batch / current_batch;
      r.estimated_vram_mb = current_vram_mb * (double)new_batch / current_batch;
      r.within_target = (r.estimated_utilization >= UTILIZATION_MIN &&
                         r.estimated_utilization <= UTILIZATION_MAX);
      std::snprintf(r.reason, sizeof(r.reason),
                    "SCALE_UP: util %.0f%%<75%%, batch %u->%u",
                    current_utilization * 100, current_batch, new_batch);
    } else if (current_utilization > UTILIZATION_MAX) {
      // Over-utilized: decrease batch
      double scale = UTILIZATION_MAX / current_utilization;
      uint32_t new_batch = static_cast<uint32_t>(current_batch * scale);
      if (new_batch < dev.min_batch_size)
        new_batch = dev.min_batch_size;

      r.recommended_batch = new_batch;
      r.estimated_utilization =
          current_utilization * (double)new_batch / current_batch;
      r.estimated_vram_mb = current_vram_mb * (double)new_batch / current_batch;
      r.within_target = true;
      std::snprintf(r.reason, sizeof(r.reason),
                    "SCALE_DOWN: util %.0f%%>85%%, batch %u->%u",
                    current_utilization * 100, current_batch, new_batch);
    } else {
      r.recommended_batch = current_batch;
      r.estimated_utilization = current_utilization;
      r.estimated_vram_mb = current_vram_mb;
      r.within_target = true;
      std::snprintf(r.reason, sizeof(r.reason),
                    "OPTIMAL: util %.0f%% in [75%%,85%%]",
                    current_utilization * 100);
    }

    return r;
  }
};

} // namespace performance
