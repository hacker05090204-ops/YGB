/**
 * training_telemetry.cpp — Live Training Telemetry (Phase 1)
 *
 * Emit telemetry every 1 second:
 * - epoch, batch, samples_processed
 * - samples_per_sec, gpu_utilization
 * - loss, running_accuracy
 *
 * C API for Python ctypes / socket relay.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <mutex>

// ============================================================================
// CONSTANTS
// ============================================================================

#define MAX_HISTORY 3600 // 1 hour of 1-sec samples
#define EMIT_INTERVAL_SEC 1

// ============================================================================
// TYPES
// ============================================================================

struct TelemetrySnapshot {
  int epoch;
  int batch;
  int total_batches;
  long samples_processed;
  long total_samples;
  double samples_per_sec;
  double gpu_utilization; // 0.0 - 1.0
  double gpu_memory_used_mb;
  double gpu_temp_celsius;
  double loss;
  double running_accuracy;
  double learning_rate;
  long timestamp;
};

struct TelemetryState {
  TelemetrySnapshot history[MAX_HISTORY];
  int history_count;
  TelemetrySnapshot current;
  int training_active;
  long training_started;
  long last_emit;
  int stall_detected; // No update for 10s
};

// ============================================================================
// GLOBAL STATE
// ============================================================================

static struct {
  TelemetryState state;
  std::mutex mu;
  int initialized;
} g_telem = {.initialized = 0};

static long _now() { return (long)time(NULL); }

// ============================================================================
// C API
// ============================================================================

extern "C" {

int telemetry_init(void) {
  std::lock_guard<std::mutex> lock(g_telem.mu);
  memset(&g_telem.state, 0, sizeof(TelemetryState));
  g_telem.state.training_active = 0;
  g_telem.initialized = 1;
  fprintf(stdout, "[TELEMETRY] Initialized: interval=%ds max_history=%d\n",
          EMIT_INTERVAL_SEC, MAX_HISTORY);
  return 0;
}

int telemetry_start_training(long total_samples) {
  std::lock_guard<std::mutex> lock(g_telem.mu);
  g_telem.state.training_active = 1;
  g_telem.state.training_started = _now();
  g_telem.state.current.total_samples = total_samples;
  g_telem.state.stall_detected = 0;
  return 0;
}

int telemetry_stop_training(void) {
  std::lock_guard<std::mutex> lock(g_telem.mu);
  g_telem.state.training_active = 0;
  return 0;
}

/**
 * Record a telemetry snapshot.
 */
int telemetry_record(int epoch, int batch, int total_batches,
                     long samples_processed, double samples_per_sec,
                     double gpu_utilization, double gpu_memory_mb,
                     double gpu_temp, double loss, double accuracy,
                     double learning_rate) {
  std::lock_guard<std::mutex> lock(g_telem.mu);

  TelemetrySnapshot snap;
  snap.epoch = epoch;
  snap.batch = batch;
  snap.total_batches = total_batches;
  snap.samples_processed = samples_processed;
  snap.total_samples = g_telem.state.current.total_samples;
  snap.samples_per_sec = samples_per_sec;
  snap.gpu_utilization = gpu_utilization;
  snap.gpu_memory_used_mb = gpu_memory_mb;
  snap.gpu_temp_celsius = gpu_temp;
  snap.loss = loss;
  snap.running_accuracy = accuracy;
  snap.learning_rate = learning_rate;
  snap.timestamp = _now();

  g_telem.state.current = snap;
  g_telem.state.last_emit = snap.timestamp;
  g_telem.state.stall_detected = 0;

  // Add to history (circular)
  if (g_telem.state.history_count < MAX_HISTORY) {
    g_telem.state.history[g_telem.state.history_count++] = snap;
  } else {
    // Shift and append
    memmove(&g_telem.state.history[0], &g_telem.state.history[1],
            (MAX_HISTORY - 1) * sizeof(TelemetrySnapshot));
    g_telem.state.history[MAX_HISTORY - 1] = snap;
  }

  return 0;
}

/**
 * Get current telemetry state.
 */
int telemetry_get_current(int *out_epoch, int *out_batch, long *out_samples,
                          double *out_sps, double *out_gpu, double *out_loss,
                          double *out_acc, double *out_lr, int *out_stalled) {
  std::lock_guard<std::mutex> lock(g_telem.mu);

  // Stall detection: 10 seconds with no update
  long now = _now();
  if (g_telem.state.training_active && g_telem.state.last_emit > 0 &&
      (now - g_telem.state.last_emit) >= 10) {
    g_telem.state.stall_detected = 1;
  }

  TelemetrySnapshot &c = g_telem.state.current;
  if (out_epoch)
    *out_epoch = c.epoch;
  if (out_batch)
    *out_batch = c.batch;
  if (out_samples)
    *out_samples = c.samples_processed;
  if (out_sps)
    *out_sps = c.samples_per_sec;
  if (out_gpu)
    *out_gpu = c.gpu_utilization;
  if (out_loss)
    *out_loss = c.loss;
  if (out_acc)
    *out_acc = c.running_accuracy;
  if (out_lr)
    *out_lr = c.learning_rate;
  if (out_stalled)
    *out_stalled = g_telem.state.stall_detected;

  return 0;
}

/**
 * Calculate ETA in seconds.
 */
double telemetry_eta_seconds(void) {
  std::lock_guard<std::mutex> lock(g_telem.mu);
  TelemetrySnapshot &c = g_telem.state.current;
  if (c.samples_per_sec <= 0)
    return -1.0;
  long remaining = c.total_samples - c.samples_processed;
  if (remaining <= 0)
    return 0.0;
  return (double)remaining / c.samples_per_sec;
}

int telemetry_history_count(void) {
  std::lock_guard<std::mutex> lock(g_telem.mu);
  return g_telem.state.history_count;
}

int telemetry_is_active(void) {
  std::lock_guard<std::mutex> lock(g_telem.mu);
  return g_telem.state.training_active;
}

} // extern "C"
