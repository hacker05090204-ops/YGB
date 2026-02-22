/**
 * gpu_load_control.cpp — Adaptive GPU Utilization Control (Phase 2)
 *
 * Target band: 65–80% GPU utilization.
 * - If < 60%: increase batch, increase workers
 * - If > 85%: reduce batch, prevent OOM
 *
 * Monitor: utilization, VRAM, temperature.
 * C API for Python ctypes.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <mutex>

// ============================================================================
// CONSTANTS
// ============================================================================

#define GPU_TARGET_LOW 65.0      // Target lower bound %
#define GPU_TARGET_HIGH 80.0     // Target upper bound %
#define GPU_SCALE_UP_THRESH 60.0 // Below this: scale up
#define GPU_SCALE_DN_THRESH 85.0 // Above this: scale down
#define VRAM_SAFETY_MB 256       // Reserve this much VRAM
#define TEMP_WARN_C 80.0
#define TEMP_THROTTLE_C 90.0
#define MAX_HISTORY 600 // 10 min at 1/sec

// ============================================================================
// TYPES
// ============================================================================

struct GPUSnapshot {
  double utilization; // 0-100
  double vram_used_mb;
  double vram_total_mb;
  double temperature;
  int batch_size;
  int num_workers;
  long timestamp;
};

enum GPUAction {
  GPU_HOLD = 0,
  GPU_SCALE_UP = 1,
  GPU_SCALE_DOWN = 2,
  GPU_THROTTLE = 3,
};

struct GPUControlState {
  GPUSnapshot history[MAX_HISTORY];
  int history_count;
  GPUSnapshot current;
  int recommended_batch;
  int recommended_workers;
  int last_action;
  double avg_utilization;
};

// ============================================================================
// GLOBAL STATE
// ============================================================================

static struct {
  GPUControlState state;
  std::mutex mu;
  int initialized;
} g_gpu = {.initialized = 0};

// ============================================================================
// C API
// ============================================================================

extern "C" {

int gpu_control_init(int initial_batch, int initial_workers) {
  std::lock_guard<std::mutex> lock(g_gpu.mu);
  memset(&g_gpu.state, 0, sizeof(GPUControlState));
  g_gpu.state.recommended_batch = initial_batch;
  g_gpu.state.recommended_workers = initial_workers;
  g_gpu.initialized = 1;
  fprintf(stdout, "[GPU_CTRL] Init: batch=%d workers=%d target=%0.f-%0.f%%\n",
          initial_batch, initial_workers, GPU_TARGET_LOW, GPU_TARGET_HIGH);
  return 0;
}

/**
 * Record GPU metrics and get adaptive action.
 * Returns: 0=hold, 1=scale_up, 2=scale_down, 3=throttle
 */
int gpu_control_update(double utilization, double vram_used_mb,
                       double vram_total_mb, double temperature,
                       int current_batch, int current_workers) {
  std::lock_guard<std::mutex> lock(g_gpu.mu);

  GPUSnapshot snap;
  snap.utilization = utilization;
  snap.vram_used_mb = vram_used_mb;
  snap.vram_total_mb = vram_total_mb;
  snap.temperature = temperature;
  snap.batch_size = current_batch;
  snap.num_workers = current_workers;
  snap.timestamp = (long)time(NULL);

  g_gpu.state.current = snap;

  // History (circular)
  if (g_gpu.state.history_count < MAX_HISTORY) {
    g_gpu.state.history[g_gpu.state.history_count++] = snap;
  } else {
    memmove(&g_gpu.state.history[0], &g_gpu.state.history[1],
            (MAX_HISTORY - 1) * sizeof(GPUSnapshot));
    g_gpu.state.history[MAX_HISTORY - 1] = snap;
  }

  // Rolling average (last 10)
  int window = g_gpu.state.history_count < 10 ? g_gpu.state.history_count : 10;
  double sum = 0;
  for (int i = g_gpu.state.history_count - window;
       i < g_gpu.state.history_count; i++) {
    sum += g_gpu.state.history[i].utilization;
  }
  g_gpu.state.avg_utilization = sum / (window > 0 ? window : 1);

  int action = GPU_HOLD;

  // Thermal throttle (highest priority)
  if (temperature >= TEMP_THROTTLE_C) {
    g_gpu.state.recommended_batch =
        current_batch > 32 ? current_batch - current_batch / 4 : 32;
    action = GPU_THROTTLE;
  }
  // VRAM safety
  else if ((vram_total_mb - vram_used_mb) < VRAM_SAFETY_MB) {
    g_gpu.state.recommended_batch =
        current_batch > 32 ? current_batch - current_batch / 8 : 32;
    action = GPU_SCALE_DOWN;
  }
  // Under-utilized: scale up
  else if (g_gpu.state.avg_utilization < GPU_SCALE_UP_THRESH) {
    int new_batch = current_batch + current_batch / 8;
    // Don't exceed VRAM
    double vram_free = vram_total_mb - vram_used_mb - VRAM_SAFETY_MB;
    if (vram_free > 100) {
      g_gpu.state.recommended_batch = new_batch;
      g_gpu.state.recommended_workers =
          current_workers < 8 ? current_workers + 1 : 8;
      action = GPU_SCALE_UP;
    }
  }
  // Over-utilized: scale down
  else if (g_gpu.state.avg_utilization > GPU_SCALE_DN_THRESH) {
    g_gpu.state.recommended_batch =
        current_batch > 32 ? current_batch - current_batch / 16 : 32;
    action = GPU_SCALE_DOWN;
  }

  g_gpu.state.last_action = action;
  return action;
}

int gpu_control_get_batch(void) {
  std::lock_guard<std::mutex> lock(g_gpu.mu);
  return g_gpu.state.recommended_batch;
}

int gpu_control_get_workers(void) {
  std::lock_guard<std::mutex> lock(g_gpu.mu);
  return g_gpu.state.recommended_workers;
}

double gpu_control_avg_util(void) {
  std::lock_guard<std::mutex> lock(g_gpu.mu);
  return g_gpu.state.avg_utilization;
}

int gpu_control_history_count(void) {
  std::lock_guard<std::mutex> lock(g_gpu.mu);
  return g_gpu.state.history_count;
}

} // extern "C"
