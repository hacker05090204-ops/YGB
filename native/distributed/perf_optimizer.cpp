/*
 * perf_optimizer.cpp — Performance Optimization (Phase 7)
 *
 * Mixed precision FP16/TF32
 * Dynamic batch scaler
 * IO overlap controller
 * Thermal throttle
 * GPU 65-80% target enforcement
 *
 * C API for Python bridge.
 */

#include <cstdint>
#include <cstring>

#ifdef __cplusplus
extern "C" {
#endif

#define TARGET_LOW 0.65
#define TARGET_HIGH 0.80
#define TEMP_WARN 80.0
#define TEMP_THROTTLE 85.0
#define MIN_BATCH 4
#define MAX_BATCH 256

typedef struct {
  /* Current state */
  int batch_size;
  int fp16_enabled;
  int tf32_enabled;
  int io_overlap;
  int gradient_checkpoint;
  int num_workers;

  /* Telemetry */
  double gpu_util;
  double vram_used_mb;
  double vram_total_mb;
  double temp_c;
  double throughput_sps; /* samples per second */
} PerfState;

typedef struct {
  int batch_action; /* -1=decrease, 0=stable, 1=increase */
  int new_batch;
  int fp16_rec;
  int tf32_rec;
  int io_overlap_rec;
  int checkpoint_rec;
  int throttled;
  double score;         /* 0-1 optimization score */
  double predicted_sps; /* predicted throughput */
} PerfDecision;

/* Globals */
static PerfState g_state;
static int g_step_count = 0;

/* ---- Public API ---- */

int perf_init(int batch_size, double vram_total_mb) {
  memset(&g_state, 0, sizeof(g_state));
  g_state.batch_size = batch_size;
  g_state.fp16_enabled = 1;
  g_state.tf32_enabled = 1;
  g_state.io_overlap = 1;
  g_state.num_workers = 4;
  g_state.vram_total_mb = vram_total_mb;
  g_step_count = 0;
  return 0;
}

PerfDecision perf_step(double gpu_util, double vram_used_mb, double temp_c,
                       double throughput_sps) {
  PerfDecision d;
  memset(&d, 0, sizeof(d));
  g_step_count++;

  g_state.gpu_util = gpu_util;
  g_state.vram_used_mb = vram_used_mb;
  g_state.temp_c = temp_c;
  g_state.throughput_sps = throughput_sps;

  d.fp16_rec = 1;
  d.tf32_rec = 1;
  d.io_overlap_rec = 1;
  d.throttled = 0;

  /* VRAM pressure → gradient checkpointing */
  d.checkpoint_rec = (vram_used_mb > g_state.vram_total_mb * 0.85) ? 1 : 0;

  /* Thermal throttle */
  if (temp_c >= TEMP_THROTTLE) {
    int dec = g_state.batch_size / 4;
    if (dec < 1)
      dec = 1;
    d.batch_action = -1;
    d.new_batch = g_state.batch_size - dec;
    if (d.new_batch < MIN_BATCH)
      d.new_batch = MIN_BATCH;
    d.throttled = 1;
    d.score = 0.2;
    g_state.batch_size = d.new_batch;
    d.predicted_sps = throughput_sps * 0.7;
    return d;
  }

  /* GPU utilization band */
  if (gpu_util < TARGET_LOW) {
    int inc = g_state.batch_size / 4;
    if (inc < 1)
      inc = 1;
    d.batch_action = 1;
    d.new_batch = g_state.batch_size + inc;
    if (d.new_batch > MAX_BATCH)
      d.new_batch = MAX_BATCH;
    d.score = 0.65;
    d.predicted_sps = throughput_sps * 1.2;
  } else if (gpu_util > TARGET_HIGH) {
    int dec = g_state.batch_size / 8;
    if (dec < 1)
      dec = 1;
    d.batch_action = -1;
    d.new_batch = g_state.batch_size - dec;
    if (d.new_batch < MIN_BATCH)
      d.new_batch = MIN_BATCH;
    d.score = 0.75;
    d.predicted_sps = throughput_sps * 0.95;
  } else {
    d.batch_action = 0;
    d.new_batch = g_state.batch_size;
    d.score = 1.0;
    d.predicted_sps = throughput_sps;
  }

  g_state.batch_size = d.new_batch;
  return d;
}

void perf_get_state(PerfState *out) {
  if (out)
    *out = g_state;
}
int perf_get_batch(void) { return g_state.batch_size; }
int perf_get_step_count(void) { return g_step_count; }

#ifdef __cplusplus
}
#endif
