/**
 * async_prefetch_engine.cpp — Asynchronous Data Prefetching
 *
 * Optimizes data pipeline: workers >= CPU_cores/2, prefetch_factor=4,
 * pin_memory=true, persistent_workers=true, async disk I/O.
 *
 * NO cross-field contamination. Single-field data only.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace performance {

// =========================================================================
// PREFETCH CONFIG
// =========================================================================

struct PrefetchConfig {
  uint32_t num_workers;     // >= CPU_cores / 2
  uint32_t prefetch_factor; // default: 4
  bool pin_memory;          // default: true
  bool persistent_workers;  // default: true
  uint32_t io_queue_depth;  // default: 8
  uint32_t buffer_pool_mb;  // default: 512
};

static PrefetchConfig auto_config(uint32_t cpu_cores, uint32_t ram_mb) {
  PrefetchConfig c;
  c.num_workers = (cpu_cores > 2) ? cpu_cores / 2 : 1;
  c.prefetch_factor = 4;
  c.pin_memory = true;
  c.persistent_workers = true;
  c.io_queue_depth = 8;
  c.buffer_pool_mb = (ram_mb > 4096) ? 512 : 256;
  return c;
}

// =========================================================================
// PIPELINE METRICS
// =========================================================================

struct PipelineMetrics {
  double samples_per_second;
  double io_wait_ms;
  double cpu_utilization;
  double gpu_stall_ratio; // time GPU waits for data
  uint32_t batches_prefetched;
  uint32_t io_errors;
  bool bottleneck_io;
  bool bottleneck_cpu;
};

// =========================================================================
// ASYNC PREFETCH ENGINE
// =========================================================================

class AsyncPrefetchEngine {
public:
  static constexpr double MAX_GPU_STALL_RATIO = 0.05; // GPU idle <5%
  static constexpr double MAX_IO_WAIT_MS = 50.0;

  explicit AsyncPrefetchEngine(PrefetchConfig config)
      : config_(config), total_batches_(0), total_stalls_(0) {}

  // Evaluate pipeline health and recommend adjustments
  PipelineMetrics evaluate(double io_wait_ms, double cpu_util,
                           double gpu_stall_pct, uint32_t batches) {
    PipelineMetrics m;
    std::memset(&m, 0, sizeof(m));

    m.io_wait_ms = io_wait_ms;
    m.cpu_utilization = cpu_util;
    m.gpu_stall_ratio = gpu_stall_pct;
    m.batches_prefetched = batches;
    m.bottleneck_io = (io_wait_ms > MAX_IO_WAIT_MS);
    m.bottleneck_cpu = (cpu_util > 0.90);

    total_batches_ += batches;
    if (gpu_stall_pct > MAX_GPU_STALL_RATIO)
      ++total_stalls_;

    return m;
  }

  // Recommend worker count adjustment
  uint32_t recommend_workers(double cpu_util, double io_wait_ms) const {
    if (io_wait_ms > MAX_IO_WAIT_MS && cpu_util < 0.80) {
      // IO bottleneck with CPU headroom: add workers
      return config_.num_workers + 2;
    }
    if (cpu_util > 0.90) {
      // CPU saturated: reduce workers
      return (config_.num_workers > 2) ? config_.num_workers - 1 : 1;
    }
    return config_.num_workers; // optimal
  }

  const PrefetchConfig &config() const { return config_; }
  uint64_t total_batches() const { return total_batches_; }

private:
  PrefetchConfig config_;
  uint64_t total_batches_;
  uint32_t total_stalls_;
};

} // namespace performance
