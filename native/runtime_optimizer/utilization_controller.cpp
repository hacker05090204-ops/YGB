// ============================================================
// UTILIZATION CONTROLLER — GPU/CPU Utilization Management
// ============================================================
// Rules:
//   - Target GPU utilization 85–92%
//   - Monitor CPU alongside GPU
//   - Per-field resource tracking
//   - Training velocity computation
//   - NO mock data — "Awaiting Data" if unavailable
// ============================================================

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


// ============================================================
// CONSTANTS
// ============================================================
static constexpr double GPU_TARGET_MIN = 0.85;
static constexpr double GPU_TARGET_MAX = 0.92;
static constexpr double CPU_WARNING = 0.95;
static constexpr uint32_t HISTORY_LEN = 60; // 60 samples
static constexpr uint32_t MAX_GPUS = 8;

// ============================================================
// GPU DEVICE STATE
// ============================================================
struct DeviceState {
  char name[64];      // e.g. "RTX 3050"
  double utilization; // 0.0–1.0
  double temperature; // °C
  uint64_t memory_used_mb;
  uint64_t memory_total_mb;
  double power_watts;
  bool available;
  bool has_data; // false = show "Awaiting Data"
};

// ============================================================
// SYSTEM UTILIZATION SNAPSHOT
// ============================================================
struct SystemUtilization {
  DeviceState gpus[MAX_GPUS];
  uint32_t gpu_count;
  double cpu_utilization; // 0.0–1.0
  bool cpu_has_data;
  uint64_t timestamp;
};

// ============================================================
// TRAINING VELOCITY
// ============================================================
struct VelocityMetrics {
  double samples_per_hour;
  double batches_per_second;
  uint32_t epochs_completed;
  double epoch_duration_seconds;
  bool has_data;
  char summary[128];
};

// ============================================================
// UTILIZATION REPORT
// ============================================================
struct UtilizationReport {
  double avg_gpu_util;
  double max_gpu_temp;
  double avg_cpu_util;
  bool gpu_in_target; // within 85–92%
  bool cpu_warning;   // >95%
  uint32_t active_gpus;
  uint32_t total_gpus;
  char status[256];
};

// ============================================================
// UTILIZATION CONTROLLER
// ============================================================
class UtilizationController {
public:
  UtilizationController() {
    std::memset(&current_, 0, sizeof(current_));
    std::memset(&velocity_, 0, sizeof(velocity_));
    sample_count_ = 0;
  }

  // --------------------------------------------------------
  // UPDATE — push new utilization sample
  // --------------------------------------------------------
  void update(const SystemUtilization &snap) {
    current_ = snap;
    sample_count_++;

    // Store in history ring buffer
    history_[history_idx_] = snap;
    history_idx_ = (history_idx_ + 1) % HISTORY_LEN;
    if (history_len_ < HISTORY_LEN)
      history_len_++;
  }

  // --------------------------------------------------------
  // REPORT — generate utilization report
  // --------------------------------------------------------
  UtilizationReport report() const {
    UtilizationReport r;
    std::memset(&r, 0, sizeof(r));

    if (sample_count_ == 0) {
      std::snprintf(r.status, sizeof(r.status),
                    "AWAITING_DATA: no utilization samples received");
      return r;
    }

    double gpu_sum = 0.0;
    double max_temp = 0.0;
    uint32_t active = 0;

    for (uint32_t i = 0; i < current_.gpu_count && i < MAX_GPUS; ++i) {
      const DeviceState &d = current_.gpus[i];
      if (!d.available || !d.has_data)
        continue;

      gpu_sum += d.utilization;
      if (d.temperature > max_temp)
        max_temp = d.temperature;
      active++;
    }

    r.total_gpus = current_.gpu_count;
    r.active_gpus = active;

    if (active > 0) {
      r.avg_gpu_util = gpu_sum / static_cast<double>(active);
    }
    r.max_gpu_temp = max_temp;
    r.avg_cpu_util = current_.cpu_has_data ? current_.cpu_utilization : 0.0;

    r.gpu_in_target =
        (r.avg_gpu_util >= GPU_TARGET_MIN && r.avg_gpu_util <= GPU_TARGET_MAX);
    r.cpu_warning =
        (current_.cpu_has_data && current_.cpu_utilization >= CPU_WARNING);

    // Status string
    if (!current_.gpus[0].has_data && active == 0) {
      std::snprintf(r.status, sizeof(r.status),
                    "AWAITING_DATA: GPU metrics not yet available");
    } else if (r.gpu_in_target) {
      std::snprintf(r.status, sizeof(r.status),
                    "OPTIMAL: GPU %.0f%% [target %.0f–%.0f%%] | "
                    "CPU %.0f%% | %u/%u GPUs active | "
                    "maxTemp %.0f°C",
                    r.avg_gpu_util * 100.0, GPU_TARGET_MIN * 100.0,
                    GPU_TARGET_MAX * 100.0, r.avg_cpu_util * 100.0,
                    r.active_gpus, r.total_gpus, r.max_gpu_temp);
    } else {
      std::snprintf(r.status, sizeof(r.status),
                    "ADJUST: GPU %.0f%% [target %.0f–%.0f%%] | "
                    "CPU %.0f%% | %u/%u GPUs | "
                    "maxTemp %.0f°C",
                    r.avg_gpu_util * 100.0, GPU_TARGET_MIN * 100.0,
                    GPU_TARGET_MAX * 100.0, r.avg_cpu_util * 100.0,
                    r.active_gpus, r.total_gpus, r.max_gpu_temp);
    }

    return r;
  }

  // --------------------------------------------------------
  // VELOCITY — compute training speed
  // --------------------------------------------------------
  void update_velocity(double samples_per_hour, double batches_per_sec,
                       uint32_t epochs, double epoch_duration) {
    velocity_.samples_per_hour = samples_per_hour;
    velocity_.batches_per_second = batches_per_sec;
    velocity_.epochs_completed = epochs;
    velocity_.epoch_duration_seconds = epoch_duration;
    velocity_.has_data = (samples_per_hour > 0.0);

    if (velocity_.has_data) {
      std::snprintf(velocity_.summary, sizeof(velocity_.summary),
                    "VELOCITY: %.0f samples/hr | %.1f batch/s | "
                    "%u epochs | %.0fs/epoch",
                    samples_per_hour, batches_per_sec, epochs, epoch_duration);
    } else {
      std::snprintf(velocity_.summary, sizeof(velocity_.summary),
                    "AWAITING_DATA: no training velocity data");
    }
  }

  const VelocityMetrics &velocity() const { return velocity_; }
  uint32_t sample_count() const { return sample_count_; }

private:
  SystemUtilization current_;
  SystemUtilization history_[HISTORY_LEN];
  uint32_t history_idx_ = 0;
  uint32_t history_len_ = 0;
  VelocityMetrics velocity_;
  uint32_t sample_count_;
};
