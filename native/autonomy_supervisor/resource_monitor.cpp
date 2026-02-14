/**
 * Resource Monitor — GPU & System Resource Integrity Tracker
 *
 * Monitors:
 *   1) GPU temperature (score degrades above 80°C, critical at 90°C)
 *   2) GPU throttle event counter
 *   3) HDD free space percentage (penalty below 15%)
 *   4) I/O latency (running average, alert on spikes)
 *   5) Memory pressure
 *
 * Computes a resource_integrity_score (0–100).
 * No silent failure. Every metric update is tracked.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <ctime>
#include <deque>
#include <vector>

// ============================================================================
// Resource Stats
// ============================================================================

struct ResourceStats {
  double gpu_temp_c;          // Current GPU temperature in Celsius
  int gpu_throttle_events;    // Total throttle events observed
  double hdd_free_percent;    // HDD free space percentage
  double io_latency_ms;       // Average I/O latency in milliseconds
  double memory_used_percent; // Memory usage percentage
  double resource_score;      // Combined score (0–100)
  bool gpu_temp_alert;        // GPU temp > 80°C
  bool gpu_throttle_alert;    // Any throttle events
  bool hdd_alert;             // Free space < 15%
  bool io_latency_alert;      // Latency > 50ms rolling average
  bool memory_alert;          // Memory > 90%
  bool any_alert;             // Any alert active
};

// ============================================================================
// I/O Latency Sample
// ============================================================================

struct IOLatencySample {
  double latency_ms;
  double timestamp;
};

// ============================================================================
// Resource Monitor
// ============================================================================

class ResourceMonitor {
private:
  // Thresholds
  static constexpr double GPU_TEMP_WARN = 80.0;  // °C
  static constexpr double GPU_TEMP_CRIT = 90.0;  // °C
  static constexpr double GPU_TEMP_MAX = 100.0;  // °C
  static constexpr double HDD_FREE_MIN = 15.0;   // %
  static constexpr double IO_LATENCY_MAX = 50.0; // ms
  static constexpr double MEMORY_MAX = 90.0;     // %
  static constexpr int IO_WINDOW_SIZE = 100;

  // GPU state
  double gpu_temp_;
  int gpu_throttle_events_;

  // HDD state
  double hdd_free_percent_;

  // I/O latency tracking
  std::deque<IOLatencySample> io_window_;
  double io_sum_;

  // Memory
  double memory_used_percent_;

  // Score weights (within resource sub-score)
  static constexpr double W_GPU_TEMP = 0.30;
  static constexpr double W_GPU_THROT = 0.15;
  static constexpr double W_HDD_FREE = 0.25;
  static constexpr double W_IO_LAT = 0.15;
  static constexpr double W_MEMORY = 0.15;

  double compute_gpu_temp_score() const {
    if (gpu_temp_ <= GPU_TEMP_WARN)
      return 100.0;
    if (gpu_temp_ >= GPU_TEMP_MAX)
      return 0.0;
    // Linear degradation from 100 at 80°C to 0 at 100°C
    return 100.0 * (GPU_TEMP_MAX - gpu_temp_) / (GPU_TEMP_MAX - GPU_TEMP_WARN);
  }

  double compute_gpu_throttle_score() const {
    if (gpu_throttle_events_ == 0)
      return 100.0;
    if (gpu_throttle_events_ >= 10)
      return 0.0;
    // Each event drops 10 points
    return std::max(0.0, 100.0 - gpu_throttle_events_ * 10.0);
  }

  double compute_hdd_score() const {
    if (hdd_free_percent_ >= HDD_FREE_MIN)
      return 100.0;
    if (hdd_free_percent_ <= 1.0)
      return 0.0;
    // Linear degradation from 100 at 15% to 0 at 1%
    return 100.0 * (hdd_free_percent_ - 1.0) / (HDD_FREE_MIN - 1.0);
  }

  double compute_io_score() const {
    double avg = get_avg_io_latency();
    if (avg <= 5.0)
      return 100.0; // Excellent
    if (avg >= IO_LATENCY_MAX)
      return 0.0;
    // Linear degradation from 100 at 5ms to 0 at 50ms
    return 100.0 * (IO_LATENCY_MAX - avg) / (IO_LATENCY_MAX - 5.0);
  }

  double compute_memory_score() const {
    if (memory_used_percent_ <= 70.0)
      return 100.0;
    if (memory_used_percent_ >= 99.0)
      return 0.0;
    return 100.0 * (99.0 - memory_used_percent_) / (99.0 - 70.0);
  }

  double get_avg_io_latency() const {
    if (io_window_.empty())
      return 0.0;
    return io_sum_ / io_window_.size();
  }

public:
  ResourceMonitor()
      : gpu_temp_(0.0), gpu_throttle_events_(0), hdd_free_percent_(100.0),
        io_sum_(0.0), memory_used_percent_(0.0) {}

  // -------------------------------------------------------------------
  // Update Methods (called by system probes)
  // -------------------------------------------------------------------

  void update_gpu_temp(double temp_c) { gpu_temp_ = temp_c; }

  void record_gpu_throttle() { gpu_throttle_events_++; }

  void update_hdd_free(double free_percent) {
    hdd_free_percent_ = free_percent;
  }

  void record_io_latency(double latency_ms) {
    IOLatencySample sample;
    sample.latency_ms = latency_ms;
    sample.timestamp = static_cast<double>(std::time(nullptr));

    io_sum_ += latency_ms;
    io_window_.push_back(sample);

    if (static_cast<int>(io_window_.size()) > IO_WINDOW_SIZE) {
      io_sum_ -= io_window_.front().latency_ms;
      io_window_.pop_front();
    }
  }

  void update_memory_used(double percent) { memory_used_percent_ = percent; }

  void reset_throttle_counter() { gpu_throttle_events_ = 0; }

  // -------------------------------------------------------------------
  // Score Computation
  // -------------------------------------------------------------------

  double compute_resource_score() const {
    double score = compute_gpu_temp_score() * W_GPU_TEMP +
                   compute_gpu_throttle_score() * W_GPU_THROT +
                   compute_hdd_score() * W_HDD_FREE +
                   compute_io_score() * W_IO_LAT +
                   compute_memory_score() * W_MEMORY;
    return std::max(0.0, std::min(100.0, score));
  }

  ResourceStats get_stats() const {
    ResourceStats stats;
    stats.gpu_temp_c = gpu_temp_;
    stats.gpu_throttle_events = gpu_throttle_events_;
    stats.hdd_free_percent = hdd_free_percent_;
    stats.io_latency_ms = get_avg_io_latency();
    stats.memory_used_percent = memory_used_percent_;
    stats.resource_score = compute_resource_score();

    stats.gpu_temp_alert = (gpu_temp_ > GPU_TEMP_WARN);
    stats.gpu_throttle_alert = (gpu_throttle_events_ > 0);
    stats.hdd_alert = (hdd_free_percent_ < HDD_FREE_MIN);
    stats.io_latency_alert = (get_avg_io_latency() > IO_LATENCY_MAX);
    stats.memory_alert = (memory_used_percent_ > MEMORY_MAX);

    stats.any_alert = stats.gpu_temp_alert || stats.gpu_throttle_alert ||
                      stats.hdd_alert || stats.io_latency_alert ||
                      stats.memory_alert;
    return stats;
  }

  // -------------------------------------------------------------------
  // Accessors
  // -------------------------------------------------------------------

  double gpu_temp() const { return gpu_temp_; }
  int throttle_events() const { return gpu_throttle_events_; }
  double hdd_free() const { return hdd_free_percent_; }
  double avg_io_latency() const { return get_avg_io_latency(); }
  double memory_used() const { return memory_used_percent_; }
  int io_window_size() const { return static_cast<int>(io_window_.size()); }
};
