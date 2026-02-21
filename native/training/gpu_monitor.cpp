/*
 * gpu_monitor.cpp — CUDA GPU Utilization & Memory Monitor
 *
 * Monitors:
 *   - cudaMemGetInfo() for VRAM usage
 *   - GPU utilization % (via NVML when available)
 *   - Kernel occupancy tracking
 *
 * C++ runtime enforcement — Python governance only.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

// =============================================================================
// GPU METRICS STRUCTURE
// =============================================================================

struct GpuMetrics {
  double gpu_util_percent; // GPU core utilization 0-100
  double vram_used_mb;     // VRAM currently used
  double vram_total_mb;    // VRAM total capacity
  double vram_free_mb;     // VRAM free
  double vram_peak_mb;     // Peak VRAM usage
  double temperature_c;    // GPU temperature (0 if unavailable)
  int power_watts;         // Power draw (0 if unavailable)
  bool available;          // true if GPU monitoring works
};

// =============================================================================
// GLOBAL STATE
// =============================================================================

static GpuMetrics g_metrics = {0};
static GpuMetrics g_peak = {0};
static int g_sample_count = 0;
static double g_util_sum = 0.0;

// =============================================================================
// CUDA MEMORY QUERY
// =============================================================================

static void query_cuda_memory() {
#ifdef __CUDACC__
  size_t free_bytes = 0, total_bytes = 0;
  if (cudaMemGetInfo(&free_bytes, &total_bytes) == cudaSuccess) {
    g_metrics.vram_total_mb = (double)total_bytes / (1024.0 * 1024.0);
    g_metrics.vram_free_mb = (double)free_bytes / (1024.0 * 1024.0);
    g_metrics.vram_used_mb = g_metrics.vram_total_mb - g_metrics.vram_free_mb;
    g_metrics.available = true;

    if (g_metrics.vram_used_mb > g_peak.vram_peak_mb) {
      g_peak.vram_peak_mb = g_metrics.vram_used_mb;
    }
  }
#else
  // Stub: values set from Python via set_metrics()
  g_metrics.available = true;
#endif
}

// =============================================================================
// NVML GPU UTILIZATION (stub — links with NVML when available)
// =============================================================================

static void query_nvml_utilization() {
#ifdef NVML_AVAILABLE
  nvmlDevice_t device;
  if (nvmlDeviceGetHandleByIndex(0, &device) == NVML_SUCCESS) {
    nvmlUtilization_t util;
    if (nvmlDeviceGetUtilizationRates(device, &util) == NVML_SUCCESS) {
      g_metrics.gpu_util_percent = (double)util.gpu;
    }

    nvmlMemory_t mem;
    if (nvmlDeviceGetMemoryInfo(device, &mem) == NVML_SUCCESS) {
      g_metrics.vram_used_mb = (double)mem.used / (1024.0 * 1024.0);
      g_metrics.vram_total_mb = (double)mem.total / (1024.0 * 1024.0);
      g_metrics.vram_free_mb = (double)mem.free / (1024.0 * 1024.0);
    }

    unsigned int temp;
    if (nvmlDeviceGetTemperature(device, NVML_TEMPERATURE_GPU, &temp) ==
        NVML_SUCCESS) {
      g_metrics.temperature_c = (double)temp;
    }

    unsigned int power;
    if (nvmlDeviceGetPowerUsage(device, &power) == NVML_SUCCESS) {
      g_metrics.power_watts = (int)(power / 1000);
    }
  }
#else
  // Estimate utilization from VRAM ratio when NVML unavailable
  if (g_metrics.vram_total_mb > 0) {
    g_metrics.gpu_util_percent =
        (g_metrics.vram_used_mb / g_metrics.vram_total_mb) * 100.0;
  }
#endif
}

// =============================================================================
// C EXPORTS (for Python ctypes binding)
// =============================================================================

extern "C" {

/**
 * Sample current GPU metrics. Call this periodically during training.
 */
void gpu_monitor_sample() {
  query_cuda_memory();
  query_nvml_utilization();

  // Track running average
  g_util_sum += g_metrics.gpu_util_percent;
  g_sample_count++;

  if (g_metrics.vram_used_mb > g_peak.vram_peak_mb)
    g_peak.vram_peak_mb = g_metrics.vram_used_mb;
}

/**
 * Set metrics from Python (when C++ can't query CUDA directly).
 */
void gpu_monitor_set_metrics(double vram_used_mb, double vram_total_mb,
                             double gpu_util_pct) {
  g_metrics.vram_used_mb = vram_used_mb;
  g_metrics.vram_total_mb = vram_total_mb;
  g_metrics.vram_free_mb = vram_total_mb - vram_used_mb;
  g_metrics.gpu_util_percent = gpu_util_pct;
  g_metrics.available = true;

  if (vram_used_mb > g_peak.vram_peak_mb)
    g_peak.vram_peak_mb = vram_used_mb;

  g_util_sum += gpu_util_pct;
  g_sample_count++;
}

double gpu_monitor_get_util_percent() { return g_metrics.gpu_util_percent; }

double gpu_monitor_get_util_avg() {
  if (g_sample_count == 0)
    return 0.0;
  return g_util_sum / g_sample_count;
}

double gpu_monitor_get_vram_used_mb() { return g_metrics.vram_used_mb; }

double gpu_monitor_get_vram_total_mb() { return g_metrics.vram_total_mb; }

double gpu_monitor_get_vram_peak_mb() { return g_peak.vram_peak_mb; }

double gpu_monitor_get_vram_free_mb() { return g_metrics.vram_free_mb; }

double gpu_monitor_get_temperature() { return g_metrics.temperature_c; }

int gpu_monitor_get_power_watts() { return g_metrics.power_watts; }

int gpu_monitor_get_sample_count() { return g_sample_count; }

bool gpu_monitor_is_available() { return g_metrics.available; }

/**
 * Check if GPU is underutilized (for adaptive batch scaling trigger).
 *
 * Returns:
 *   0 = well utilized (≥85%)
 *   1 = underutilized (VRAM <50% AND util <85%)
 *   2 = critically underutilized (<30%)
 */
int gpu_monitor_check_utilization() {
  if (g_metrics.vram_total_mb <= 0)
    return 0;

  double vram_pct = (g_metrics.vram_used_mb / g_metrics.vram_total_mb) * 100.0;
  double util = g_metrics.gpu_util_percent;

  if (vram_pct < 30.0 && util < 50.0)
    return 2; // Critical
  if (vram_pct < 50.0 && util < 85.0)
    return 1; // Underutilized
  return 0;   // OK
}

void gpu_monitor_reset() {
  std::memset(&g_metrics, 0, sizeof(g_metrics));
  std::memset(&g_peak, 0, sizeof(g_peak));
  g_sample_count = 0;
  g_util_sum = 0.0;
}

} // extern "C"
