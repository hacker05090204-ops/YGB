/**
 * resource_governor.cpp — Hunt Engine Resource Governance
 *
 * Limits:
 *   - GPU utilization ≤ 80%
 *   - CPU utilization ≤ 75%
 *   - IO throttling (max ops/sec)
 *   - Memory pressure monitoring
 *
 * Auto-throttle when limits exceeded. No training in hunt engine.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace hunt_engine {

// =========================================================================
// RESOURCE LIMITS
// =========================================================================

struct ResourceLimits {
  double max_gpu_utilization; // 0.0–1.0 (default: 0.80)
  double max_cpu_utilization; // 0.0–1.0 (default: 0.75)
  uint32_t max_io_ops_sec;    // default: 1000
  uint32_t max_memory_mb;     // default: 4096
};

static ResourceLimits default_limits() { return {0.80, 0.75, 1000, 4096}; }

// =========================================================================
// RESOURCE SNAPSHOT
// =========================================================================

struct ResourceSnapshot {
  double gpu_utilization;
  double cpu_utilization;
  uint32_t io_ops_sec;
  uint32_t memory_mb;
  double gpu_temp_c;
};

// =========================================================================
// GOVERNOR VERDICT
// =========================================================================

struct GovernorVerdict {
  bool allow_new_target;
  bool throttle_io;
  bool pause_execution;
  double gpu_headroom; // remaining before limit
  double cpu_headroom;
  char reason[256];
};

// =========================================================================
// RESOURCE GOVERNOR
// =========================================================================

class ResourceGovernor {
public:
  explicit ResourceGovernor(ResourceLimits limits = default_limits())
      : limits_(limits), violation_count_(0) {}

  GovernorVerdict evaluate(const ResourceSnapshot &snap) const {
    GovernorVerdict v;
    std::memset(&v, 0, sizeof(v));

    v.gpu_headroom = limits_.max_gpu_utilization - snap.gpu_utilization;
    v.cpu_headroom = limits_.max_cpu_utilization - snap.cpu_utilization;

    bool gpu_ok = snap.gpu_utilization <= limits_.max_gpu_utilization;
    bool cpu_ok = snap.cpu_utilization <= limits_.max_cpu_utilization;
    bool io_ok = snap.io_ops_sec <= limits_.max_io_ops_sec;
    bool mem_ok = snap.memory_mb <= limits_.max_memory_mb;

    v.throttle_io = !io_ok;
    v.pause_execution = !gpu_ok || !cpu_ok || !mem_ok;
    v.allow_new_target = gpu_ok && cpu_ok && io_ok && mem_ok;

    if (v.pause_execution) {
      std::snprintf(v.reason, sizeof(v.reason),
                    "RESOURCE_LIMIT: GPU=%.0f%% CPU=%.0f%% IO=%u MEM=%uMB",
                    snap.gpu_utilization * 100, snap.cpu_utilization * 100,
                    snap.io_ops_sec, snap.memory_mb);
    } else if (v.throttle_io) {
      std::snprintf(v.reason, sizeof(v.reason),
                    "IO_THROTTLE: %u ops/sec > %u limit", snap.io_ops_sec,
                    limits_.max_io_ops_sec);
    } else {
      std::snprintf(v.reason, sizeof(v.reason), "RESOURCES_OK");
    }

    return v;
  }

  const ResourceLimits &limits() const { return limits_; }

private:
  ResourceLimits limits_;
  uint32_t violation_count_;
};

} // namespace hunt_engine
